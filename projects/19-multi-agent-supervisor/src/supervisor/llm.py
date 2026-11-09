"""LLM adapters: one tiny interface, deterministic offline models, an optional real provider.

Two roles need a model here: the **supervisor** (routing decisions as JSON) and the **coder**
(Python source in a fenced block). Each gets its own scripted mock so the demo and tests are
offline and repeatable. ``LLM_PROVIDER=anthropic|openai`` swaps both for a real model.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import Settings, load_settings

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5", "openai": "gpt-4.1-mini"}


class LLM(Protocol):
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
                model=self.model, max_tokens=16000, system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(block.text for block in response.content if block.type == "text")
        from openai import OpenAI  # pip install openai

        response = OpenAI().chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


def llm_from_env(default: LLM, settings: Settings | None = None) -> LLM:
    """Return a real provider if ``LLM_PROVIDER`` asks for one, otherwise the offline default."""
    settings = settings or load_settings()
    if settings.use_mock:
        return default
    return ProviderLLM(settings.llm_provider, settings.llm_model)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply."""
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in reply: {text[:80]!r}")
    return json.loads(match.group(0))


def extract_code(text: str) -> str:
    """Pull Python source out of a ```python fenced block (or take the whole reply)."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, flags=re.DOTALL)
    return (match.group(1) if match else text).strip() + "\n"


def _line(prompt: str, label: str) -> str:
    match = re.search(rf"^{label}:\s*(.+)$", prompt, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


class MockSupervisorLLM:
    """Reads the state summary and routes like a sensible tech lead would.

    The real model gets exactly the same prompt; this mock just makes the routing deterministic.
    """

    name = "mock-supervisor"

    def complete(self, system: str, prompt: str) -> str:
        research, code, review = (_line(prompt, k) for k in ("RESEARCH", "CODE", "REVIEW"))
        if research == "none":
            plan = {"next": [
                {"worker": "researcher", "instruction": "Find our URL slug style guide rules"},
                {"worker": "researcher", "instruction": "Find slug examples we must match (acceptance tests)"},
            ], "reason": "No research yet; the two lookups are independent, so run them in parallel."}
        elif code == "none":
            plan = {"next": [{"worker": "coder", "instruction": "Implement slugify(title) following the rules"}],
                    "reason": "Research is in; time to write code."}
        elif review == "none" or not review.startswith(code.split()[0]):
            plan = {"next": [{"worker": "reviewer", "instruction": f"Review {code.split()[0]} against every example"}],
                    "reason": "New code has not been reviewed yet."}
        elif "FAILED" in review:
            plan = {"next": [{"worker": "coder", "instruction": "Fix the failing examples from the review"}],
                    "reason": "Review failed; send the failures back to the coder."}
        else:
            plan = {"next": "FINISH", "reason": "Latest code passed review."}
        return json.dumps(plan)


_CODE_V1 = '''def slugify(title: str) -> str:
    """Turn a title into a URL slug."""
    return "-".join(title.lower().split())
'''

_CODE_V2 = '''import re

MAX_LENGTH = 40


def slugify(title: str) -> str:
    """Turn a title into a URL slug that follows the style guide."""
    text = re.sub(r"[^a-z0-9\\s-]", "", title.lower())
    text = re.sub(r"[\\s-]+", "-", text).strip("-")
    return text[:MAX_LENGTH].rstrip("-")
'''


class MockCoderLLM:
    """First draft is the classic naive slugify; with review feedback it writes the real one."""

    name = "mock-coder"

    def complete(self, system: str, prompt: str) -> str:
        code = _CODE_V2 if "REVIEW FEEDBACK" in prompt else _CODE_V1
        return f"Here is the implementation.\n```python\n{code}```"
