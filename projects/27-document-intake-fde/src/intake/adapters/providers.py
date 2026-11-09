"""Optional real providers. Both ask for JSON and let the pipeline's pydantic validation (plus one
repair retry) catch anything malformed. The official SDK is imported only when selected.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import Settings
from .llm import LLM, MockLLM

CLASSIFY_PROMPT = """Classify this business document as one of: {labels}, or "unknown".
Reply with JSON only: {{"label": "...", "confidence": 0.0-1.0, "rationale": "..."}}

<document>
{text}
</document>"""

EXTRACT_PROMPT = """Extract a {doc_type} from the document into JSON matching this JSON Schema.
Copy values exactly as printed except: dates as YYYY-MM-DD, amounts as numbers. Use null for anything
not present; never guess. Reply with the JSON object only.
{feedback}
<schema>
{schema}
</schema>

<document>
{text}
</document>"""


def parse_json(reply: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    return json.loads(match.group(0)) if match else {}


class PromptedLLM:
    """Shared prompt logic; subclasses only implement `_complete(prompt) -> str`."""

    name = "prompted"

    def _complete(self, prompt: str) -> str:
        raise NotImplementedError

    def classify(self, text: str, labels: list[str]) -> dict[str, Any]:
        return parse_json(self._complete(CLASSIFY_PROMPT.format(labels=", ".join(labels), text=text)))

    def extract(self, text: str, doc_type: str, schema: dict[str, Any], feedback: str | None = None) -> dict[str, Any]:
        note = f"\nYour previous answer failed validation: {feedback}\nFix those fields.\n" if feedback else ""
        return parse_json(self._complete(EXTRACT_PROMPT.format(
            doc_type=doc_type, schema=json.dumps(schema), text=text, feedback=note)))


class AnthropicLLM(PromptedLLM):
    name = "anthropic"

    def __init__(self, model: str) -> None:
        import anthropic  # pip install anthropic

        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY (or an `ant auth login` profile)
        self._model = model or "claude-opus-5-5"

    def _complete(self, prompt: str) -> str:
        response = self._client.messages.create(model=self._model, max_tokens=16000,
                                                messages=[{"role": "user", "content": prompt}])
        if response.stop_reason == "refusal":
            return "{}"  # empty extraction -> validation fails -> exceptions queue
        return "".join(b.text for b in response.content if b.type == "text")


class OpenAILLM(PromptedLLM):
    name = "openai"

    def __init__(self, model: str) -> None:
        import openai  # pip install openai

        if not model:
            raise ValueError("Set LLM_MODEL to an OpenAI model name when LLM_PROVIDER=openai")
        self._client = openai.OpenAI()  # reads OPENAI_API_KEY
        self._model = model

    def _complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(model=self._model,
                                                        messages=[{"role": "user", "content": prompt}])
        return response.choices[0].message.content or ""


def build_llm(provider: str | None = None, settings: Settings | None = None) -> LLM:
    """Pick the extractor: an explicit ``provider`` wins, otherwise ``Settings`` (``LLM_PROVIDER``)."""
    settings = settings or Settings.from_env()
    provider = (provider or settings.llm_provider).lower()
    model = settings.llm_model
    if provider == "anthropic":
        return AnthropicLLM(model)
    if provider == "openai":
        return OpenAILLM(model)
    return MockLLM()
