"""12 - Evaluator-optimizer: a writer + critic loop with a rubric, scores and stop criteria."""

__version__ = "1.0.0"

from .config import Settings
from .llm import MockLLM, make_llm
from .optimizer import Attempt, EvaluatorOptimizer, OptimizeResult
from .rubric import Brief, Evaluation, Rubric, Score
from .trace import Trace

__all__ = [
    "Attempt", "Brief", "Evaluation", "EvaluatorOptimizer", "MockLLM", "OptimizeResult", "Rubric",
    "Score", "Settings", "Trace", "make_llm",
]
