"""Run report: the thing the AP manager actually reads every morning."""

from __future__ import annotations

from collections import Counter

from ..config import ClientConfig
from ..domain.models import DocType, Status
from .pipeline import RunOutput


def _invoice_total(run: RunOutput, status: Status) -> float:
    return sum((r.data or {}).get("total", 0.0) for r in run.by_status(status) if r.doc_type is DocType.INVOICE)


def stats(run: RunOutput) -> dict[str, float | int]:
    invoices = [r for r in run.results if r.doc_type is DocType.INVOICE]
    approved = [r for r in invoices if r.status is Status.APPROVED]
    return {
        "documents": len(run.results),
        "invoices": len(invoices),
        "approved": len(approved),
        "exceptions": len(run.by_status(Status.EXCEPTION)),
        "approved_amount": round(_invoice_total(run, Status.APPROVED), 2),
        "held_amount": round(_invoice_total(run, Status.EXCEPTION), 2),
        "stp_rate": round(len(approved) / len(invoices), 3) if invoices else 0.0,
    }


def render_markdown(run: RunOutput, cfg: ClientConfig, provider: str) -> str:
    s = stats(run)
    types = Counter(r.doc_type.value for r in run.results)
    codes = Counter(i.code for r in run.by_status(Status.EXCEPTION) for i in r.blocking)
    owners = Counter(r.owner for r in run.by_status(Status.EXCEPTION))
    out = [
        f"# Intake run report: {cfg.client_name}",
        "",
        f"As of **{cfg.today()}** · extractor `{provider}` · {s['documents']} documents in {run.duration_ms} ms",
        "",
        "| Metric | Value |",
        "|---|---|",
        *[f"| documents: {k} | {v} |" for k, v in sorted(types.items())],
        f"| invoices approved (straight-through) | {s['approved']} / {s['invoices']} ({s['stp_rate']:.0%}) |",
        f"| amount posted to ERP | {s['approved_amount']:,.2f} |",
        f"| amount held in exceptions | {s['held_amount']:,.2f} |",
        "",
        "## Exceptions by reason",
        "",
        "| Code | Count |",
        "|---|---|",
        *[f"| {c} | {n} |" for c, n in codes.most_common()],
        "",
        "## Exceptions by owner",
        "",
        *[f"- **{o}**: {n}" for o, n in owners.most_common()],
        "",
        "## Exceptions queue",
        "",
        "| Document | Vendor | Doc no. | Total | Owner | Reasons |",
        "|---|---|---|---|---|---|",
    ]
    for r in run.by_status(Status.EXCEPTION):
        d = r.data or {}
        total = f"{d['total']:,.2f}" if "total" in d else ""
        reasons = "<br>".join(f"{i.code}: {i.message}" for i in r.blocking)
        out.append(f"| {r.doc_id} | {r.vendor_id or ''} | {d.get('invoice_number', '')} | {total} | {r.owner} | {reasons} |")
    out += ["", "## Posted to ERP", "", "| DocumentNo | Vendor | Gross |", "|---|---|---|"]
    out += [f"| {e['DocumentNo']} | {e['VendorAccount']} | {e['GrossAmount']:,.2f} |" for e in run.erp_records]
    return "\n".join(out) + "\n"
