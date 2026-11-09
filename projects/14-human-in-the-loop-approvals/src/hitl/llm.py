"""Model adapters. The model only *proposes* actions as JSON; it never executes anything itself.

    {"tool": "<name>", "args": {...}}   or   {"answer": "<text>"}
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from .config import load_settings

Message = dict[str, str]
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
RESULT = re.compile(r'<tool_result name="(?P<tool>\w+)" status="(?P<status>\w+)">\n?(?P<body>.*?)\n?</tool_result>', re.S)


class LLM(Protocol):
    name: str

    def complete(self, system: str, messages: list[Message]) -> str: ...


def parse_reply(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and ("tool" in data or "answer" in data):
                return data
        except json.JSONDecodeError:
            pass
    return {"answer": text.strip()}


def tool_history(messages: list[Message]) -> dict[str, tuple[str, str]]:
    """Map each tool the agent tried to (status, body) of its latest result."""
    seen: dict[str, tuple[str, str]] = {}
    for m in messages:
        if m["role"] == "user":
            for hit in RESULT.finditer(m["content"]):
                seen[hit["tool"]] = (hit["status"], hit["body"])
    return seen


class PlannerMockLLM:
    """A scripted support agent: look up the order, refund, tell the customer, tidy up accounts.

    It reacts to rejections like a sensible model would: if the refund is rejected it tells the
    customer the case was escalated instead of claiming the money is on its way.
    """

    name = "mock:planner"

    def complete(self, system: str, messages: list[Message]) -> str:
        task = messages[0]["content"]
        lowered = task.lower()
        tried = tool_history(messages)
        found = re.search(r"\b[A-Z]-\d{4}\b", task)
        if not found:
            return json.dumps({"answer": "Which order is this about? I need an order id like A-1042."})
        order_id = found.group(0)

        if "lookup_order" not in tried:
            return _call("lookup_order", order_id=order_id)
        if not tried["lookup_order"][1].startswith("{"):
            return json.dumps({"answer": f"I could not find order {order_id}; nothing was changed."})
        order = json.loads(tried["lookup_order"][1])
        if "refund" in lowered and "issue_refund" not in tried:
            return _call("issue_refund", order_id=order_id, amount=order["amount"])
        if ("tell" in lowered or "email" in lowered) and "send_email" not in tried:
            refunded = tried.get("issue_refund", ("", ""))[0] == "ok"
            body = (f"We refunded the duplicate charge of {order['amount']:.2f} on order {order_id}."
                    if refunded else f"We have escalated the duplicate charge on order {order_id} to our finance team.")
            return _call("send_email", to=order["email"], subject=f"Your order {order_id}", body=body)
        if "close" in lowered and "close_account" not in tried:
            return _call("close_account", customer_id=order["duplicate_account"], purge_data=True)
        summary = "; ".join(f"{tool}: {status}" for tool, (status, _) in tried.items())
        return json.dumps({"answer": f"Finished. {summary}."})


def _call(tool: str, **args: Any) -> str:
    return json.dumps({"tool": tool, "args": args})


class AnthropicLLM:
    """Claude via the official `anthropic` SDK (pip install anthropic)."""

    def __init__(self, model: str | None = None) -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or load_settings().llm_model or "claude-opus-5-5"
        self.name = f"anthropic:{self.model}"

    def complete(self, system: str, messages: list[Message]) -> str:
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": 16000, "system": system, "messages": messages}
        if self.model in FALLBACK_MODELS:
            response = self.client.beta.messages.create(
                **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
            )
        else:
            response = self.client.messages.create(**kwargs)
        if response.stop_reason == "refusal":
            return json.dumps({"answer": "[the model declined this request]"})
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAILLM:
    """OpenAI chat completions via the official `openai` SDK (pip install openai)."""

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        self.client = OpenAI()
        self.model = model or load_settings().llm_model or "gpt-4o-mini"
        self.name = f"openai:{self.model}"

    def complete(self, system: str, messages: list[Message]) -> str:
        response = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "system", "content": system}, *messages]
        )
        return response.choices[0].message.content or ""


def llm_from_env(default: LLM) -> LLM:
    provider = load_settings().llm_provider
    if provider == "mock":
        return default
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "openai":
        return OpenAILLM()
    raise ValueError(f"Unknown LLM_PROVIDER {provider!r}; use mock, anthropic or openai")
