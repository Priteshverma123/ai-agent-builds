"""The debate loop: independent openings, rebuttal rounds in parallel, stop when stances settle."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from .debater import Debater
from .judge import judge
from .messages import Position, Verdict


def transcript_for(agent: str, positions: list[Position]) -> str:
    """What one agent gets to read: everyone *else's* latest stance and claims."""
    lines = []
    for p in positions:
        if p.agent == agent or p.abstained:
            continue
        lines.append(f"- {p.agent} ({p.argument.stance}, confidence {p.argument.confidence:.2f}):")
        lines += [f"    {claim}" for claim in p.argument.claims]
    return "\n".join(lines)


def stances(positions: list[Position]) -> dict[str, str | None]:
    return {p.agent: None if p.abstained else p.argument.stance for p in positions}


class Debate:
    def __init__(self, debaters: list[Debater], max_rounds: int = 4, threshold: float = 0.66,
                 on_round: Callable[[int, list[Position], bool], None] | None = None) -> None:
        if len({d.name for d in debaters}) != len(debaters):
            raise ValueError("debater names must be unique")
        self.debaters = debaters
        self.max_rounds = max_rounds
        self.threshold = threshold
        self.on_round = on_round or (lambda *_: None)

    async def run(self, question: str) -> Verdict:
        rounds: list[list[Position]] = []
        for round_no in range(1, self.max_rounds + 1):
            previous = rounds[-1] if rounds else []
            # Everyone argues at once. In round 1 nobody sees anybody: independent openings avoid
            # anchoring on whoever happened to speak first.
            positions = list(await asyncio.gather(*(
                d.argue(question, round_no, transcript_for(d.name, previous)) for d in self.debaters)))
            rounds.append(positions)
            stable = bool(previous) and stances(positions) == stances(previous)
            self.on_round(round_no, positions, stable)
            if stable:
                break
        return judge(question, rounds, self.threshold)
