"""LLM backends: complete(system, messages) -> str. MockLLM is the offline default."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Protocol

from .config import DEFAULT_MODELS, Settings

ChatMessage = dict[str, str]


class LLM(Protocol):
    def complete(self, system: str, messages: list[ChatMessage]) -> str: ...


# --- The offline mock ------------------------------------------------------------

_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y")


def _find(pattern: str, text: str, default: str | None = None) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else default


def _iso_date(value: str | None) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value or "", fmt).date().isoformat()
        except ValueError:
            continue
    return value


def _number(value: str) -> float:
    return float(value.replace("$", "").replace(",", ""))


def _invoice(text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (first-draft, corrected) versions of the same extraction."""
    items = re.findall(r"^\s*[-*]\s*(\d+)\s*x\s*(.+?)\s*@\s*\$?([\d,]+\.\d{2})", text, re.MULTILINE)
    raw_date = _find(r"^(?:Invoice )?Date:\s*(.+)$", text)
    raw_due = _find(r"^Due(?: date)?:\s*(.+)$", text)
    raw_total = _find(r"^\s*Total(?: due)?:\s*(\$?[\d,]+\.\d{2})", text, "0")
    common = {
        "vendor": _find(r"^From:\s*([^<\n]+?)\s*(?:<|$)", text, ""),
        "invoice_number": _find(r"Invoice\s*(?:#|No\.?|number)\s*:?\s*([A-Z0-9-]+)", text, ""),
        "currency": _find(r"\b(USD|EUR|GBP|INR)\b", text, "USD"),
        "line_items": [{"description": d, "quantity": int(q), "unit_price": _number(p)} for q, d, p in items],
        "tax": _number(_find(r"^\s*Tax[^:\n]*:\s*\$?([\d,]+\.\d{2})", text, "0") or "0"),
    }
    draft = {**common, "invoice_date": raw_date, "due_date": raw_due, "total": raw_total}
    fixed = {**common, "invoice_date": _iso_date(raw_date), "due_date": _iso_date(raw_due), "total": _number(raw_total or "0")}
    return draft, fixed


def _ticket(text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    body = " ".join(text.split("\n\n", 1)[-1].split())
    lowered = body.lower()
    categories = {
        "shipping": ("deliver", "shipped", "package", "arrive", "tracking"),
        "billing": ("charge", "refund", "invoice", "payment"),
        "technical": ("error", "crash", "login", "bug"),
    }
    category = next((c for c, words in categories.items() if any(w in lowered for w in words)), "other")
    urgency = "high" if re.search(r"urgent|asap|immediately|today", lowered) else "medium"
    order = _find(r"order\s*(?:number\s*)?#\s?(\d{5})", text)
    common = {
        "customer_name": _find(r"^From:\s*([^<\n]+?)\s*<", text, ""),
        "customer_email": _find(r"([\w.+-]+@[\w-]+\.[\w.]+)", text, ""),
        "category": category,
        "urgency": urgency,
    }
    first_sentence = re.split(r"(?<=[.!?])\s", body)[0][:200]
    draft = {**common, "order_id": f"#{order}" if order else None, "summary": body}
    fixed = {**common, "order_id": f"ORD-{order}" if order else None, "summary": first_sentence}
    return draft, fixed


class MockLLM:
    """Simulates a capable but sloppy model, deterministically.

    Its first draft makes the mistakes real models make: JSON wrapped in a chatty code fence,
    dates copied as written ("March 3, 2026"), money as "$1,234.50" strings, IDs as written.
    Shown validation errors, it fixes exactly the fields the errors name, like a real model would.
    It cannot fix data that is wrong in the source document itself.
    """

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        source = messages[0]["content"].split("\n\n", 1)[-1]  # drop the "Extract a ..." instruction line
        if '"title": "Invoice"' in system:
            draft, fixed = _invoice(source)
        elif '"title": "SupportTicket"' in system:
            draft, fixed = _ticket(source)
        else:
            return "{}"

        feedback = " ".join(m["content"] for m in messages[1:] if m["role"] == "user")
        if not feedback:
            return f"Sure! Here's the extracted data:\n```json\n{json.dumps(draft, indent=2)}\n```"
        repaired = {key: fixed[key] if key in feedback else value for key, value in draft.items()}
        return json.dumps(repaired, indent=2)


# --- Real providers (optional) ---------------------------------------------------


class AnthropicLLM:
    """Claude via the official SDK: `pip install anthropic`, set ANTHROPIC_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or DEFAULT_MODELS["anthropic"]

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=messages,
            betas=["server-side-fallback-2026-07-01"],  # retry on a fallback model if a classifier declines
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal":
            return "[the model declined to answer]"
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAILLM:
    """OpenAI via the official SDK: `pip install openai`, set OPENAI_API_KEY."""

    def __init__(self, model: str | None = None) -> None:
        import openai

        self.client = openai.OpenAI()
        self.model = model or DEFAULT_MODELS["openai"]

    def complete(self, system: str, messages: list[ChatMessage]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
        )
        return response.choices[0].message.content or ""


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a backend from settings (env LLM_PROVIDER: mock | anthropic | openai). Default: mock."""
    settings = settings or Settings.from_env()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.model_for("anthropic"))
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.model_for("openai"))
    return MockLLM()
