"""File-system adapters: read the inbox and master data, write ERP files and the exceptions queue.

In a real deployment the inbox is an email/SFTP/S3 drop and the ERP is SAP, NetSuite or Dynamics;
only this module changes.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..config import ErpMapping
from ..domain.models import DocumentResult, Vendor


@dataclass(frozen=True)
class RawDocument:
    doc_id: str
    text: str

    @property
    def is_json(self) -> bool:
        return self.doc_id.endswith(".json")


def load_inbox(folder: Path) -> list[RawDocument]:
    return [RawDocument(p.name, p.read_text(encoding="utf-8"))
            for p in sorted(folder.iterdir()) if p.suffix in (".txt", ".json")]


def load_vendors(path: Path) -> list[Vendor]:
    return [Vendor.model_validate(v) for v in json.loads(path.read_text(encoding="utf-8"))]


def load_posted_keys(path: Path) -> frozenset[tuple[str, str]]:
    """(vendor_id, invoice_number) pairs the ERP already holds: the duplicate-payment guard."""
    if not path.exists():
        return frozenset()
    return frozenset((r["vendor_id"], r["invoice_number"]) for r in json.loads(path.read_text(encoding="utf-8")))


def _resolve(path: str, context: dict[str, Any]) -> Any:
    value: Any = context
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _fmt(value: Any, date_format: str) -> Any:
    if isinstance(value, date):
        return value.strftime(date_format)
    if isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-":
        return date.fromisoformat(value).strftime(date_format)
    return value


def to_erp_record(result: DocumentResult, vendor: Vendor, mapping: ErpMapping) -> dict[str, Any]:
    """Map one approved invoice to the client's ERP layout, purely from config."""
    context = dict(result.data or {}) | {"vendor_id": result.vendor_id, "vendor": vendor.model_dump()}
    header = {col: _fmt(_resolve(src, context), mapping.date_format) for col, src in mapping.header.items()}
    header["Lines"] = [{"LineNo": i} | {col: _resolve(src, line) for col, src in mapping.line.items()}
                       for i, line in enumerate(context["lines"], start=1)]
    return header


class OutputWriter:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)

    def write_erp(self, records: list[dict[str, Any]]) -> tuple[Path, Path]:
        jsonl = self.out_dir / "erp_invoices.jsonl"
        jsonl.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        csv_path = self.out_dir / "erp_invoice_lines.csv"
        rows = [{k: v for k, v in r.items() if k != "Lines"} | line for r in records for line in r["Lines"]]
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            if rows:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        return jsonl, csv_path

    def write_exceptions(self, results: list[DocumentResult]) -> Path:
        path = self.out_dir / "exceptions.jsonl"
        lines = [json.dumps({"doc_id": r.doc_id, "doc_type": r.doc_type.value, "owner": r.owner,
                             "vendor_id": r.vendor_id,
                             "document_no": (r.data or {}).get("invoice_number"),
                             "total": (r.data or {}).get("total"),
                             "reasons": [i.model_dump(mode="json") for i in r.blocking]}) + "\n"
                 for r in results]
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def write_text(self, name: str, content: str) -> Path:
        path = self.out_dir / name
        path.write_text(content, encoding="utf-8")
        return path
