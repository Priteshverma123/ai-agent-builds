import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from support_agent.bootstrap import build_agent  # noqa: E402
from support_agent.config import Settings  # noqa: E402
from support_agent.evals import DEMO_TODAY  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(today=DEMO_TODAY, log_level="WARNING")


@pytest.fixture
def agent(settings):
    return build_agent(settings)
