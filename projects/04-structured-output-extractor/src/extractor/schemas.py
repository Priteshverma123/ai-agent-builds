"""The target shapes. Pydantic models are the contract: if data validates, downstream code can trust it."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


# Money is Decimal (never float: 0.1 + 0.2 != 0.3) normalised to whole cents.
Money = Annotated[Decimal, Field(ge=0, decimal_places=2), AfterValidator(lambda v: v.quantize(Decimal("0.01")))]


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit_price: Money


class Invoice(BaseModel):
    """An invoice found in an email or a PDF's text."""

    model_config = ConfigDict(extra="forbid")

    vendor: str = Field(min_length=1)
    invoice_number: str = Field(min_length=1)
    invoice_date: date
    due_date: date | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$", description="ISO 4217 code, e.g. USD")
    line_items: list[LineItem] = Field(min_length=1)
    tax: Money = Decimal("0.00")
    total: Money

    @model_validator(mode="after")
    def check_business_rules(self) -> Invoice:
        """Types aren't enough: the numbers must also add up."""
        expected = sum((item.quantity * item.unit_price for item in self.line_items), Decimal("0")) + self.tax
        if abs(expected - self.total) > Decimal("0.01"):
            raise ValueError(f"total {self.total} does not equal line items + tax = {expected}")
        if self.due_date and self.due_date < self.invoice_date:
            raise ValueError("due_date is before invoice_date")
        return self


class SupportTicket(BaseModel):
    """A customer support request found in an email."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(min_length=1)
    customer_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
    order_id: str | None = Field(default=None, pattern=r"^ORD-\d{5}$", description="Format ORD-12345")
    category: Literal["billing", "shipping", "technical", "other"]
    urgency: Literal["low", "medium", "high"]
    summary: str = Field(max_length=200, description="One sentence, at most 200 characters")


SCHEMAS: dict[str, type[BaseModel]] = {"invoice": Invoice, "ticket": SupportTicket}
