"""The judge: deterministic aggregation that surfaces disagreement instead of averaging it away.

We deliberately do *not* ask a model "so what's the consensus?" - that invites a confident summary
that quietly drops the minority. Instead the judge is plain, auditable arithmetic:

* **tally**: confidence-weighted votes per stance from each agent's *final* position,
* **agreement**: the winning stance's share of the total weight; consensus needs a threshold,
* **dissent**: every agent whose final stance differs from the decision, with their best claim,
* **cruxes**: topics where agents on different sides made claims (where the argument really is),
* **shifts**: stance changes, flagged when the agent couldn't say what changed its mind.
"""

from __future__ import annotations

from collections import defaultdict

from .messages import Crux, Position, Shift, Verdict


def final_positions(rounds: list[list[Position]]) -> dict[str, Position]:
    """Each agent's last non-abstaining position (an agent that never argued is absent)."""
    final: dict[str, Position] = {}
    for positions in rounds:
        for p in positions:
            if not p.abstained:
                final[p.agent] = p
    return final


def find_shifts(rounds: list[list[Position]]) -> list[Shift]:
    shifts: list[Shift] = []
    last: dict[str, str] = {}
    for positions in rounds:
        for p in positions:
            if p.abstained:
                continue
            before = last.get(p.agent)
            if before is not None and before != p.argument.stance:
                shifts.append(Shift(agent=p.agent, round=p.round, before=before, after=p.argument.stance,
                                    because=p.argument.changed_because))
            last[p.agent] = p.argument.stance
    return shifts


def find_cruxes(rounds: list[list[Position]]) -> list[Crux]:
    """A topic is a crux if at least two different agents argued it from at least two stances."""
    by_topic: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for positions in rounds:
        for p in positions:
            if p.abstained:
                continue
            for claim in p.argument.claims:
                topic = claim.split(":", 1)[0].strip().lower()
                by_topic[topic][p.argument.stance].add(p.agent)
    cruxes = []
    for topic, sides in sorted(by_topic.items()):
        agents = set().union(*sides.values())
        if len(sides) >= 2 and len(agents) >= 2:
            cruxes.append(Crux(topic=topic, sides={s: sorted(a) for s, a in sorted(sides.items())}))
    return cruxes


def judge(question: str, rounds: list[list[Position]], threshold: float = 0.66) -> Verdict:
    final = final_positions(rounds)
    tally: dict[str, float] = defaultdict(float)
    for p in final.values():
        tally[p.argument.stance] += p.argument.confidence
    total = sum(tally.values())
    leader = max(tally, key=lambda s: (tally[s], s)) if tally else None
    agreement = tally[leader] / total if leader and total else 0.0
    consensus = agreement >= threshold
    decision = leader if consensus else "no consensus"
    dissent = [f"{p.agent} ({p.argument.stance}, {p.argument.confidence:.2f}): {p.argument.claims[0]}"
               for p in final.values() if not consensus or p.argument.stance != leader]
    everyone = {p.agent for positions in rounds for p in positions}
    return Verdict(
        question=question,
        consensus=consensus,
        decision=decision,
        agreement=round(agreement, 3),
        tally={s: round(w, 3) for s, w in sorted(tally.items(), key=lambda kv: -kv[1])},
        dissent=dissent,
        cruxes=find_cruxes(rounds),
        shifts=find_shifts(rounds),
        abstained=sorted(everyone - set(final)),
        rounds=len(rounds),
    )
