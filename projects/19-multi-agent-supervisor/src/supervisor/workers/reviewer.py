"""Reviewer: runs the candidate code against the acceptance examples. Tests don't hallucinate.

The code runs with a restricted set of builtins, an import allow-list and a timeout. That is
enough for a teaching demo - but it is NOT a security sandbox. In production, run untrusted code in
a separate process or container with no network and hard resource limits.
"""

from __future__ import annotations

import asyncio
import builtins

from ..messages import Example, Review, WorkerResult
from ..state import SharedState

ALLOWED_IMPORTS = {"re", "string", "unicodedata"}
SAFE_BUILTINS = {name: getattr(builtins, name) for name in (
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "int", "isinstance", "len", "list",
    "map", "max", "min", "range", "reversed", "set", "sorted", "str", "sum", "tuple", "zip", "ValueError",
)}


def _guarded_import(name: str, *args, **kwargs):
    if name.split(".")[0] not in ALLOWED_IMPORTS:
        raise ImportError(f"import of {name!r} is not allowed in review")
    return __import__(name, *args, **kwargs)


def run_examples(source: str, examples: list[Example], func: str = "slugify") -> tuple[int, list[str]]:
    """Execute ``source`` and check ``func(given) == expected`` for each example, plus a docstring."""
    namespace: dict = {"__builtins__": {**SAFE_BUILTINS, "__import__": _guarded_import}, "__name__": "candidate"}
    try:
        exec(compile(source, "<candidate>", "exec"), namespace)
    except Exception as exc:  # noqa: BLE001 - any failure to load is a review failure
        return 0, [f"code does not load: {type(exc).__name__}: {exc}"]
    fn = namespace.get(func)
    if not callable(fn):
        return 0, [f"no function named {func}()"]
    failures = []
    for ex in examples:
        try:
            got = fn(ex.given)
        except Exception as exc:  # noqa: BLE001
            got = f"<{type(exc).__name__}: {exc}>"
        if got != ex.expected:
            failures.append(f"{func}({ex.given!r}) returned {got!r}, expected {ex.expected!r}")
    if not (fn.__doc__ or "").strip():
        failures.append(f"{func}() has no docstring")
    return len(examples) + 1, failures


class Reviewer:
    name = "reviewer"
    description = "Executes the latest code against every acceptance example and reports failures."
    parallel_safe = True

    def __init__(self, timeout_s: float = 2.0) -> None:
        self.timeout_s = timeout_s

    async def run(self, instruction: str, state: SharedState) -> WorkerResult:
        if state.code is None:
            return WorkerResult(worker="reviewer", instruction=instruction, ok=False, summary="nothing to review")
        examples = state.research.examples if state.research else []
        if not examples:  # no evidence, no approval
            review = Review(version=state.code.version, passed=False, failures=["no acceptance examples to check"])
            return WorkerResult(worker="reviewer", instruction=instruction, review=review, ok=False,
                                summary=f"v{review.version} NOT REVIEWABLE: no acceptance examples")
        try:
            checked, failures = await asyncio.wait_for(
                asyncio.to_thread(run_examples, state.code.source, examples), self.timeout_s)
        except TimeoutError:
            checked, failures = 0, [f"review timed out after {self.timeout_s}s"]
        review = Review(version=state.code.version, passed=not failures, failures=failures, checked=checked)
        verdict = "PASSED" if review.passed else f"FAILED {len(failures)}/{checked}, e.g. {failures[0]}"
        return WorkerResult(worker="reviewer", instruction=instruction, review=review,
                            summary=f"v{review.version} {verdict}")
