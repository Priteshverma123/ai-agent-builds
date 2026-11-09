"""LLM adapters. MockLLM is rule-based and deterministic; RealLLM calls a provider and falls back to it."""
from __future__ import annotations

import json
import re
from typing import Any, Protocol

from capstone.config import Settings
from capstone.domain.models import Blackboard, Plan, Step
from capstone.services.rag import tokenize

TICKET_INTENT = re.compile(r"\b(open|create|file|raise|log)\s+(a|an)?\s*(ops\s+)?ticket\b", re.I)
CALC_INTENT = re.compile(r"\b(how much|in total|total|calculate|sum)\b|\b\d+\s*(nights?|days?)\b", re.I)
SENTENCE_WORDS = {"How", "What", "Can", "Please", "My", "The", "When", "Where", "Is", "Do", "Does"}
URGENT = re.compile(r"\b(swollen|swelling|smoke|fire|hot|stolen|lost|breach|injur\w*)\b", re.I)


class LLM(Protocol):
    def plan(self, question: str, agents: dict[str, str]) -> Plan: ...

    def calculation_for(self, question: str, board: Blackboard) -> str | None: ...

    def ticket_for(self, question: str) -> dict[str, str]: ...

    def write_answer(self, question: str, board: Blackboard) -> str: ...


def _best_sentence(text: str, question: str) -> tuple[str, int]:
    """Sentence sharing the most specific words with the question. Long words are a cheap IDF proxy."""
    q = set(tokenize(question))
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    scored = [(sum(len(w) for w in q & set(tokenize(s))), len(q & set(tokenize(s))), -i, s)
              for i, s in enumerate(sentences)]
    _, overlap, _, best = max(scored)
    return best, overlap


class MockLLM:
    """Deterministic stand-in for a model, so every demo run and test gives the same answer."""

    def plan(self, question: str, agents: dict[str, str]) -> Plan:
        steps = [Step("research", f"Find handbook passages relevant to: {question}")]
        if TICKET_INTENT.search(question):
            steps.append(Step("ops", "Open an Ops ticket describing the user's issue"))
        elif CALC_INTENT.search(question):
            steps.append(Step("analyst", "Compute the number the user asked for from the cited rates"))
        steps.append(Step("writer", "Write a short answer with [n] citations"))
        return Plan(question, tuple(s for s in steps if s.agent in agents))

    def calculation_for(self, question: str, board: Blackboard) -> str | None:
        count = re.search(r"\b(\d+)\s*(night|day)s?\b", question, re.I)
        if not count:
            return None
        unit = count.group(2).lower()
        names = set(re.findall(r"\b[A-Z][a-z]+\b", question)) - SENTENCE_WORDS  # e.g. {"Berlin"}
        best: tuple[int, str] | None = None
        for hit in board.findings:
            for m in re.finditer(rf"\$(\d+(?:\.\d+)?) per {unit}([^.$]*)", hit.chunk.text):
                window = m.group(2)
                score = 2 * any(n in window for n in names)
                if names and not any(n in window for n in names) and re.search(r"everywhere else|elsewhere", window):
                    score += 1
                if best is None or score > best[0]:
                    best = (score, f"{m.group(1)} * {count.group(1)}")
        return best[1] if best else None

    def ticket_for(self, question: str) -> dict[str, str]:
        title = question.split(":", 1)[1].strip() if ":" in question else question.strip()
        return {"title": title.rstrip(".?!"), "priority": "high" if URGENT.search(question) else "normal"}

    def write_answer(self, question: str, board: Blackboard) -> str:
        parts: list[str] = []
        top = board.findings[0].score if board.findings else 0
        for n, hit in enumerate(board.findings[:2], 1):
            sentence, overlap = _best_sentence(hit.chunk.text, question)
            if (n == 1 and overlap) or (overlap >= 2 and hit.score >= 0.6 * top):
                parts.append(f"{sentence.rstrip('.')} [{n}].")
        if board.calculation:
            c = board.calculation
            parts.append(f"For your trip that comes to ${c['value']:g} ({c['expression']}) [1].")
        if board.ticket:
            t = board.ticket
            parts.append(f"I opened ticket {t['id']} ({t['priority']} priority): \"{t['title']}\".")
        if not parts:
            return ("I couldn't find this in the company documents, so I won't guess. "
                    "Please ask the team that owns the topic.")
        return " ".join(parts)


class RealLLM(MockLLM):
    """Uses a real model for planning and writing; the deterministic helpers stay rule-based.

    Any provider or parsing failure falls back to MockLLM behaviour, so the system degrades, not breaks.
    """

    def __init__(self, provider: str, settings: Settings | None = None) -> None:
        import httpx
        self.provider, self._http = provider, httpx.Client(timeout=30)
        self.settings = settings or Settings.from_env()

    def plan(self, question: str, agents: dict[str, str]) -> Plan:
        prompt = ("Plan which specialists to call, in order. Reply ONLY with JSON "
                  '{"steps": [{"agent": str, "instruction": str}]}. Always end with "writer".\n'
                  f"Agents: {json.dumps(agents)}\nQuestion: {question}")
        try:
            data = json.loads(re.search(r"\{.*\}", self._complete(prompt), re.S).group(0))
            steps = tuple(Step(s["agent"], s["instruction"]) for s in data["steps"] if s["agent"] in agents)
            if steps and steps[-1].agent == "writer":
                return Plan(question, steps)
        except Exception:  # noqa: BLE001
            pass
        return super().plan(question, agents)

    def write_answer(self, question: str, board: Blackboard) -> str:
        sources = "\n".join(f"[{i}] {h.chunk.text}" for i, h in enumerate(board.findings, 1))
        prompt = (f"Answer using ONLY these sources and cite them as [n]. If they don't answer it, say so.\n"
                  f"{sources}\nCalculation: {board.calculation}\nTicket: {board.ticket}\nQuestion: {question}")
        try:
            return self._complete(prompt).strip()
        except Exception:  # noqa: BLE001
            return super().write_answer(question, board)

    def _complete(self, prompt: str) -> str:
        msgs: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        if self.provider == "anthropic":
            r = self._http.post("https://api.anthropic.com/v1/messages", json={
                "model": self.settings.model, "max_tokens": 500, "messages": msgs},
                headers={"x-api-key": self.settings.anthropic_api_key, "anthropic-version": "2023-06-01"})
            r.raise_for_status()
            return r.json()["content"][0]["text"]
        r = self._http.post("https://api.openai.com/v1/chat/completions", json={
            "model": self.settings.model, "messages": msgs},
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def default_llm(settings: Settings | None = None) -> LLM:
    settings = settings or Settings.from_env()
    provider = settings.llm_provider
    return RealLLM(provider, settings) if provider in ("anthropic", "openai") else MockLLM()
