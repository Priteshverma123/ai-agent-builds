"""Three-way match: what we were billed vs what we ordered (PO) vs what we received (GRN).

  invoice qty  <= received qty   (don't pay for goods that never arrived)
  invoice qty  <= ordered qty    (don't pay for more than we asked for)
  invoice price ~= PO price      (within the client's tolerance)
"""

from __future__ import annotations

from collections import defaultdict

from .models import GoodsReceipt, Invoice, Issue, PurchaseOrder


def received_quantities(receipts: list[GoodsReceipt]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for grn in receipts:
        for line in grn.lines:
            totals[line.sku] += line.quantity_received
    return dict(totals)


def three_way_match(inv: Invoice, po: PurchaseOrder | None, receipts: list[GoodsReceipt],
                    po_vendor_id: str | None, inv_vendor_id: str | None, price_pct: float) -> list[Issue]:
    if not inv.po_number:
        return []  # MISSING_PO is reported by the validation rules
    if po is None:
        return [Issue(code="PO_NOT_FOUND", message=f"{inv.po_number} is not an open purchase order")]
    issues: list[Issue] = []
    if po_vendor_id != inv_vendor_id:
        issues.append(Issue(code="PO_VENDOR_MISMATCH", message=f"{po.po_number} was issued to another vendor"))
    if not receipts:
        issues.append(Issue(code="NO_RECEIPT", message=f"nothing has been received against {po.po_number}"))
    ordered = {l.sku: l for l in po.lines}
    received = received_quantities(receipts)
    for line in inv.lines:
        po_line = ordered.get(line.sku)
        if po_line is None:
            issues.append(Issue(code="LINE_NOT_ON_PO", message=f"{line.sku} is not on {po.po_number}"))
            continue
        if po_line.unit_price and abs(line.unit_price - po_line.unit_price) / po_line.unit_price > price_pct:
            change = (line.unit_price - po_line.unit_price) / po_line.unit_price
            issues.append(Issue(code="PRICE_VARIANCE",
                                message=f"{line.sku}: billed {line.unit_price:.2f} vs PO {po_line.unit_price:.2f} ({change:+.1%})"))
        if line.quantity > po_line.quantity:
            issues.append(Issue(code="QTY_EXCEEDS_PO",
                                message=f"{line.sku}: billed {line.quantity:g} > ordered {po_line.quantity:g}"))
        if receipts and line.quantity > received.get(line.sku, 0):
            issues.append(Issue(code="QTY_EXCEEDS_RECEIVED",
                                message=f"{line.sku}: billed {line.quantity:g} > received {received.get(line.sku, 0):g}"))
    return issues
