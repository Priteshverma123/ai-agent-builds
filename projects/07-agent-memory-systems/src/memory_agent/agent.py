"""MemoryAgent: one chat turn = extract -> store -> recall -> build prompt -> respond -> evict/summarise.

Memory layers, from fastest to most durable:
  1. Short-term buffer   - the last few turns, verbatim, under a token budget
  2. Running summary     - the gist of turns that fell out of the buffer
  3. Long-term store     - durable facts in SQLite, recalled by relevance
"""

from __future__ import annotations

from dataclasses import dataclass

from .buffer import Message, ShortTermMemory, estimate_tokens
from .llm import LLM, extract_json
from .store import Fact, LongTermMemory, Recall
from .trace import Trace

EXTRACT_SYSTEM = """TASK: EXTRACT
Find durable facts about the user in their message: identity, preferences, goals,
constraints. Ignore small talk and questions. Give each fact a stable "slot" when a
newer fact should replace an older one (name, city, diet, allergy:<item>, training),
and an importance from 0 to 1 (safety-related facts like allergies = 1.0).
Reply with JSON only: {"facts": [{"text": "...", "kind": "...", "slot": "...", "importance": 0.8}]}"""

SUMMARIZE_SYSTEM = """TASK: SUMMARIZE
Merge the new turns into the current summary. Keep names, decisions and open
questions. Stay under 60 words. Reply with the summary text only."""

RESPOND_SYSTEM = """TASK: RESPOND
You are a friendly personal assistant. Use the relevant memories when they help,
and never contradict them. Keep replies to one or two sentences."""


@dataclass
class TurnReport:
    reply: str
    stored: list[str]
    already_known: list[str]
    recalled: list[Recall]
    prompt_tokens: int


class MemoryAgent:
    def __init__(self, llm: LLM, store: LongTermMemory, buffer_tokens: int = 80, recall_k: int = 4, trace: Trace | None = None) -> None:
        self.llm = llm
        self.store = store
        self.buffer = ShortTermMemory(buffer_tokens)
        self.summary = ""
        self.recall_k = recall_k
        self.trace = trace or Trace(echo=False)

    # -- the turn ------------------------------------------------------------
    def chat(self, user_text: str) -> TurnReport:
        turn = self.store.tick()
        self.trace.event("user", f"(turn {turn}) {user_text}")
        stored, known = self._remember(user_text)
        recalled = self.store.recall(user_text, k=self.recall_k)
        self._show_recall(recalled)

        prompt = self._build_prompt(user_text, recalled, stored, known)
        reply = self.llm.complete(RESPOND_SYSTEM, prompt).strip()
        self.trace.event("agent", reply)

        evicted = self.buffer.add("user", user_text) + self.buffer.add("assistant", reply)
        if evicted:
            self._summarise(evicted)
        self.trace.blank()
        return TurnReport(reply, stored, known, recalled, estimate_tokens(RESPOND_SYSTEM + prompt))

    def end_session(self) -> None:
        """Turn the session summary into an episodic long-term memory."""
        if self.summary:
            result = self.store.write(Fact(f"Earlier session: {self.summary}", kind="episode", importance=0.4))
            self.trace.event("store", f"+ episode saved (#{result.memory.id})")

    # -- steps ---------------------------------------------------------------
    def _remember(self, user_text: str) -> tuple[list[str], list[str]]:
        """Write extracted facts to long-term memory. Returns (new_or_updated, already_known)."""
        facts = extract_json(self.llm.complete(EXTRACT_SYSTEM, f"Message: {user_text}"))["facts"]
        stored, known = [], []
        for raw in facts:
            result = self.store.write(Fact(raw["text"], raw.get("kind", "note"), raw.get("slot"), float(raw.get("importance", 0.5))))
            if result.action == "added":
                self.trace.event("store", f"+ added   #{result.memory.id} [{result.memory.kind}] {result.memory.text}")
                stored.append(result.memory.text)
            elif result.action == "updated":
                self.trace.event("store", f"~ updated #{result.memory.id} slot={result.memory.slot}: "
                                          f'"{result.previous}" -> "{result.memory.text}"')
                stored.append(result.memory.text)
            else:
                self.trace.event("store", f"= already known #{result.memory.id} {result.memory.text}")
                known.append(result.memory.text)
        return stored, known

    def _show_recall(self, recalled: list[Recall]) -> None:
        if not recalled:
            self.trace.event("recall", "nothing relevant in long-term memory")
            return
        rows = [f"{r.score:5.2f}  sim {r.similarity:4.2f}  imp {r.memory.importance:3.1f}  rec {r.recency:4.2f}  {r.memory.text}"
                for r in recalled]
        self.trace.event("recall", f"top {len(recalled)} memor{'y' if len(recalled) == 1 else 'ies'} (score = .6 sim + .25 importance + .15 recency)", rows)

    def _build_prompt(self, user_text: str, recalled: list[Recall], stored: list[str], known: list[str]) -> str:
        notes = "".join([f"New facts I just stored: {'; '.join(stored)}\n" if stored else "",
                         f"Facts I already knew: {'; '.join(known)}\n" if known else ""])
        sections = {
            "summary": f"Conversation summary: {self.summary or '(none)'}",
            "memories": "Relevant memories:\n" + "\n".join(f"- ({r.memory.kind}) {r.memory.text}" for r in recalled),
            "buffer": "Recent conversation:\n" + (self.buffer.render() or "(none)"),
            "user": f"{notes}User message: {user_text}",
        }
        sizes = " | ".join(f"{name} {estimate_tokens(text)}" for name, text in sections.items())
        self.trace.event("prompt", f"{estimate_tokens(RESPOND_SYSTEM + ' '.join(sections.values()))} tokens  "
                                   f"(system {estimate_tokens(RESPOND_SYSTEM)} | {sizes})")
        return "\n\n".join(sections.values())

    def _summarise(self, evicted: list[Message]) -> None:
        turns = "\n".join(m.render() for m in evicted)
        prompt = f"Current summary: {self.summary or '(none)'}\nNew turns:\n{turns}"
        self.summary = self.llm.complete(SUMMARIZE_SYSTEM, prompt).strip()
        self.trace.event("evict", f"{len(evicted)} old message(s) left the {self.buffer.max_tokens}-token buffer -> summarised",
                         [f"summary: {self.summary}"])
