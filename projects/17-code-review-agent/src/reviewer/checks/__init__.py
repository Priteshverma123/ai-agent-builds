"""Static checks. Each is a function ReviewContext -> list[Finding]; add yours to ALL_CHECKS."""

from typing import Callable

from ..context import ReviewContext
from ..findings import Finding
from .lines import check_lines
from .project import check_change_size, check_tests_changed
from .python_ast import check_python

Check = Callable[[ReviewContext], list[Finding]]

ALL_CHECKS: tuple[Check, ...] = (check_lines, check_python, check_tests_changed, check_change_size)


def run_checks(ctx: ReviewContext, checks: tuple[Check, ...] = ALL_CHECKS) -> list[Finding]:
    return [finding for check in checks for finding in check(ctx)]
