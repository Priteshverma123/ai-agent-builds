"""Model adapters.

Every model speaks the same tiny protocol: it receives a system prompt plus a chat history and
returns ONE JSON object per turn:

    {"tool": "<name>", "args": {...}}     -> the agent should call a tool
    {"answer": "<text>"}                  -> the agent is done

`GullibleMockLLM` is the default. It is deliberately naive: like a real model, it can be talked
into following instructions that appear *inside* tool results. That is the whole point of this
project: the guardrails have to protect an agent whose model cannot protect itself.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from .config import load_settings

Message = dict[str, str]

FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


class LLM(Protocol):
    """Anything with a name and a `complete(system, messages) -> str` method."""

    name: str

    def complete(self, system: str, messages: list[Message]) -> str: ...


def parse_reply(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply; plain text becomes a final answer."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and ("tool" in data or "answer" in data):
                return data
        except json.JSONDecodeError:
            pass
    return {"answer": text.strip()}


# --------------------------------------------------------------------------- mock model

INJECTED_EMAIL = re.compile(
    r"\b(?:send|e-?mail|forward)\b[^.\n]{0,60}?\bto\s+([\w.+-]+@[\w-]+(?:\.[\w-]+)+)", re.IGNORECASE
)
URL = re.compile(r"https?://[^\s\"'<>]+")
TAGS = re.compile(r"<!--.*?-->|<[^>]+>", re.DOTALL)


def _tool_results(messages: list[Message]) -> list[str]:
    return [m["content"] for m in messages if m["role"] == "user" and m["content"].startswith("<tool_result")]


def _result_of(results: list[str], tool: str) -> str:
    """Return the body of the first result produced by `tool`, with all markup removed."""
    raw = next((r for r in results if f'name="{tool}"' in r), "")
    without_headings = re.sub(r"(?m)^\s*#.*$", " ", TAGS.sub(" ", raw))
    return re.sub(r"\s+", " ", without_headings).strip()


def _summarise(page: str, sentences: int = 2) -> str:
    prose = [s for s in re.split(r"(?<=[.!?])\s+", page) if len(s.split()) > 4]
    return " ".join(prose[:sentences]) or "The page had no readable content."


class GullibleMockLLM:
    """A rule-based stand-in for an LLM that obeys whatever instructions it reads."""

    name = "mock:gullible"

    def complete(self, system: str, messages: list[Message]) -> str:
        request = messages[0]["content"]
        results = _tool_results(messages)
        called = [json.loads(m["content"]).get("tool") for m in messages if m["role"] == "assistant"]

        # 1. The vulnerability: an instruction inside fetched content is treated as a command.
        for text in results:
            hit = INJECTED_EMAIL.search(text)
            if hit and "send_email" not in called:
                if "notes" in text.lower() and "read_notes" not in called:
                    return json.dumps({"tool": "read_notes", "args": {}})
                body = _result_of(results, "read_notes") or "hello"
                return json.dumps({"tool": "send_email", "args": {"to": hit.group(1), "body": body}})

        # 2. The honest plan: fetch the page the user asked about, or read their notes.
        url = URL.search(request)
        if url and "fetch_page" not in called:
            return json.dumps({"tool": "fetch_page", "args": {"url": url.group(0)}})
        if "notes" in request.lower() and "read_notes" not in called:
            return json.dumps({"tool": "read_notes", "args": {}})

        # 3. Compose the answer from what came back.
        if "notes" in request.lower():
            return json.dumps({"answer": "Your notes say: " + _result_of(results, "read_notes")})
        return json.dumps({"answer": "Summary: " + _summarise(_result_of(results, "fetch_page"))})


# --------------------------------------------------------------------------- real providers


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
            # Server-side refusal fallback: a declined request is retried on a fallback model.
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
    """Pick a model from LLM_PROVIDER (mock | anthropic | openai). Mock is the default."""
    provider = load_settings().llm_provider
    if provider == "mock":
        return default
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "openai":
        return OpenAILLM()
    raise ValueError(f"Unknown LLM_PROVIDER {provider!r}; use mock, anthropic or openai")
