"""Two specialist agents. Each is just a card + a handler; ``create_agent_app`` adds the protocol.

They are deterministic on purpose (lookup tables, not LLM calls) so the protocol is what you
watch. In a real system each one could be a full LLM agent built by a different team.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI

from .models import AgentCard, AgentSkill, Artifact, DataPart, Task, TaskState, TextPart
from .server import Reply, create_agent_app

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
AMBIGUOUS = {"dollar": ["USD", "CAD", "AUD"], "dollars": ["USD", "CAD", "AUD"]}
NAMES = {"yen": "JPY", "euro": "EUR", "euros": "EUR", "pound": "GBP", "pounds": "GBP", "rupees": "INR"}


def _user_text(task: Task) -> str:
    """Everything the caller has said on this task so far (multi-turn: later answers count too)."""
    return " ".join(m.text for m in task.history if m.role == "user")


# ---- currency agent ----------------------------------------------------------------------
def currency_card(url: str) -> AgentCard:
    return AgentCard(
        name="FX Desk",
        description="Converts amounts between currencies using the desk's daily rates.",
        url=url,
        skills=[AgentSkill(id="convert_currency", name="Convert currency",
                           description="Convert an amount from one currency to another.",
                           tags=["currency", "money", "exchange", "budget"],
                           examples=["Convert 500 USD to EUR", "How much is 20000 yen in pounds?"])],
    )


def currency_handler(rates: dict[str, float]):
    def handle(task: Task) -> Reply:
        text = _user_text(task)
        words = re.findall(r"[A-Za-z]+", text)
        code_of = {w: w.upper() if w.upper() in rates else NAMES.get(w.lower()) for w in words}
        # The target is the currency right after "to"/"in"/"into"; the source is any other one.
        target = next((code_of[b] for a, b in zip(words, words[1:]) if a.lower() in ("to", "in", "into") and code_of[b]), None)
        source = next((code_of[w] for w in words if code_of[w] and code_of[w] != target), None)
        amount = re.search(r"(\d[\d,]*(?:\.\d+)?)", text)
        ambiguous = next((w for w in words if w.lower() in AMBIGUOUS), None)
        if ambiguous and source is None:
            options = AMBIGUOUS[ambiguous.lower()]
            return Reply(TaskState.input_required, f"Which {ambiguous} do you mean: {', '.join(options)}?")
        if amount is None:
            return Reply(TaskState.input_required, "How much money should I convert?")
        if source is None or target is None:
            return Reply(TaskState.input_required, "Which two currencies? For example: 500 USD to EUR.")
        value = float(amount.group(1).replace(",", ""))
        result = round(value / rates[source] * rates[target], 2)
        data = {"amount": value, "from": source, "to": target, "result": result,
                "rate": round(rates[target] / rates[source], 4)}
        return Reply(TaskState.completed, f"{value:,.0f} {source} = {result:,.0f} {target}",
                     [Artifact(name="conversion", parts=[DataPart(data=data)])])

    return handle


# ---- weather agent -----------------------------------------------------------------------
def weather_card(url: str) -> AgentCard:
    return AgentCard(
        name="Packing Weather",
        description="Typical weather for a city and month, with a packing list.",
        url=url,
        skills=[AgentSkill(id="packing_forecast", name="Packing forecast",
                           description="Typical temperatures and rain for a city in a given month, plus what to pack.",
                           tags=["weather", "climate", "packing", "travel"],
                           examples=["What should I pack for Lisbon in July?"])],
    )


def packing_list(high: int, low: int, rain_days: int) -> list[str]:
    items = ["comfortable walking shoes"]
    items += ["t-shirts", "sunscreen"] if high >= 25 else ["light layers"]
    if low <= 10:
        items.append("a warm jacket")
    if rain_days >= 8:
        items.append("a compact umbrella")
    return items


def weather_handler(climate: dict[str, dict[str, list[int]]]):
    def handle(task: Task) -> Reply:
        text = _user_text(task)
        city = next((c for c in climate if c.lower() in text.lower()), None)
        month = next((m for m in MONTHS if m.lower() in text.lower()), None)
        if city is None:
            return Reply(TaskState.failed, f"I only have data for: {', '.join(climate)}.")
        if month is None or month not in climate[city]:
            return Reply(TaskState.input_required, f"Which month are you travelling to {city}?")
        high, low, rain = climate[city][month]
        data = {"city": city, "month": month, "high_c": high, "low_c": low, "rain_days": rain,
                "pack": packing_list(high, low, rain)}
        summary = f"{city} in {month}: {high}C / {low}C, about {rain} rainy day{'s' if rain != 1 else ''}. Pack: {', '.join(data['pack'])}."
        return Reply(TaskState.completed, summary,
                     [Artifact(name="forecast", parts=[TextPart(text=summary), DataPart(data=data)])])

    return handle


def _load(name: str) -> dict:
    return {k: v for k, v in json.loads((EXAMPLES / name).read_text(encoding="utf-8")).items() if not k.startswith("_")}


def build_currency_agent(url: str) -> FastAPI:
    return create_agent_app(currency_card(url), currency_handler(_load("rates.json")))


def build_weather_agent(url: str, work_seconds: float = 0.4) -> FastAPI:
    return create_agent_app(weather_card(url), weather_handler(_load("climate.json")), work_seconds=work_seconds)
