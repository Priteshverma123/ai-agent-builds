"""Business documents as pydantic schemas. Extraction output must validate against these."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DocType(str, Enum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    GOODS_RECEIPT = "goods_receipt"
    UNKNOWN = "unknown"


class LineItem(BaseModel):
    sku: str = Field(min_length=1)
    description: str = ""
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    amount: float = Field(ge=0)


class Invoice(BaseModel):
    invoice_number: str = Field(min_length=1)
    vendor_name: str = Field(min_length=1)
    vendor_tax_id: str | None = None
    invoice_date: date
    due_date: date | None = None
    po_number: str | None = None
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    lines: list[LineItem] = Field(min_length=1)
    subtotal: float
    tax: float
    total: float

    @field_validator("po_number")
    @classmethod
    def blank_po_is_none(cls, value: str | None) -> str | None:
        return value or None


class PurchaseOrder(BaseModel):
    po_number: str = Field(min_length=1)
    vendor_name: str = Field(min_length=1)
    order_date: date
    currency: str = "USD"
    lines: list[LineItem] = Field(min_length=1)


class ReceiptLine(BaseModel):
    sku: str
    quantity_received: float = Field(ge=0)


class GoodsReceipt(BaseModel):
    grn_number: str = Field(min_length=1)
    po_number: str = Field(min_length=1)
    received_date: date
    lines: list[ReceiptLine] = Field(min_length=1)


SCHEMAS: dict[DocType, type[BaseModel]] = {
    DocType.INVOICE: Invoice,
    DocType.PURCHASE_ORDER: PurchaseOrder,
    DocType.GOODS_RECEIPT: GoodsReceipt,
}


class Vendor(BaseModel):
    vendor_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    tax_id: str | None = None
    currency: str = "USD"
    tax_rate: float
    gl_code: str


class Severity(str, Enum):
    ERROR = "error"      # blocks posting; goes to the exceptions queue
    WARNING = "warning"  # recorded in the report; does not block


class Issue(BaseModel):
    code: str
    message: str
    severity: Severity = Severity.ERROR


class Status(str, Enum):
    APPROVED = "approved"      # posted to the ERP
    EXCEPTION = "exception"    # waiting for a person
    REFERENCE = "reference"    # PO / goods receipt kept for matching


class StageEvent(BaseModel):
    stage: str
    detail: str
    ok: bool = True


class DocumentResult(BaseModel):
    doc_id: str
    doc_type: DocType = DocType.UNKNOWN
    classification_confidence: float = 0.0
    extraction_confidence: float = 0.0
    data: dict | None = None             # validated document as JSON-ready dict
    vendor_id: str | None = None
    issues: list[Issue] = Field(default_factory=list)
    status: Status = Status.EXCEPTION
    owner: str | None = None             # who should fix the exception
    trace: list[StageEvent] = Field(default_factory=list)

    def log(self, stage: str, detail: str, ok: bool = True) -> None:
        self.trace.append(StageEvent(stage=stage, detail=detail, ok=ok))

    @property
    def blocking(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]
