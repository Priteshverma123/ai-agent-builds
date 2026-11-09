import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from browser_agent import Browser, FileSite, ShopSite  # noqa: E402


@pytest.fixture
def shop():
    return ShopSite()


@pytest.fixture
def browser(shop):
    return Browser(shop)


@pytest.fixture
def static_browser():
    return Browser(FileSite(ROOT / "examples" / "static"))


def ref_of(snapshot: str, role: str, name: str) -> str:
    """Helper for tests: find the ref of ``role "name"`` in a snapshot."""
    for line in snapshot.splitlines():
        if f'- {role} "{name}"' in line and "[ref=" in line:
            return line.split("[ref=")[1].split("]")[0]
    raise AssertionError(f'{role} "{name}" not in snapshot:\n{snapshot}')
