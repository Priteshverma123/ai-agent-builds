from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from extractor.extract import extract, parse_json
from extractor.llm import MockLLM
from extractor.schemas import Invoice, SupportTicket

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class Replay:
    """A fake model that returns fixed replies, to test the loop in isolation."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.seen: list[list[dict]] = []

    def complete(self, system, messages):
        self.seen.append(list(messages))
        return self.replies.pop(0)


def test_parse_json_digs_object_out_of_fences_and_chatter():
    assert parse_json('Sure!\n```json\n{"a": 1}\n```\nHope that helps') == {"a": 1}
    assert parse_json('Here you go: {"a": {"b": 2}} done') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_invoice_business_rule_catches_wrong_total():
    good = {
        "vendor": "V", "invoice_number": "1", "invoice_date": "2026-01-01", "currency": "USD",
        "line_items": [{"description": "x", "quantity": 2, "unit_price": 10}], "tax": 1, "total": 21,
    }
    assert Invoice.model_validate(good).total == Decimal("21.00")
    with pytest.raises(ValidationError, match="does not equal"):
        Invoice.model_validate({**good, "total": 25})


def test_mock_repairs_invoice_on_second_attempt():
    result = extract((EXAMPLES / "invoice_acme.txt").read_text(), Invoice, MockLLM())
    assert result.ok and len(result.attempts) == 2
    assert result.data.invoice_date == date(2026, 3, 3)
    assert result.data.total == Decimal("725.75")
    assert len(result.data.line_items) == 3


def test_mock_repairs_ticket_fields():
    result = extract((EXAMPLES / "email_late_order.txt").read_text(), SupportTicket, MockLLM())
    assert result.ok
    assert result.data.order_id == "ORD-48213"
    assert (result.data.category, result.data.urgency) == ("shipping", "high")


def test_unfixable_document_fails_after_max_attempts():
    result = extract((EXAMPLES / "invoice_bad_total.txt").read_text(), Invoice, MockLLM(), max_attempts=3)
    assert not result.ok and result.data is None
    assert len(result.attempts) == 3
    assert "does not equal" in result.attempts[-1].errors[0]


def test_repair_message_shows_the_model_its_errors():
    model = Replay(
        "not json at all",
        '{"customer_name": "A", "customer_email": "a@b.co", "category": "other", "urgency": "low", "summary": "hi"}',
    )
    result = extract("some email", SupportTicket, model)
    assert result.ok and len(result.attempts) == 2
    repair = model.seen[1][-1]["content"]
    assert "failed validation" in repair and "invalid JSON" in repair
    assert model.seen[1][-2] == {"role": "assistant", "content": "not json at all"}
