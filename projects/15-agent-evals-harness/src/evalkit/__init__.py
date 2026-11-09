"""Agent evals: suites, graders, regression gates with CI exit codes."""

from .compare import Exit, compare, gate
from .runner import RunResult, run_suite
from .suite import Suite, load_suite

__version__ = "0.1.0"

__all__ = ["Exit", "RunResult", "Suite", "compare", "gate", "load_suite", "run_suite", "__version__"]
