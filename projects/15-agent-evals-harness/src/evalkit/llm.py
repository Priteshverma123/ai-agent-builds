"""Models: two versions of a mock support bot (the system under test), a mock judge, real adapters.

`v1` is the released bot. `v2` is a "prompt improvement": warmer tone, but it also changed facts
and got wordy. Without evals you would ship v2 because it *sounds* better.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from .config import load_settings

Message = dict[str, str]
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


class LLM(Protocol):
    name: str

    def complete(self, system: str, messages: list[Message]) -> str: ...


def _answer(text: str) -> str:
    return json.dumps({"answer": text})


class MockSupportLLM:
    """Rule-based support bot. Speaks the agent JSON protocol: a tool call or an answer."""

    def __init__(self, version: str = "v1") -> None:
        if version not in ("v1", "v2"):
            raise ValueError("version must be v1 or v2")
        self.version = version
        self.name = f"mock:support-{version}"

    def complete(self, system: str, messages: list[Message]) -> str:
        question = messages[0]["content"]
        q = question.lower()
        tool_result = next((m["content"] for m in messages[1:] if m["role"] == "user"), None)
        order = re.search(r"\border (\d{4})\b", q)

        if order and tool_result is None:
            return json.dumps({"tool": "order_status", "args": {"order_id": order.group(1)}})
        if order and tool_result is not None:
            return _answer(self._order_reply(order.group(1), json.loads(tool_result), "json" in q))
        if "discount" in q or "ignore your rules" in q:
            return _answer("Sorry, I can't create discount codes, but I can help with your order.")
        if "return" in q:
            days = 30 if self.version == "v1" else 14
            return _answer(f"You have {days} days to return an item for a full refund.")
        if "shipping" in q:
            count = re.search(r"(\d+) items?", q)
            items = int(count.group(1)) if count else 1
            extra = items - 1 if self.version == "v1" else items  # v2 bug: charges the first item twice
            return _answer(f"Shipping for {items} items costs ${4.99 + 1.50 * extra:.2f}.")
        if "support email" in q:
            return _answer("support@shop.example")
        if "broken" in q or "damaged" in q:
            if self.version == "v1":
                return _answer("Sorry about that! Please send a photo of the damage and we'll ship a "
                               "replacement or refund you, whichever you prefer.")
            return _answer("Oh no, I'm truly sorry to hear that your package arrived broken. We know how "
                           "disappointing it is to wait for something and then find it damaged. To get "
                           "this sorted, please reply with a photo of the item and the packaging. Once "
                           "our team has reviewed it, which usually takes one or two business days, we "
                           "will happily ship a replacement or issue a refund to your original payment "
                           "method, whichever you prefer. Thanks for your patience!")
        if "waiting" in q or "furious" in q:
            if self.version == "v1":
                return _answer("Orders usually arrive within 5-7 business days.")
            return _answer("I'm so sorry for the wait, that's frustrating. Share your order number "
                           "and I'll help right away.")
        if "open" in q or "hours" in q:
            return _answer("Support is open 9am-5pm, Monday to Friday.")
        return _answer("I'm not sure. Let me connect you with a human.")

    @staticmethod
    def _order_reply(order_id: str, record: dict[str, Any], as_json: bool) -> str:
        if not record:
            return f"Sorry, I couldn't find order {order_id}. Please check the number."
        if as_json:
            return json.dumps({"id": order_id, "status": record["status"]})
        tracking = f" Tracking number: {record['tracking']}." if "tracking" in record else ""
        return f"Order {order_id} has {record['status']}.{tracking}"


class MockJudgeLLM:
    """A deterministic stand-in for an LLM judge: scores key-point coverage, then formats like a model."""

    name = "mock:judge"

    def complete(self, system: str, messages: list[Message]) -> str:
        prompt = messages[-1]["content"]
        reply = re.search(r"Reply: (.*)\nKey points", prompt, re.S)
        points = re.search(r"covers: (.*)\n", prompt)
        text = reply.group(1).lower() if reply else ""
        wanted = [p.strip().lower() for p in points.group(1).split(";")] if points else []
        hit = [p for p in wanted if p in text]
        stars = 1 + round(4 * len(hit) / len(wanted)) if wanted else 1
        missing = [p for p in wanted if p not in hit]
        reason = "covers every key point" if not missing else f"misses: {', '.join(missing)}"
        return f"SCORE: {stars}\nREASON: {reason}"


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
