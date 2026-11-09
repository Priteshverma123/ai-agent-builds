import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a2a_local import A2AClient, build_currency_agent, build_weather_agent  # noqa: E402

URL = "http://testserver"


@pytest.fixture
def fx():
    """An A2A client wired straight into the FX agent's ASGI app (no network)."""
    return A2AClient(URL, http=TestClient(build_currency_agent(URL)))


@pytest.fixture
def weather():
    return A2AClient(URL, http=TestClient(build_weather_agent(URL, work_seconds=0.1)))
