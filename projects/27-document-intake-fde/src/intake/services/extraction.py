"""Classification and extraction: the only two steps that need a model.

Structured inputs (JSON / EDI) skip the model entirely. Unstructured text goes through the LLM, then
through client-specific normalisation (date formats), then through pydantic. If validation fails we
give the model one repair attempt with the exact errors, and after that it's a human's job.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from ..adapters.llm import LABELS, LLM
from ..adapters.storage import RawDocument
from ..config import ClientConfig
from ..domain.models import SCHEMAS, DocType, DocumentResult, Issue

DATE_FIELDS = ("invoice_date", "due_date", "order_date", "received_date")


def classify(raw: RawDocument, llm: LLM, cfg: ClientConfig, result: DocumentResult) -> DocType:
    if raw.is_json:
        label, confidence, why = json.loads(raw.text).get("document_type", "unknown"), 1.0, "declared in JSON"
    else:
        answer = llm.classify(raw.text, LABELS)
        label, confidence, why = answer.get("label", "unknown"), float(answer.get("confidence", 0)), answer.get("rationale", "")
    doc_type = DocType(label) if label in DocType._value2member_map_ else DocType.UNKNOWN
    result.doc_type, result.classification_confidence = doc_type, confidence
    ok = doc_type is not DocType.UNKNOWN and confidence >= cfg.min_classification_confidence
    result.log("classify", f"{doc_type.value} ({confidence:.2f}) {why}", ok)
    if doc_type is DocType.UNKNOWN:
        result.issues.append(Issue(code="UNCLASSIFIED", message="not an invoice, PO or goods receipt"))
    elif confidence < cfg.min_classification_confidence:
        result.issues.append(Issue(code="LOW_CONFIDENCE", message=f"classified {doc_type.value} with {confidence:.2f}"))
    return doc_type


def normalize_dates(data: dict[str, Any], formats: list[str]) -> dict[str, Any]:
    """Turn '10/05/2026' into '2026-10-05' using the client's known formats; leave unknowns for pydantic."""
    out = dict(data)
    for field in DATE_FIELDS:
        value = out.get(field)
        if isinstance(value, str):
            for fmt in formats:
                try:
                    out[field] = datetime.strptime(value, fmt).date().isoformat()
                    break
                except ValueError:
                    continue
        elif isinstance(value, date):
            out[field] = value.isoformat()
    return out


def coverage(data: dict[str, Any], schema: type[BaseModel]) -> float:
    required = [name for name, f in schema.model_fields.items() if f.is_required()]
    return round(sum(1 for name in required if data.get(name) not in (None, "", [])) / len(required), 2)


def _errors(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:6])


def extract(raw: RawDocument, doc_type: DocType, llm: LLM, cfg: ClientConfig,
            result: DocumentResult) -> BaseModel | None:
    schema = SCHEMAS[doc_type]
    if raw.is_json:
        data, source = json.loads(raw.text), "parsed JSON (no LLM)"
    else:
        data, source = llm.extract(raw.text, doc_type.value, schema.model_json_schema()), f"{llm.name} LLM"
    for attempt in range(2):
        data = normalize_dates({k: v for k, v in data.items() if k != "document_type"}, cfg.date_formats)
        result.extraction_confidence = coverage(data, schema)
        try:
            doc = schema.model_validate(data)
        except ValidationError as exc:
            result.log("extract", f"attempt {attempt + 1} failed: {_errors(exc)}", ok=False)
            if raw.is_json or attempt == 1:
                result.issues.append(Issue(code="EXTRACTION_FAILED", message=_errors(exc)))
                return None
            data = llm.extract(raw.text, doc_type.value, schema.model_json_schema(), feedback=_errors(exc))
            continue
        result.data = doc.model_dump(mode="json")
        result.log("extract", f"{source}: {_headline(doc)} ({result.extraction_confidence:.0%} of required fields)")
        return doc
    return None


def _headline(doc: BaseModel) -> str:
    d = doc.model_dump()
    key = d.get("invoice_number") or d.get("grn_number") or d.get("po_number")
    total = f", total {d['total']:.2f}" if "total" in d else ""
    return f"{key}, {len(d['lines'])} line(s){total}"
