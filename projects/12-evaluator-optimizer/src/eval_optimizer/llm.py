"""LLM clients. ``MockLLM`` is deterministic and used by default and in tests.

It plays two roles, picked by the ``TASK:`` line of the system prompt:
- WRITE / REVISE (the optimizer): the first draft is deliberately over-hyped; each
  revision applies the specific fixes named in the feedback, one edit rule per fix.
- JUDGE (the evaluator): grades clarity by sentence length and audience fit by
  counting "you" versus "we".
Because revisions only follow the feedback, the loop shows exactly how much the
quality of feedback drives the quality of the result.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from .config import Settings


class LLM(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


def extract_json(text: str) -> dict:
    """Parse the first JSON object in ``text`` (real models sometimes add prose or fences)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model output: {text[:80]!r}")
    return json.loads(match.group(0))


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, re.IGNORECASE))


YOU, WE = r"\b(you|your)\b", r"\b(we|our|us)\b"


class MockLLM:
    name = "mock"

    def complete(self, system: str, prompt: str) -> str:
        if "TASK: JUDGE" in system:
            return self._judge(prompt.split("Text:\n", 1)[1])
        brief = json.loads(re.search(r"^Brief: (.*)$", prompt, re.MULTILINE).group(1))
        if "TASK: REVISE" in system:
            draft = prompt.split("Draft:\n", 1)[1].split("\n\nFix these issues", 1)[0]
            fixes = re.findall(r"^- (.+)$", prompt.split("Fix these issues", 1)[1], re.MULTILINE)
            return self._revise(draft, fixes, brief)
        return self._first_draft(brief)

    # -- writer --------------------------------------------------------------
    @staticmethod
    def _first_draft(brief: dict) -> str:
        product, facts = brief["product"], brief["facts"]
        return (f"Introducing {product}, our revolutionary and game-changing new feature that our team has been "
                f"building for many months with a lot of care, and we truly believe every developer will love it. "
                f"{facts[0]} Behind the scenes it runs on a best-in-class storage engine that we designed and tuned "
                f"ourselves for speed and reliability on every operating system we support. We can't wait!")

    def _revise(self, draft: str, fixes: list[str], brief: dict) -> str:
        text = draft
        for fix in fixes:
            for phrase in re.findall(r"Remove hype phrase '([^']+)'", fix):
                text = re.sub(rf"\s*\b{re.escape(phrase)}\b( and)?", "", text, flags=re.IGNORECASE)
            for keyword in re.findall(r"Mention '([^']+)'", fix):
                fact = next(f for f in brief["facts"] if keyword.lower() in f.lower())
                text = self._insert_before_cta(text, fact)
            if fix.startswith("End with a call to action"):
                text = f"{text} Try it today: run `snap save` in any project."
            if fix.startswith("Split sentences"):
                text = re.sub(r", and (\w)", lambda m: ". " + m.group(1).upper(), text)
            if "'you'" in fix:
                text = self._reader_first(text, brief["required_keywords"])
            if fix.startswith("Expand to at least"):
                for fact in brief["facts"]:
                    if fact not in text:
                        text = self._insert_before_cta(text, fact)
            if (limit := re.search(r"Cut to at most (\d+) words", fix)):
                text = self._trim(text, int(limit.group(1)), brief["required_keywords"])
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _insert_before_cta(text: str, sentence: str) -> str:
        parts = _sentences(text)
        at = len(parts) - 1 if parts and parts[-1].startswith("Try") else len(parts)
        return " ".join(parts[:at] + [sentence] + parts[at:])

    @staticmethod
    def _reader_first(text: str, keywords: list[str]) -> str:
        """Drop sentences that talk about 'we' more than 'you' (unless they carry a keyword)."""
        keep = [s for s in _sentences(text)
                if _count(WE, s) <= _count(YOU, s) or any(k.lower() in s.lower() for k in keywords[1:])]
        return " ".join(keep)

    @staticmethod
    def _trim(text: str, limit: int, keywords: list[str]) -> str:
        parts = _sentences(text)
        while len(" ".join(parts).split()) > limit:
            optional = [s for s in parts if not s.startswith("Try") and not any(k.lower() in s.lower() for k in keywords)]
            if not optional:
                break
            parts.remove(max(optional, key=len))
        return " ".join(parts)

    # -- judge ---------------------------------------------------------------
    @staticmethod
    def _judge(text: str) -> str:
        longest = max((len(s.split()) for s in _sentences(text)), default=0)
        clarity = 5 if longest <= 22 else 3 if longest <= 30 else 2
        you, we = _count(YOU, text), _count(WE, text)
        audience = 5 if you > we else 3 if you == we else 2
        return json.dumps({
            "clarity": {"score": clarity, "feedback": f"Split sentences longer than 22 words (longest: {longest})."},
            "audience": {"score": audience, "feedback": f"Speak to the reader: more 'you' ({you}), less 'we/our' ({we})."},
        })


class AnthropicLLM:
    def __init__(self, model: str | None = None) -> None:
        import anthropic  # optional dependency: pip install anthropic

        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or "claude-opus-5-5"
        self.name = f"anthropic:{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model, max_tokens=16000, system=system, messages=[{"role": "user", "content": prompt}]
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAILLM:
    def __init__(self, model: str | None = None) -> None:
        import openai  # optional dependency: pip install openai

        self.client = openai.OpenAI()  # reads OPENAI_API_KEY
        self.model = model or "gpt-4.1-mini"
        self.name = f"openai:{self.model}"

    def complete(self, system: str, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model, messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content or ""


def make_llm(settings: Settings | None = None) -> LLM:
    """Pick a client from ``settings.llm_provider`` (env ``LLM_PROVIDER``, default: mock)."""
    settings = settings or Settings.from_env()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model)
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.llm_model)
    return MockLLM()
