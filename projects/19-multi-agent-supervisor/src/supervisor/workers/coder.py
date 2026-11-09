"""Coder: asks a model for an implementation, grounded in research notes and review feedback."""

from __future__ import annotations

import asyncio

from ..llm import LLM, extract_code
from ..messages import CodeArtifact, WorkerResult
from ..state import SharedState

SYSTEM_PROMPT = """You are a senior Python engineer. Write one small, dependency-free module.
Follow every rule you are given exactly. Return only a ```python fenced block."""


class Coder:
    name = "coder"
    description = "Writes or fixes Python code from the research notes and the latest review."
    parallel_safe = False  # two coders editing one file is a merge conflict, not a speed-up

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    async def run(self, instruction: str, state: SharedState) -> WorkerResult:
        prompt = self.build_prompt(instruction, state)
        reply = await asyncio.to_thread(self.llm.complete, SYSTEM_PROMPT, prompt)
        version = state.code.version + 1 if state.code else 1
        source = extract_code(reply)
        return WorkerResult(worker="coder", instruction=instruction,
                            code=CodeArtifact(version=version, source=source),
                            summary=f"wrote v{version} ({len(source.splitlines())} lines)")

    @staticmethod
    def build_prompt(instruction: str, state: SharedState) -> str:
        """Everything the coder needs, nothing it doesn't: rules, examples, and the failures to fix."""
        parts = [f"GOAL: {state.goal}", f"TASK: {instruction}"]
        if state.research:
            parts.append("RULES:\n" + "\n".join(f"- {r}" for r in state.research.rules))
            parts.append("EXAMPLES:\n" + "\n".join(f"- {e.given!r} -> {e.expected!r}" for e in state.research.examples))
        review = state.latest_review
        if state.code and review and not review.passed:
            parts.append(f"CURRENT CODE (v{state.code.version}):\n{state.code.source}")
            parts.append("REVIEW FEEDBACK:\n" + "\n".join(f"- {f}" for f in review.failures))
        return "\n\n".join(parts)
