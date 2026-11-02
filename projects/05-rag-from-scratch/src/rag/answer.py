"""Step 4 of RAG: retrieve, put the chunks in the prompt as numbered sources, answer with citations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .index import Hit, VectorIndex
from .llm import LLM

SYSTEM_PROMPT = (
    "You answer questions using ONLY the numbered sources provided. "
    "Cite the source of every claim with its number in square brackets, like [1]. "
    "If the sources do not contain the answer, say you don't know. Do not use outside knowledge."
)

NO_CONTEXT_ANSWER = "I don't know -- nothing in the documents matches that question."


@dataclass
class Answer:
    text: str
    hits: list[Hit] = field(default_factory=list)  # everything retrieved
    cited: list[Hit] = field(default_factory=list)  # what the answer actually used
    bad_citations: list[int] = field(default_factory=list)  # [n] that point at no source


def build_prompt(question: str, hits: list[Hit]) -> str:
    sources = "\n".join(f"[{i}] ({hit.chunk.id}) {hit.chunk.text}" for i, hit in enumerate(hits, start=1))
    return f"Sources:\n{sources}\n\nQuestion: {question}"


def answer(question: str, index: VectorIndex, llm: LLM, k: int = 3, min_score: float = 0.1) -> Answer:
    hits = index.search(question, k, min_score)
    if not hits:  # the cheapest hallucination guard: no context, no model call
        return Answer(NO_CONTEXT_ANSWER)

    reply = llm.complete(SYSTEM_PROMPT, [{"role": "user", "content": build_prompt(question, hits)}])

    # Check the citations: every [n] must point at a source we actually provided.
    numbers = sorted({int(n) for n in re.findall(r"\[(\d+)\]", reply)})
    cited = [hits[n - 1] for n in numbers if 1 <= n <= len(hits)]
    bad = [n for n in numbers if not 1 <= n <= len(hits)]
    return Answer(reply, hits, cited, bad)
