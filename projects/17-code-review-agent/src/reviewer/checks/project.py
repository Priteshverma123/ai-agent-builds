"""Change-level checks: things you only see by looking at the whole diff."""

from __future__ import annotations

from pathlib import PurePosixPath

from ..context import ReviewContext
from ..findings import Finding, Severity

MAX_ADDED_LINES = 400


def check_tests_changed(ctx: ReviewContext) -> list[Finding]:
    """Each changed source module should come with a change to its test module."""
    changed_tests = {PurePosixPath(f.path).name for f in ctx.files if f.is_test}
    findings = []
    for f in ctx.files:
        if not f.is_python or f.is_test or not f.added or PurePosixPath(f.path).name == "__init__.py":
            continue
        expected = f"test_{PurePosixPath(f.path).name}"
        if expected not in changed_tests:
            findings.append(Finding("missing-tests", Severity.MEDIUM, 0.7, f.path, min(f.added),
                                    f"{f.path} changed but no {expected} was added or updated.",
                                    f"Add tests in tests/{expected} for the new behaviour."))
    return findings


def check_change_size(ctx: ReviewContext) -> list[Finding]:
    added = sum(len(f.added) for f in ctx.files)
    if added <= MAX_ADDED_LINES or not ctx.files:
        return []
    first = ctx.files[0]
    return [Finding("large-change", Severity.LOW, 1.0, first.path, min(first.added or {1: ""}),
                    f"{added} added lines; large changes get shallow reviews.", "Split into smaller PRs.")]
