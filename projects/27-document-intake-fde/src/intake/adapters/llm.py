"""LLM port for classification and extraction, plus a deterministic rule-based MockLLM.

The MockLLM plays the role of "the model reading a scanned document": keyword voting for the
document type and label-driven regexes for fields. It returns raw strings exactly as printed
(e.g. US dates); normalising them is the pipeline's job, driven by client config.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

LABELS = ["invoice", "purchase_order", "goods_receipt"]

KEYWORDS: dict[str, list[str]] = {
    "invoice": ["invoice", "total due", "amount due", "bill to", "remit to", "payment due"],
    "purchase_order": ["purchase order", "order total", "ship to", "order date"],
    "goods_receipt": ["goods received", "received by", "qty received", "receiving"],
}

M = re.IGNORECASE | re.MULTILINE
MONEY = r"([\d,]+\.\d{2})"
PATTERNS: dict[str, dict[str, re.Pattern[str]]] = {
    "invoice": {
        "invoice_number": re.compile(r"^\s*invoice[ \t]*(?:no\.?|number|#)[ \t]*[:#]?[ \t]*#?([A-Z0-9][A-Z0-9-]+)", M),
        "vendor_tax_id": re.compile(r"^\s*tax id[ \t]*:[ \t]*([\d-]+)", M),
        "invoice_date": re.compile(r"^\s*(?:invoice date|date)[ \t]*:[ \t]*(\S+)", M),
        "due_date": re.compile(r"^\s*(?:due date|payment due)[ \t]*:[ \t]*(\S+)", M),
        "po_number": re.compile(r"^\s*(?:po number|your po|po #)[ \t]*:[ \t]*(PO-\d+)", M),
        "subtotal": re.compile(r"^\s*subtotal[ \t]*:[ \t]*" + MONEY, M),
        "tax": re.compile(r"^\s*(?:sales[ \t]+)?tax\b[^:\n]*:[ \t]*" + MONEY, M),
        "currency": re.compile(r"^\s*(?:total due|amount due|total)[ \t]*:[ \t]*([A-Z]{3})\b", M),
        "total": re.compile(r"^\s*(?:total due|amount due|total)[ \t]*:[ \t]*(?:[A-Z]{3}[ \t]*)?" + MONEY, M),
    },
    "purchase_order": {
        "po_number": re.compile(r"^\s*po number[ \t]*:[ \t]*(\S+)", M),
        "vendor_name": re.compile(r"^\s*vendor[ \t]*:[ \t]*(.+?)\s*$", M),
        "order_date": re.compile(r"^\s*order date[ \t]*:[ \t]*(\S+)", M),
        "currency": re.compile(r"^\s*currency[ \t]*:[ \t]*([A-Z]{3})", M),
    },
    "goods_receipt": {
        "grn_number": re.compile(r"^\s*grn no[ \t]*:[ \t]*(\S+)", M),
        "po_number": re.compile(r"^\s*po number[ \t]*:[ \t]*(\S+)", M),
        "received_date": re.compile(r"^\s*received date[ \t]*:[ \t]*(\S+)", M),
    },
}
PRICED_LINE = re.compile(r"^([A-Z][A-Z0-9-]+)[ \t]{2,}(.+?)[ \t]{2,}(\d+(?:\.\d+)?)[ \t]+" + MONEY + r"[ \t]+" + MONEY + r"[ \t]*$", re.M)
RECEIPT_LINE = re.compile(r"^([A-Z][A-Z0-9-]+)[ \t]{2,}(\d+(?:\.\d+)?)[ \t]{2,}\w+[ \t]*$", re.M)


class LLM(Protocol):
    name: str

    def classify(self, text: str, labels: list[str]) -> dict[str, Any]:
        """Return {"label": str, "confidence": float, "rationale": str}."""

    def extract(self, text: str, doc_type: str, schema: dict[str, Any], feedback: str | None = None) -> dict[str, Any]:
        """Return a JSON object shaped like `schema`. `feedback` carries validation errors on a retry."""


def money(value: str) -> float:
    return float(value.replace(",", ""))


class MockLLM:
    name = "mock"

    def classify(self, text: str, labels: list[str]) -> dict[str, Any]:
        lower = text.lower()
        votes = {label: [k for k in KEYWORDS[label] if k in lower] for label in labels}
        total = sum(len(v) for v in votes.values())
        best = max(labels, key=lambda label: len(votes[label]))
        if total == 0:
            return {"label": "unknown", "confidence": 0.0, "rationale": "no document keywords"}
        return {"label": best, "confidence": round(len(votes[best]) / total, 2),
                "rationale": "keywords: " + ", ".join(votes[best])}

    def extract(self, text: str, doc_type: str, schema: dict[str, Any], feedback: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field, pattern in PATTERNS[doc_type].items():
            if match := pattern.search(text):
                out[field] = money(match.group(1)) if field in ("subtotal", "tax", "total") else match.group(1)
        if doc_type == "invoice":
            out["vendor_name"] = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if doc_type == "goods_receipt":
            out["lines"] = [{"sku": s, "quantity_received": float(q)} for s, q in RECEIPT_LINE.findall(text)]
        else:
            out["lines"] = [{"sku": s, "description": d.strip(), "quantity": float(q),
                             "unit_price": money(p), "amount": money(a)}
                            for s, d, q, p, a in PRICED_LINE.findall(text)]
        return out
