"""The model side of the review: a reply schema, a mock reviewer and real adapters.

The LLM pass does what regexes and ASTs can't: notice a network call with no timeout, decide a
`print` in a test is fine, write a summary. Its reply is validated against `LLMReview`, and the
agent applies guardrails to it (see agent.py), because the diff it reads is untrusted input.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .config import load_settings

Message = dict[str, str]
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


class LLMFinding(BaseModel):
    line: int
    severity: Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    rule: str = Field(pattern=r"^[a-z0-9-]+$")
    message: str
    suggestion: str = ""


class Dismissal(BaseModel):
    id: str
    reason: str


class LLMReview(BaseModel):
    findings: list[LLMFinding] = Field(default_factory=list)
    dismiss: list[Dismissal] = Field(default_factory=list)
    summary: str = ""


class LLM(Protocol):
    name: str

    def complete(self, system: str, messages: list[Message]) -> str: ...


ADDED = re.compile(r"^\+\s*(\d+) \| (.*)$", re.M)
STATIC = re.compile(r"^- id: (\S+)", re.M)


class MockReviewerLLM:
    """Rule-based stand-in for a reviewing model. Like real models it is helpful, occasionally
    wrong about line numbers, and willing to follow instructions it reads inside the code."""

    name = "mock:reviewer"

    def complete(self, system: str, messages: list[Message]) -> str:
        prompt = messages[-1]["content"]
        path = re.search(r"^File: (.+)$", prompt, re.M).group(1)  # type: ignore[union-attr]
        added = [(int(n), text) for n, text in ADDED.findall(prompt)]
        static_ids = STATIC.findall(prompt)
        review: dict[str, Any] = {"findings": [], "dismiss": [], "summary": ""}

        for line, text in added:
            if re.search(r"\b(requests|httpx)\.(get|post|put|delete)\(", text) and "timeout" not in text:
                review["findings"].append({
                    "line": line, "severity": "MEDIUM", "rule": "http-no-timeout",
                    "message": "HTTP call without a timeout can hang the worker forever.",
                    "suggestion": "Pass timeout=10 (or your service's budget) and handle the timeout."})
            order = re.search(r"dismiss ([a-z-]+)", text, re.I)
            if order:  # obeys an instruction written in a code comment
                rule = order.group(1).lower()
                review["dismiss"] += [{"id": i, "reason": "author says it is a test fixture"}
                                      for i in static_ids if i.startswith(rule + "@")]

        if "/tests/" in f"/{path}" or path.split("/")[-1].startswith("test_"):
            review["dismiss"] += [{"id": i, "reason": "print in a test is acceptable output"}
                                  for i in static_ids if i.startswith("debug-print@")]
        if path.endswith("db.py"):  # a plausible comment on the wrong line: the guard must drop it
            review["findings"].append({"line": 3, "severity": "LOW", "rule": "connection-pooling",
                                       "message": "Consider a connection pool.", "suggestion": ""})
        review["summary"] = f"{path}: {len(added)} added lines reviewed."
        return json.dumps(review)


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
            return json.dumps({"summary": "[the model declined to review this file]"})
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
