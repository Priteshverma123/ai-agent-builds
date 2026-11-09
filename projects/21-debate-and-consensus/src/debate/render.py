"""Terminal rendering for rounds and verdicts (plain ASCII, aligned columns)."""

from __future__ import annotations

import textwrap

from .messages import Position, Verdict

WIDTH = 78


def wrap(line: str, width: int) -> list[str]:
    if len(line) <= width:
        return [line]
    indent = line[: len(line) - len(line.lstrip())]
    return textwrap.wrap(line, width, subsequent_indent=indent + "    ") or [""]


def clip(line: str, width: int = WIDTH) -> str:
    """Trim a line to the terminal width - the full claims are in the verdict and the data."""
    return line if len(line) <= width else line[: width - 3] + "..."


def box(title: str, lines: list[str]) -> str:
    inner = WIDTH - 4
    top = f"+-- {title} " + "-" * max(0, WIDTH - len(title) - 6) + "+"
    body = [f"| {chunk.ljust(inner)} |" for line in lines for chunk in wrap(line, inner)]
    return "\n".join([top, *body, "+" + "-" * (WIDTH - 2) + "+"])


def render_round(round_no: int, positions: list[Position], previous: dict[str, str], stable: bool) -> str:
    title = "independent openings - nobody sees anybody" if round_no == 1 else "rebuttals - each agent read the others"
    lines = [f"ROUND {round_no}  ({title})"]
    for p in positions:
        if p.abstained:
            lines.append(f"  {p.agent:<10} ABSTAIN            invalid reply: {p.error}")
            continue
        a = p.argument
        lines.append(clip(f"  {p.agent:<10} {a.stance.upper():<12} {a.confidence:.2f}  {a.claims[0]}"))
        if previous.get(p.agent) not in (None, a.stance):
            lines.append(f"  {'':<10} ^ shifted from {previous[p.agent].upper()}, "
                         f"because: {a.changed_because or '(no reason given!)'}")
    if stable:
        lines.append("  -> no stance changed this round: debate has settled")
    return "\n".join(line for raw in lines for line in wrap(raw, WIDTH))


def render_verdict(v: Verdict) -> str:
    total = sum(v.tally.values()) or 1
    headline = (f"CONSENSUS: {v.decision.upper()}  (agreement {v.agreement:.0%}, after {v.rounds} rounds)"
                if v.consensus else f"NO CONSENSUS  (strongest side only {v.agreement:.0%}, after {v.rounds} rounds)")
    lines = [headline, "", "weighted tally (confidence of final positions):"]
    lines += [f"  {stance:<12} {'#' * round(30 * w / total):<30} {w:.2f}" for stance, w in v.tally.items()]
    lines += ["", "dissent (kept, not averaged away):" if v.consensus else "the split:"]
    lines += [f"  - {d}" for d in v.dissent] or ["  (none)"]
    lines += ["", "cruxes (topics argued from different sides):"]
    lines += [f"  - {c.topic}: " + "; ".join(f"{s}={', '.join(a)}" for s, a in c.sides.items()) for c in v.cruxes] \
        or ["  (none)"]
    if v.shifts:
        lines += ["", "stance shifts:"]
        lines += [f"  - {s.agent} r{s.round}: {s.before} -> {s.after}"
                  + ("   [FLAG: unexplained - possible herding]" if s.unexplained else f"   (because {s.because})")
                  for s in v.shifts]
    if v.abstained:
        lines += ["", f"abstained (never gave a valid argument): {', '.join(v.abstained)}"]
    return box("JUDGE", lines)
