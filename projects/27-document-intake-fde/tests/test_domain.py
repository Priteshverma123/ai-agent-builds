from datetime import date

import pytest

from intake.config import Tolerances
from intake.domain.matching import three_way_match
from intake.domain.models import GoodsReceipt, Invoice, LineItem, PurchaseOrder, ReceiptLine, Vendor
from intake.domain.rules import RuleContext, validate_invoice
from intake.domain.vendors import VendorMaster, normalize_name

ACME = Vendor(vendor_id="V-001", name="Acme Industrial Supply Co.", aliases=["Acme Industrial"],
              tax_id="31-4455667", tax_rate=0.07, gl_code="5100")


def invoice(**overrides) -> Invoice:
    base = dict(invoice_number="A-1", vendor_name="Acme", invoice_date=date(2026, 10, 1), po_number="PO-1",
                lines=[LineItem(sku="BOLT", quantity=10, unit_price=12.5, amount=125.0)],
                subtotal=125.0, tax=8.75, total=133.75)
    return Invoice(**(base | overrides))


def ctx(**overrides) -> RuleContext:
    base = dict(vendor=ACME, today=date(2026, 10, 20), tolerances=Tolerances(), require_po=True,
                seen_invoice_keys=frozenset())
    return RuleContext(**(base | overrides))


def codes(issues) -> list[str]:
    return [i.code for i in issues]


def test_clean_invoice_passes_every_rule():
    assert validate_invoice(invoice(), ctx()) == []


@pytest.mark.parametrize("overrides, context, expected", [
    ({"lines": [LineItem(sku="BOLT", quantity=10, unit_price=12.5, amount=130.0)]}, {}, "LINE_MATH"),
    ({"subtotal": 120.0, "total": 128.75, "tax": 8.75}, {}, "SUBTOTAL_MISMATCH"),
    ({"total": 140.0}, {}, "TOTAL_MISMATCH"),
    ({"tax": 12.0, "total": 137.0}, {}, "TAX_MISMATCH"),
    ({"invoice_date": date(2026, 12, 1)}, {}, "DATE_INVALID"),
    ({"due_date": date(2026, 9, 1)}, {}, "DATE_INVALID"),
    ({}, {"vendor": None}, "UNKNOWN_VENDOR"),
    ({"currency": "EUR"}, {}, "CURRENCY_MISMATCH"),
    ({"po_number": ""}, {}, "MISSING_PO"),
    ({}, {"seen_invoice_keys": frozenset({("V-001", "A-1")})}, "DUPLICATE_INVOICE"),
])
def test_each_rule_fires(overrides, context, expected):
    assert expected in codes(validate_invoice(invoice(**overrides), ctx(**context)))


def test_missing_po_is_allowed_when_client_does_not_require_it():
    assert validate_invoice(invoice(po_number=None), ctx(require_po=False)) == []


PO = PurchaseOrder(po_number="PO-1", vendor_name="Acme", order_date=date(2026, 9, 1),
                   lines=[LineItem(sku="BOLT", quantity=10, unit_price=12.5, amount=125.0)])
GRN = GoodsReceipt(grn_number="G-1", po_number="PO-1", received_date=date(2026, 9, 5),
                   lines=[ReceiptLine(sku="BOLT", quantity_received=6), ReceiptLine(sku="BOLT", quantity_received=4)])


def match(inv, po=PO, receipts=(GRN,), po_vendor="V-001", inv_vendor="V-001"):
    return codes(three_way_match(inv, po, list(receipts), po_vendor, inv_vendor, price_pct=0.02))


def test_three_way_match_sums_partial_receipts():
    assert match(invoice()) == []


def test_price_within_tolerance_passes_and_outside_fails():
    near = invoice(lines=[LineItem(sku="BOLT", quantity=10, unit_price=12.7, amount=127.0)])
    far = invoice(lines=[LineItem(sku="BOLT", quantity=10, unit_price=13.5, amount=135.0)])
    assert match(near) == [] and match(far) == ["PRICE_VARIANCE"]


def test_quantity_checks_against_po_and_receipts():
    over = invoice(lines=[LineItem(sku="BOLT", quantity=12, unit_price=12.5, amount=150.0)])
    assert match(over) == ["QTY_EXCEEDS_PO", "QTY_EXCEEDS_RECEIVED"]


@pytest.mark.parametrize("kwargs, expected", [
    ({"po": None}, ["PO_NOT_FOUND"]),
    ({"receipts": ()}, ["NO_RECEIPT"]),
    ({"po_vendor": "V-999"}, ["PO_VENDOR_MISMATCH"]),
])
def test_match_structural_failures(kwargs, expected):
    assert match(invoice(), **kwargs) == expected


def test_line_not_on_po():
    extra = invoice(lines=[LineItem(sku="NUT", quantity=1, unit_price=1, amount=1)])
    assert "LINE_NOT_ON_PO" in match(extra)


def test_vendor_resolution_order():
    master = VendorMaster([ACME])
    assert master.resolve("anything", "31-4455667")[1] == "tax id"
    assert master.resolve("ACME INDUSTRIAL")[1] == "name"
    vendor, how = master.resolve("ACME INDUSTR1AL SUPPLY C0.")
    assert vendor is ACME and how.startswith("fuzzy")
    assert master.resolve("Shady Parts LLC") == (None, "no match")
    assert normalize_name("Acme Industrial Supply Co., Inc.") == "acme industrial supply"
