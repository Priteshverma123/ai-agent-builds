"""The end-to-end intake pipeline.

  pass 1  classify -> extract -> validate schema          (every document)
  pass 2  vendor -> business rules -> 3-way match -> decide (invoices, now that all POs/GRNs are known)
  pass 3  export approved to ERP, queue exceptions, write the run report
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from ..adapters.llm import LLM
from ..adapters.storage import OutputWriter, RawDocument, to_erp_record
from ..config import ClientConfig
from ..domain.matching import three_way_match
from ..domain.models import (DocType, DocumentResult, GoodsReceipt, Invoice, PurchaseOrder, Status)
from ..domain.rules import RuleContext, validate_invoice
from ..domain.vendors import VendorMaster
from .extraction import classify, extract


@dataclass
class RunOutput:
    results: list[DocumentResult]
    erp_records: list[dict[str, Any]]
    duration_ms: float
    files: dict[str, str] = field(default_factory=dict)

    def by_status(self, status: Status) -> list[DocumentResult]:
        return [r for r in self.results if r.status is status]


class IntakePipeline:
    def __init__(self, cfg: ClientConfig, vendors: VendorMaster, posted_keys: frozenset[tuple[str, str]],
                 llm: LLM) -> None:
        self.cfg, self.vendors, self.posted_keys, self.llm = cfg, vendors, posted_keys, llm

    def run(self, docs: list[RawDocument]) -> RunOutput:
        start = time.perf_counter()
        results: list[DocumentResult] = []
        parsed: dict[str, BaseModel] = {}
        for raw in docs:                                   # pass 1
            result = DocumentResult(doc_id=raw.doc_id)
            results.append(result)
            doc_type = classify(raw, self.llm, self.cfg, result)
            if doc_type is not DocType.UNKNOWN and (doc := extract(raw, doc_type, self.llm, self.cfg, result)):
                parsed[raw.doc_id] = doc

        pos = {d.po_number: (d, self._vendor_id(d.vendor_name)) for d in parsed.values() if isinstance(d, PurchaseOrder)}
        grns: dict[str, list[GoodsReceipt]] = {}
        for d in parsed.values():
            if isinstance(d, GoodsReceipt):
                grns.setdefault(d.po_number, []).append(d)

        seen = set(self.posted_keys)
        erp_records: list[dict[str, Any]] = []
        for result in results:                             # pass 2
            doc = parsed.get(result.doc_id)
            if isinstance(doc, Invoice):
                self._check_invoice(doc, result, pos, grns, seen)
            elif isinstance(doc, PurchaseOrder):
                result.vendor_id = pos[doc.po_number][1]
            self._decide(result, doc)
            if result.status is Status.APPROVED and isinstance(doc, Invoice):
                seen.add((result.vendor_id, doc.invoice_number))
                erp_records.append(to_erp_record(result, self.vendors.get(result.vendor_id), self.cfg.erp_mapping))
        return RunOutput(results, erp_records, round((time.perf_counter() - start) * 1000, 1))

    def _vendor_id(self, name: str, tax_id: str | None = None) -> str | None:
        vendor, _ = self.vendors.resolve(name, tax_id)
        return vendor.vendor_id if vendor else None

    def _check_invoice(self, inv: Invoice, result: DocumentResult,
                       pos: dict[str, tuple[PurchaseOrder, str | None]],
                       grns: dict[str, list[GoodsReceipt]], seen: set[tuple[str, str]]) -> None:
        vendor, how = self.vendors.resolve(inv.vendor_name, inv.vendor_tax_id)
        result.vendor_id = vendor.vendor_id if vendor else None
        result.log("vendor", f"{vendor.vendor_id} {vendor.name} (matched by {how})" if vendor
                   else f"{inv.vendor_name!r}: no match in vendor master", ok=vendor is not None)

        ctx = RuleContext(vendor, self.cfg.today(), self.cfg.tolerances, self.cfg.require_po, frozenset(seen))
        rule_issues = validate_invoice(inv, ctx)
        result.issues.extend(rule_issues)
        result.log("validate", "; ".join(f"{i.code}: {i.message}" for i in rule_issues) or "all rules passed",
                   ok=not any(i.severity.value == "error" for i in rule_issues))

        po, po_vendor = pos.get(inv.po_number or "", (None, None))
        receipts = grns.get(inv.po_number or "", [])
        match_issues = three_way_match(inv, po, receipts, po_vendor, result.vendor_id, self.cfg.tolerances.price_pct)
        result.issues.extend(match_issues)
        if inv.po_number:
            grn_ids = ",".join(g.grn_number for g in receipts) or "no GRN"
            detail = "; ".join(f"{i.code}: {i.message}" for i in match_issues) or "invoice = PO = receipt"
            result.log("match", f"{inv.po_number} + {grn_ids}: {detail}", ok=not match_issues)

    def _decide(self, result: DocumentResult, doc: BaseModel | None) -> None:
        if result.blocking or doc is None:
            result.status = Status.EXCEPTION
            result.owner = self.cfg.owner_for([i.code for i in result.blocking])
            result.log("decide", f"EXCEPTION -> {result.owner}: " + ", ".join(i.code for i in result.blocking), ok=False)
        elif isinstance(doc, Invoice):
            result.status = Status.APPROVED
            result.log("decide", f"APPROVED -> ERP ({doc.currency} {doc.total:,.2f})")
        else:
            result.status = Status.REFERENCE
            result.log("decide", "REFERENCE (kept for matching)")


def write_outputs(run: RunOutput, writer: OutputWriter, report_md: str) -> RunOutput:
    jsonl, csv_path = writer.write_erp(run.erp_records)
    run.files = {
        "erp_jsonl": str(jsonl),
        "erp_csv": str(csv_path),
        "exceptions": str(writer.write_exceptions(run.by_status(Status.EXCEPTION))),
        "report": str(writer.write_text("run_report.md", report_md)),
    }
    return run
