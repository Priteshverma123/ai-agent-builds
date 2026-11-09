"""Score a run against the golden set and the client's acceptance thresholds.

This is how an FDE answers "is it good enough to go live?" with numbers the customer agreed to
in advance, instead of with a demo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Acceptance
from ..domain.models import DocumentResult


@dataclass
class EvalReport:
    metrics: dict[str, float]
    thresholds: dict[str, float]
    mismatches: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(self.metrics[k] >= v for k, v in self.thresholds.items())


def load_golden(path: Path) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["documents"]


def _actual_field(result: DocumentResult, name: str) -> Any:
    return result.vendor_id if name == "vendor_id" else (result.data or {}).get(name)


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, float) or isinstance(actual, float):
        return expected is not None and actual is not None and abs(float(expected) - float(actual)) < 0.005
    return expected == actual


def evaluate(results: list[DocumentResult], golden: dict[str, dict[str, Any]], acceptance: Acceptance) -> EvalReport:
    by_id = {r.doc_id: r for r in results}
    mismatches: list[str] = []
    cls_ok = dec_ok = fields_total = fields_ok = 0
    tp = fp = fn = 0
    for doc_id, exp in golden.items():
        r = by_id.get(doc_id)
        if r is None:
            mismatches.append(f"{doc_id}: missing from run")
            fn += len(exp["exceptions"])
            continue
        cls_ok += r.doc_type.value == exp["doc_type"]
        dec_ok += r.status.value == exp["status"]
        if r.doc_type.value != exp["doc_type"]:
            mismatches.append(f"{doc_id}: type {r.doc_type.value} != {exp['doc_type']}")
        if r.status.value != exp["status"]:
            mismatches.append(f"{doc_id}: status {r.status.value} != {exp['status']}")
        for name, want in exp["fields"].items():
            fields_total += 1
            got = _actual_field(r, name)
            if _same(want, got):
                fields_ok += 1
            else:
                mismatches.append(f"{doc_id}: {name} {got!r} != {want!r}")
        got_codes, want_codes = {i.code for i in r.blocking}, set(exp["exceptions"])
        tp, fp, fn = tp + len(got_codes & want_codes), fp + len(got_codes - want_codes), fn + len(want_codes - got_codes)
        if got_codes != want_codes:
            mismatches.append(f"{doc_id}: exceptions {sorted(got_codes)} != {sorted(want_codes)}")
    n = len(golden)
    metrics = {
        "classification_accuracy": round(cls_ok / n, 3),
        "field_accuracy": round(fields_ok / fields_total, 3) if fields_total else 1.0,
        "decision_accuracy": round(dec_ok / n, 3),
        "exception_recall": round(tp / (tp + fn), 3) if tp + fn else 1.0,
        "exception_precision": round(tp / (tp + fp), 3) if tp + fp else 1.0,
    }
    return EvalReport(metrics, acceptance.model_dump(), mismatches)
