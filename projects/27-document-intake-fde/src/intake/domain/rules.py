"""Validation rules for a single invoice. Pure functions: (invoice, context) -> list of issues.

Each rule is small and named so a customer can read the list and say "yes, that's our AP policy".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from ..config import Tolerances
from .models import Invoice, Issue, Severity, Vendor


@dataclass(frozen=True)
class RuleContext:
    vendor: Vendor | None
    today: date
    tolerances: Tolerances
    require_po: bool
    seen_invoice_keys: frozenset[tuple[str, str]]  # (vendor_id, invoice_number) already posted


Rule = Callable[[Invoice, RuleContext], list[Issue]]


def line_math(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    return [Issue(code="LINE_MATH", message=f"{l.sku}: {l.quantity} x {l.unit_price:.2f} != {l.amount:.2f}")
            for l in inv.lines if abs(l.quantity * l.unit_price - l.amount) > ctx.tolerances.amount_abs]


def subtotal_matches_lines(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    lines = round(sum(l.amount for l in inv.lines), 2)
    if abs(lines - inv.subtotal) > ctx.tolerances.amount_abs:
        return [Issue(code="SUBTOTAL_MISMATCH", message=f"lines sum to {lines:.2f}, subtotal says {inv.subtotal:.2f}")]
    return []


def total_matches(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    expected = round(inv.subtotal + inv.tax, 2)
    if abs(expected - inv.total) > ctx.tolerances.amount_abs:
        return [Issue(code="TOTAL_MISMATCH",
                      message=f"subtotal {inv.subtotal:.2f} + tax {inv.tax:.2f} = {expected:.2f}, invoice says {inv.total:.2f}")]
    return []


def tax_rate(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    if ctx.vendor is None:
        return []
    expected = round(inv.subtotal * ctx.vendor.tax_rate, 2)
    if abs(expected - inv.tax) > ctx.tolerances.tax_abs:
        return [Issue(code="TAX_MISMATCH",
                      message=f"tax {inv.tax:.2f} != {ctx.vendor.tax_rate:.2%} of {inv.subtotal:.2f} ({expected:.2f})")]
    return []


def dates(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    issues = []
    if inv.invoice_date > ctx.today:
        issues.append(Issue(code="DATE_INVALID", message=f"invoice dated {inv.invoice_date} is in the future"))
    if inv.due_date and inv.due_date < inv.invoice_date:
        issues.append(Issue(code="DATE_INVALID", message=f"due {inv.due_date} is before invoice date {inv.invoice_date}"))
    if (ctx.today - inv.invoice_date).days > 365:
        issues.append(Issue(code="STALE_INVOICE", message="invoice is more than a year old", severity=Severity.WARNING))
    return issues


def known_vendor(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    if ctx.vendor is None:
        return [Issue(code="UNKNOWN_VENDOR", message=f"{inv.vendor_name!r} is not in the vendor master")]
    if inv.currency != ctx.vendor.currency:
        return [Issue(code="CURRENCY_MISMATCH", message=f"{inv.currency} but vendor bills in {ctx.vendor.currency}")]
    return []


def has_po(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    if ctx.require_po and not inv.po_number:
        return [Issue(code="MISSING_PO", message="no PO number; client policy is 'no PO, no pay'")]
    return []


def not_duplicate(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    if ctx.vendor and (ctx.vendor.vendor_id, inv.invoice_number) in ctx.seen_invoice_keys:
        return [Issue(code="DUPLICATE_INVOICE", message=f"{inv.invoice_number} was already posted for {ctx.vendor.vendor_id}")]
    return []


RULES: list[Rule] = [line_math, subtotal_matches_lines, total_matches, tax_rate, dates, known_vendor,
                     has_po, not_duplicate]


def validate_invoice(inv: Invoice, ctx: RuleContext) -> list[Issue]:
    return [issue for rule in RULES for issue in rule(inv, ctx)]
