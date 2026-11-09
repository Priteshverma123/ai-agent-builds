import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from router_agent import MockRouterLLM, Router  # noqa: E402


@pytest.fixture
def router() -> Router:
    return Router.from_file(MockRouterLLM(), ROOT / "examples" / "intents.json", threshold=0.6)
