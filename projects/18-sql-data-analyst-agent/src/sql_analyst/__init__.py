"""Natural language -> safe, read-only SQL over SQLite, with schema grounding and chart-ready output."""

from .agent import Answer, SQLAnalyst
from .db import ReadOnlyDatabase, build_demo_db
from .guard import InvalidSQL, UnsafeSQL, check_sql

__version__ = "0.1.0"

__all__ = [
    "Answer", "SQLAnalyst", "ReadOnlyDatabase", "build_demo_db", "InvalidSQL", "UnsafeSQL", "check_sql", "__version__",
]
