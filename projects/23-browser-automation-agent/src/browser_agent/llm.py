"""LLM clients with tool calling. ``MockLLM`` is deterministic and used by default and in tests.

Interface (same as project 09):
    start(system, task, tools)        the task contains the goal and the first snapshot
    next_turn(results) -> Turn        results carry "OK/ERROR: message" + the new snapshot
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import DEFAULT_MODELS, Settings, load_settings

ELEMENT = re.compile(r'^\s*- (\w+)(?: "([^"]*)")?((?: \[[^\]]*\])*)(?:: (.*))?$')


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    text: str
    is_error: bool


@dataclass
class Turn:
    thought: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    answer: str | None = None


class LLM(Protocol):
    name: str

    def start(self, system: str, task: str, tools: list[dict[str, Any]]) -> None: ...

    def next_turn(self, results: list[ToolResult]) -> Turn: ...


@dataclass
class Element:
    role: str
    name: str
    ref: str | None
    props: list[str]
    value: str


def parse_snapshot(snapshot: str) -> list[Element]:
    """Read the snapshot *text* back into elements, exactly what a model has to work with."""
    elements = []
    for line in snapshot.splitlines():
        match = ELEMENT.match(line)
        if not match:
            continue
        role, name, props, value = match.groups()
        props_list = re.findall(r"\[([^\]]*)\]", props or "")
        ref = next((p[4:] for p in props_list if p.startswith("ref=")), None)
        if role == "text":
            name, value = (value or ""), ""
        elements.append(Element(role, name or "", ref, props_list, (value or "").rstrip(":")))
    return elements


class MockLLM:
    """A scripted shopper. It only reads the snapshot text, never the DOM, just like a real model.

    Goal format: "Buy <qty> <product>s with <standard|express> shipping for <name> (<email>)".
    """

    name = "mock"
    GOAL = re.compile(r"Buy (\d+) (.+?)s? with (\w+) shipping for (.+?) \((.+?)\)", re.IGNORECASE)

    def start(self, system: str, task: str, tools: list[dict[str, Any]]) -> None:
        goal = self.GOAL.search(task)
        if goal is None:
            raise ValueError(f"MockLLM cannot parse the goal: {task.splitlines()[0]}")
        self.qty, self.product, self.shipping, self.customer, self.email = goal.groups()
        self.snapshot = task.split("Current page:\n", 1)[1]
        self.subtotal = 0.0
        self.expected_total: str | None = None
        self._calls = 0

    def _call(self, thought: str, tool: str, **args: Any) -> Turn:
        self._calls += 1
        return Turn(thought=thought, tool_calls=[ToolCall(f"call_{self._calls}", tool, args)])

    def next_turn(self, results: list[ToolResult]) -> Turn:
        if results:
            self.snapshot = results[-1].text.split("\n\n", 1)[1]
        elements = parse_snapshot(self.snapshot)
        page = self.snapshot.splitlines()[0]

        def find(role: str, name: str) -> Element | None:
            return next((e for e in elements if e.role == role and name.lower() in e.name.lower()), None)

        def text(contains: str) -> str | None:
            return next((e.name for e in elements if e.role == "text" and contains.lower() in e.name.lower()), None)

        if dialog := re.search(r'- dialog "(.+?)"', self.snapshot):
            amount = re.search(r"\$([\d.]+)", dialog.group(1))
            ok = amount is not None and amount.group(1) == self.expected_total
            return self._call(f"Dialog says '{dialog.group(1)}'. I expect ${self.expected_total} (cart + shipping): "
                              f"{'matches, confirm' if ok else 'MISMATCH, cancel'}.", "handle_dialog", accept=ok)
        if find("heading", "Order confirmed"):
            receipt = text("Order A") or "Order placed."
            return self._call("The confirmation page is showing. Report back.", "finish", answer=receipt)
        if page.startswith("Page: Checkout"):
            return self._checkout(find, text)
        if page.startswith("Page: Cart"):
            if subtotal := text("Subtotal"):
                self.subtotal = float(re.search(r"\$([\d.]+)", subtotal).group(1))
            link = find("link", "checkout")
            if link:
                return self._call(f"Cart shows {subtotal}. Go to checkout.", "click", ref=link.ref, element=link.name)
            return self._call("The cart is empty, so the add-to-cart did not work.", "finish",
                              answer="Could not add the item to the cart.")
        if any(e.role == "heading" and e.name.lower() == self.product.lower() for e in elements):
            quantity, add = find("combobox", "Quantity"), find("button", "Add to cart")
            if add and "disabled" in add.props:
                return self._call("'Add to cart' is disabled: out of stock.", "finish",
                                  answer=f"{self.product} is out of stock.")
            if quantity and quantity.value != self.qty:
                return self._call(f"Quantity is {quantity.value}; I need {self.qty}.", "select_option",
                                  ref=quantity.ref, option=self.qty)
            return self._call("Quantity is right. Add to cart.", "click", ref=add.ref, element=add.name)
        if page.startswith("Page: Search results"):
            if link := find("link", self.product):
                return self._call(f"Found a link '{link.name}' [{link.ref}]. Open it.", "click", ref=link.ref,
                                  element=link.name)
            return self._call("No matching product.", "finish", answer=f"The shop has no '{self.product}'.")
        if search := find("searchbox", ""):
            return self._call(f"I see a searchbox '{search.name}' [{search.ref}]. Search for the product.",
                              "type", ref=search.ref, text=self.product.lower(), submit=True)
        return self._call("I'm lost. Start from the home page.", "navigate", url="/index.html")

    def _checkout(self, find, text) -> Turn:
        name, email = find("textbox", "Full name"), find("textbox", "Email")
        shipping, terms = find("combobox", "Shipping"), find("checkbox", "terms")
        problem = text("accept the terms")
        if problem and terms and "unchecked" in terms.props:
            return self._call(f"The page shows an error: '{problem}'. Tick the box.", "check", ref=terms.ref)
        if name.value != self.customer:
            return self._call("Fill in the name.", "type", ref=name.ref, text=self.customer)
        if email.value != self.email:
            return self._call("Fill in the email.", "type", ref=email.ref, text=self.email)
        if not shipping.value.lower().startswith(self.shipping.lower()):
            return self._call(f"Choose {self.shipping} shipping.", "select_option", ref=shipping.ref, option=self.shipping)
        button = find("button", "Place order")
        fee = re.search(r"\$([\d.]+)", shipping.value)  # "Express ($9.00)" adds a fee, "Standard (free)" does not
        self.expected_total = f"{self.subtotal + (float(fee.group(1)) if fee else 0):.2f}"
        note = " (retrying after the error)" if "- alert" in self.snapshot else ""
        return self._call(f"Form looks complete{note}. Place the order.", "click", ref=button.ref, element=button.name)


class AnthropicLLM:
    def __init__(self, model: str | None = None) -> None:
        import anthropic  # optional dependency: pip install anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or DEFAULT_MODELS["anthropic"]
        self.name = f"anthropic:{self.model}"

    def start(self, system: str, task: str, tools: list[dict[str, Any]]) -> None:
        self.system, self.tools = system, tools
        self.messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

    def next_turn(self, results: list[ToolResult]) -> Turn:
        if results:
            self.messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r.call_id, "content": r.text, "is_error": r.is_error}
                for r in results]})
        response = self.client.messages.create(
            model=self.model, max_tokens=16000, system=self.system, tools=self.tools, messages=self.messages)
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        self.messages.append({"role": "assistant", "content": response.content})
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, b.input) for b in response.content if b.type == "tool_use"]
        return Turn(thought=text, tool_calls=calls) if calls else Turn(answer=text)


class OpenAILLM:
    def __init__(self, model: str | None = None) -> None:
        import openai  # optional dependency: pip install openai

        self.client = openai.OpenAI()  # reads OPENAI_API_KEY
        self.model = model or DEFAULT_MODELS["openai"]
        self.name = f"openai:{self.model}"

    def start(self, system: str, task: str, tools: list[dict[str, Any]]) -> None:
        self.tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                         "parameters": t["input_schema"]}} for t in tools]
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": task}]

    def next_turn(self, results: list[ToolResult]) -> Turn:
        self.messages += [{"role": "tool", "tool_call_id": r.call_id, "content": r.text} for r in results]
        message = self.client.chat.completions.create(
            model=self.model, messages=self.messages, tools=self.tools).choices[0].message
        self.messages.append(message.model_dump(exclude_none=True))
        calls = [ToolCall(c.id, c.function.name, json.loads(c.function.arguments or "{}"))
                 for c in message.tool_calls or []]
        return Turn(thought=message.content or "", tool_calls=calls) if calls else Turn(answer=message.content or "")


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a client from ``LLM_PROVIDER`` (default: mock)."""
    settings = settings or load_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model)
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.llm_model)
    return MockLLM()
