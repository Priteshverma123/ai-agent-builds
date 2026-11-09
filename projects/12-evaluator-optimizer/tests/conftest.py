import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_optimizer import Brief  # noqa: E402


@pytest.fixture
def brief() -> Brief:
    return Brief.from_dict(json.loads((ROOT / "examples" / "brief.json").read_text(encoding="utf-8")))
