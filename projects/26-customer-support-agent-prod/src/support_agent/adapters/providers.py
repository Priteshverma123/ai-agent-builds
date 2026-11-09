"""Optional real providers behind the same LLM port. Imported lazily, so the official SDK
(`anthropic` or `openai`) is only needed when you actually select that provider.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import Settings
from ..domain.models import LLMResponse, Message, ToolCall
from .llm import LLM, MockLLM


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, model: str) -> None:
        import anthropic  # pip install anthropic

        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY (or an `ant auth login` profile)
        self._model = model or "claude-opus-5-5"

    def complete(self, system: str, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        response = self._client.beta.messages.create(
            model=self._model,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=self._to_wire(messages),
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # if the model declines, the API retries on a fallback model
        )
        if response.stop_reason == "refusal":
            return LLMResponse(text="I can't help with that here, so I'm handing you to a human agent.")
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(call_id=b.id, name=b.name, args=dict(b.input))
                 for b in response.content if b.type == "tool_use"]
        return LLMResponse(text=text, tool_calls=calls,
                           provider_content=[b.model_dump(exclude_none=True) for b in response.content])

    @staticmethod
    def _to_wire(messages: list[Message]) -> list[dict[str, Any]]:
        wire: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "user":
                wire.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                content = m.provider_content or [{"type": "text", "text": m.content}] + [
                    {"type": "tool_use", "id": c.call_id, "name": c.name, "input": c.args} for c in m.tool_calls]
                wire.append({"role": "assistant", "content": content})
            else:
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                if wire and wire[-1]["role"] == "user" and isinstance(wire[-1]["content"], list):
                    wire[-1]["content"].append(block)  # all results of one turn go in a single message
                else:
                    wire.append({"role": "user", "content": [block]})
        return wire


class OpenAILLM:
    name = "openai"

    def __init__(self, model: str) -> None:
        import openai  # pip install openai

        if not model:
            raise ValueError("Set LLM_MODEL to an OpenAI model name when LLM_PROVIDER=openai")
        self._client = openai.OpenAI()  # reads OPENAI_API_KEY
        self._model = model

    def complete(self, system: str, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        wire: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "tool":
                wire.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
            elif m.role == "assistant" and m.tool_calls:
                wire.append({"role": "assistant", "content": m.content or None, "tool_calls": [
                    {"id": c.call_id, "type": "function",
                     "function": {"name": c.name, "arguments": json.dumps(c.args)}} for c in m.tool_calls]})
            else:
                wire.append({"role": m.role, "content": m.content})
        fn_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                      "parameters": t["input_schema"]}} for t in tools]
        choice = self._client.chat.completions.create(model=self._model, messages=wire, tools=fn_tools).choices[0]
        calls = [ToolCall(call_id=c.id, name=c.function.name, args=json.loads(c.function.arguments or "{}"))
                 for c in (choice.message.tool_calls or [])]
        return LLMResponse(text=choice.message.content or "", tool_calls=calls)


def build_llm(settings: Settings) -> LLM:
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model)
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.llm_model)
    return MockLLM()
