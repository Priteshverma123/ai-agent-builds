import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from intake.config import ClientConfig  # noqa: E402

EXAMPLES = ROOT / "examples"


@pytest.fixture
def cfg() -> ClientConfig:
    return ClientConfig.load(EXAMPLES / "clients" / "northwind.json")
