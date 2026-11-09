"""Plans as data: steps, validation, references between steps, and plan diffs.

A step's argument may point at an earlier step's output with a reference string:
``"$s1.0.id"`` means "output of step s1 -> item 0 -> field id". Because references
are plain data, a plan can be validated *before* anything runs.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

REF = re.compile(r"^\$(\w+)((?:\.\w+)*)$")


class PlanError(ValueError):
    """The planner produced a plan we refuse to run."""


@dataclass(frozen=True)
class Step:
    id: str
    tool: str
    args: dict[str, Any]
    why: str = ""

    def signature(self) -> str:
        """Compact, human-readable call, e.g. book_hotel(hotel_id=$s3.0.id, nights=2)."""
        shown = ", ".join(f"{k}={_show(v)}" for k, v in self.args.items())
        return f"{self.tool}({shown})"


@dataclass(frozen=True)
class Plan:
    version: int
    steps: tuple[Step, ...]

    def step(self, step_id: str) -> Step:
        return next(s for s in self.steps if s.id == step_id)


def _show(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_show(v) for v in value) + "]"
    return str(value)


def references(value: Any) -> list[str]:
    """All step ids referenced anywhere inside an argument value."""
    if isinstance(value, str) and (m := REF.match(value)):
        return [m.group(1)]
    if isinstance(value, list):
        return [ref for item in value for ref in references(item)]
    if isinstance(value, dict):
        return [ref for item in value.values() for ref in references(item)]
    return []


def parse_plan(data: dict, version: int, tools: set[str]) -> Plan:
    """Build a Plan from model JSON and validate it. Raises PlanError on problems."""
    try:
        steps = tuple(Step(s["id"], s["tool"], dict(s.get("args", {})), s.get("why", "")) for s in data["steps"])
    except (KeyError, TypeError) as exc:
        raise PlanError(f"malformed plan: {exc}") from exc
    if not steps:
        raise PlanError("plan has no steps")
    seen: set[str] = set()
    for step in steps:
        if step.id in seen:
            raise PlanError(f"duplicate step id {step.id}")
        if step.tool not in tools:
            raise PlanError(f"step {step.id} uses unknown tool {step.tool!r}")
        for ref in references(step.args):
            if ref not in seen:
                raise PlanError(f"step {step.id} references {ref!r}, which is not an earlier step")
        seen.add(step.id)
    return Plan(version, steps)


def resolve(value: Any, outputs: dict[str, Any]) -> Any:
    """Replace reference strings with real values from earlier step outputs."""
    if isinstance(value, list):
        return [resolve(v, outputs) for v in value]
    if not (isinstance(value, str) and (m := REF.match(value))):
        return value
    current = outputs[m.group(1)]
    for part in filter(None, m.group(2).split(".")):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


@dataclass(frozen=True)
class DiffLine:
    mark: str  # "=" kept, "~" changed, "-" removed, "+" added
    step: Step
    before: Step | None = None


def diff_plans(old: Plan, new: Plan) -> list[DiffLine]:
    """Line-up two plans by step id (like `git diff`, but for plans)."""
    old_ids, new_ids = [s.id for s in old.steps], [s.id for s in new.steps]
    lines: list[DiffLine] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old_ids, b=new_ids, autojunk=False).get_opcodes():
        if op == "equal":
            for a, b in zip(old.steps[i1:i2], new.steps[j1:j2]):
                same = (a.tool, a.args) == (b.tool, b.args)
                lines.append(DiffLine("=" if same else "~", b, None if same else a))
            continue
        lines += [DiffLine("-", s) for s in old.steps[i1:i2]]
        lines += [DiffLine("+", s) for s in new.steps[j1:j2]]
    return lines
