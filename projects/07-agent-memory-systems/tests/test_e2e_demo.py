"""End-to-end: run the real demo the way a learner does and check the story it tells."""

import os
import subprocess
import sys
from pathlib import Path

from memory_agent import Settings

ROOT = Path(__file__).resolve().parents[1]


def run_demo(*args: str) -> str:
    env = {**os.environ, "LLM_PROVIDER": "mock", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("MEMORY_DB", None)
    result = subprocess.run([sys.executable, str(ROOT / "demo.py"), *args], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=60, check=True)
    return result.stdout


def test_demo_remembers_the_user_across_two_sessions(tmp_path):
    db = tmp_path / "memory.db"
    out = run_demo("--db", str(db))
    assert "DAY 1 - new user, empty memory" in out
    assert '~ updated #2 slot=city: "User lives in London" -> "User lives in Berlin"' in out
    day2 = out.split("DAY 2 - process restarted, same SQLite file", 1)[1]
    assert "= already known" in day2 and "User is vegetarian" in day2
    assert "vegetarian, no peanuts" in day2
    assert "You live in Berlin." in day2
    assert db.exists()


def test_settings_read_from_env_with_safe_defaults():
    assert Settings.from_env({}).llm_provider == "mock"
    custom = Settings.from_env({"LLM_PROVIDER": "OpenAI", "MEMORY_BUFFER_TOKENS": "99", "MEMORY_DB": "x.db"})
    assert (custom.llm_provider, custom.buffer_tokens, custom.memory_db) == ("openai", 99, Path("x.db"))
