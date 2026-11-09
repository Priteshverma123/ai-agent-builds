"""Plan-then-execute with re-planning.

    Planner (LLM)  -> a whole plan up front, as JSON data
    Executor (code)-> runs steps in order, resolving $references between them
    On failure     -> the planner sees what succeeded and what broke, and returns plan v2

Why bother? A ReAct loop (project 03) decides one step at a time. Planning first gives
you something to *validate, show a human, and diff* before any side effect happens,
and the executor never needs the model for the easy parts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .llm import LLM, extract_json
from .plan import Plan, PlanError, Step, diff_plans, parse_plan, resolve
from .tools import ToolError, ToolSpec
from .trace import Trace

PLANNER_SYSTEM = """TASK: PLAN
You are the planner of a travel-booking agent. Reply with JSON only:
{"steps": [{"id": "s1", "tool": "...", "args": {...}, "why": "..."}]}
Rules:
- Use only the listed tools and their params.
- To use an earlier step's output, write a reference string like "$s1.0.id"
  (step s1 -> item 0 -> field id) or "$s2.confirmation".
- When re-planning, keep every completed step unchanged (same id, tool and args),
  give new steps new ids, and update later steps that referenced the failed step.
- If the failure cannot be fixed with the available tools, reply {"abort": "reason"}."""


@dataclass
class StepResult:
    step_id: str
    ok: bool
    output: Any = None
    error: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    status: str  # done | failed | aborted
    plans: list[Plan]
    results: list[StepResult]
    reason: str = ""

    @property
    def outputs(self) -> dict[str, Any]:
        return {r.step_id: r.output for r in self.results if r.ok}


class Executor:
    """Runs one step: resolve references, call the tool, capture success or failure."""

    def __init__(self, tools: dict[str, ToolSpec]) -> None:
        self.tools = tools

    def run(self, step: Step, outputs: dict[str, Any]) -> StepResult:
        try:
            args = {k: resolve(v, outputs) for k, v in step.args.items()}
        except (KeyError, IndexError, TypeError) as exc:
            return StepResult(step.id, False, error=f"could not resolve arguments: {exc!r}", args=dict(step.args))
        try:
            return StepResult(step.id, True, self.tools[step.tool].fn(**args), args=args)
        except (ToolError, TypeError) as exc:
            return StepResult(step.id, False, error=str(exc), args=args)


class PlanExecuteAgent:
    def __init__(self, llm: LLM, tools: dict[str, ToolSpec], max_replans: int = 2, trace: Trace | None = None) -> None:
        self.llm = llm
        self.tools = tools
        self.executor = Executor(tools)
        self.max_replans = max_replans
        self.trace = trace or Trace(echo=False)

    # -- planning ------------------------------------------------------------
    def _ask_planner(self, request: dict[str, Any], version: int) -> Plan | str:
        """Returns a validated Plan, or an abort reason string."""
        request = {"tools": [t.schema() for t in self.tools.values()], **request}
        data = extract_json(self.llm.complete(PLANNER_SYSTEM, json.dumps(request, indent=1)))
        if "abort" in data:
            return str(data["abort"])
        return parse_plan(data, version, set(self.tools))

    def _show_plan(self, plan: Plan) -> None:
        details = [f"{s.id:<4} {s.signature()}" + (f"   # {s.why}" if s.why else "") for s in plan.steps]
        self.trace.event("plan", f"v{plan.version}  ({len(plan.steps)} steps)", details)

    def _show_diff(self, old: Plan, new: Plan, done: set[str]) -> None:
        details = []
        for line in diff_plans(old, new):
            tag = "   (done)" if line.step.id in done else ""
            details.append(f"{line.mark} {line.step.id:<4} {line.step.signature()}{tag}")
            if line.mark == "~" and line.before:
                details.append(f"       was: {line.before.signature()}")
        self.trace.event("diff", f"plan v{old.version} -> v{new.version}   (= kept  ~ changed  - removed  + added)", details)

    # -- the loop ------------------------------------------------------------
    def run(self, goal: str) -> RunResult:
        self.trace.box("PLANNER-EXECUTOR AGENT", [f"goal: {goal}", f"model: {self.llm.name} | max re-plans: {self.max_replans}"])
        plans: list[Plan] = []
        results: list[StepResult] = []
        try:
            first = self._ask_planner({"goal": goal}, version=1)
        except PlanError as exc:
            return self._finish(RunResult("failed", plans, results, f"invalid first plan: {exc}"))
        if isinstance(first, str):
            return self._finish(RunResult("aborted", plans, results, first))
        plans.append(first)
        self._show_plan(first)

        while True:
            plan, outputs = plans[-1], {r.step_id: r.output for r in results if r.ok}
            pending = [s for s in plan.steps if s.id not in outputs]
            failure = self._execute(pending, outputs, results)
            if failure is None:
                return self._finish(RunResult("done", plans, results))
            if len(plans) > self.max_replans:
                return self._finish(RunResult("failed", plans, results, f"gave up after {self.max_replans} re-plans"))

            step = plan.step(failure.step_id)
            request = {"goal": goal, "version": plan.version,
                       "current_plan": [{"id": s.id, "tool": s.tool, "args": s.args, "why": s.why} for s in plan.steps],
                       "completed": outputs,
                       "failure": {"step": step.id, "tool": step.tool, "args": step.args,
                                   "resolved_args": failure.args, "error": failure.error}}
            self.trace.event("think", f"step {step.id} failed -> asking the planner for plan v{plan.version + 1}")
            try:
                new = self._ask_planner(request, version=plan.version + 1)
            except PlanError as exc:
                return self._finish(RunResult("failed", plans, results, f"planner returned an invalid plan: {exc}"))
            if isinstance(new, str):
                return self._finish(RunResult("aborted", plans, results, new))
            self._show_diff(plan, new, set(outputs))
            plans.append(new)

    def _execute(self, steps: list[Step], outputs: dict[str, Any], results: list[StepResult]) -> StepResult | None:
        """Run steps in order. Returns the first failure, or None if all succeeded."""
        for step in steps:
            result = self.executor.run(step, outputs)
            results.append(result)
            shown = Step(step.id, step.tool, result.args).signature()
            if not result.ok:
                self.trace.event("FAIL", f"{step.id:<4} {shown}", [f"x {result.error}"])
                return result
            outputs[step.id] = result.output
            self.trace.event("run", f"{step.id:<4} {shown}", [f"-> {_brief(result.output)}"])
        return None

    def _finish(self, result: RunResult) -> RunResult:
        body = [f"status: {result.status.upper()}" + (f" - {result.reason}" if result.reason else ""),
                f"plans used: {len(result.plans)} | steps run: {len(result.results)} | "
                f"failures: {sum(not r.ok for r in result.results)}"]
        self.trace.blank()
        self.trace.box("RESULT", body)
        return result


def _brief(output: Any) -> str:
    """One-line summary of a tool output for the trace."""
    if isinstance(output, list):
        first = ", ".join(f"{k}={v}" for k, v in output[0].items()) if output else "-"
        return f"{len(output)} results; top: {first}"
    if isinstance(output, dict):
        return ", ".join(f"{k}={v}" for k, v in output.items())
    return str(output)
