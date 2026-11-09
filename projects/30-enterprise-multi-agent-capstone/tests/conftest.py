from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from capstone.adapters.llm import MockLLM
from capstone.api.app import create_app
from capstone.container import System, build

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "examples" / "docs"


@pytest.fixture
def system() -> System:
    return build(DOCS, llm=MockLLM())


@pytest.fixture
def client(system: System) -> TestClient:
    return TestClient(create_app(system))
