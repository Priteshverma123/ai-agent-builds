"""LLM adapters.

Every component talks to a model through one tiny interface, ``complete(system, prompt) -> str``.
The default is :class:`MockSQLWriter`, a deterministic rule-based "model" so the demo and the tests
run offline. Set ``LLM_PROVIDER=anthropic`` or ``LLM_PROVIDER=openai`` to use a real model; the
rest of the agent (guard, executor, repair loop) is identical either way.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import load_settings

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}


class LLM(Protocol):
    """Anything that turns a system prompt and a user prompt into text."""

    name: str

    def complete(self, system: str, prompt: str) -> str: ...


class ProviderLLM:
    """A real model behind the same interface. SDKs are imported lazily so they stay optional."""

    def __init__(self, provider: str, model: str | None = None) -> None:
        if provider not in DEFAULT_MODELS:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got {provider!r}")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        self.name = f"{provider}:{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        if self.provider == "anthropic":
            import anthropic  # pip install anthropic

            response = anthropic.Anthropic().messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(block.text for block in response.content if block.type == "text")
        from openai import OpenAI  # pip install openai

        response = OpenAI().chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


def llm_from_env(default: LLM) -> LLM:
    """Return a real provider if ``LLM_PROVIDER`` asks for one, otherwise the offline default."""
    settings = load_settings()
    if settings.llm_provider == "mock":
        return default
    return ProviderLLM(settings.llm_provider, settings.llm_model)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (models love to wrap JSON in prose)."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model reply: {text[:80]!r}")
    return json.loads(match.group(0))


# --------------------------------------------------------------------------- the offline model

_TOP_PRODUCTS = """
SELECT p.name AS product, SUM(oi.quantity * oi.unit_price) AS revenue
FROM order_items oi
JOIN products p ON p.id = oi.product_id
JOIN orders o ON o.id = oi.order_id
WHERE o.status = 'paid'
GROUP BY p.name
ORDER BY revenue DESC
LIMIT {n}
"""

_MONTHLY = """
SELECT strftime('%Y-%m', o.order_date) AS month, SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
WHERE o.status = 'paid'
GROUP BY month
ORDER BY month
"""

# The first draft makes a classic mistake: it assumes orders has a `total` column.
_AOV_BROKEN = """
SELECT c.country, ROUND(AVG(o.total), 2) AS avg_order_value
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'paid'
GROUP BY c.country
ORDER BY avg_order_value DESC
"""

_AOV_FIXED = """
WITH order_totals AS (
    SELECT o.id, c.country, SUM(oi.quantity * oi.unit_price) AS total
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    JOIN order_items oi ON oi.order_id = o.id
    WHERE o.status = 'paid'
    GROUP BY o.id, c.country
)
SELECT country, ROUND(AVG(total), 2) AS avg_order_value
FROM order_totals
GROUP BY country
ORDER BY avg_order_value DESC
"""

_CUSTOMER_COUNT = "SELECT COUNT(*) AS customers FROM customers"

_DELETE_REFUNDED = "DELETE FROM orders WHERE status = 'refunded'"


class MockSQLWriter:
    """A rule-based stand-in for an LLM that writes SQL.

    It reads the ``QUESTION:`` line of the prompt, matches a few intents, and replies with the same
    JSON shape we ask real models for. If the prompt contains ``PREVIOUS ATTEMPT FAILED`` it returns
    the corrected query, which lets the demo show the self-repair loop without any network.
    """

    name = "mock-sql-writer"

    def complete(self, system: str, prompt: str) -> str:
        question = _field(prompt, "QUESTION").lower()
        repairing = "PREVIOUS ATTEMPT FAILED" in prompt
        sql, why = self._route(question, repairing)
        return json.dumps({"sql": sql.strip(), "rationale": why})

    @staticmethod
    def _route(q: str, repairing: bool) -> tuple[str, str]:
        if re.search(r"\b(delete|remove|drop|clean up|update|insert)\b", q):
            return _DELETE_REFUNDED, "The user asked to remove refunded orders."
        if "product" in q and ("revenue" in q or "most" in q or "best" in q):
            n = re.search(r"\b(\d+)\b", q)
            return _TOP_PRODUCTS.format(n=n.group(1) if n else 5), "Rank products by paid revenue."
        if "month" in q:
            return _MONTHLY, "Group paid revenue by calendar month."
        if "average order" in q or "aov" in q:
            if repairing:
                return _AOV_FIXED, "orders has no total column; compute totals from order_items first."
            return _AOV_BROKEN, "Average the order total per country."
        if "how many customers" in q or "number of customers" in q:
            return _CUSTOMER_COUNT, "Count rows in customers."
        return "", "I can't map this question to the schema."


def _field(prompt: str, label: str) -> str:
    """Read a ``LABEL: value`` line from a prompt."""
    match = re.search(rf"^{label}:\s*(.+)$", prompt, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""
