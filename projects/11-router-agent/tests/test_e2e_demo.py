"""End-to-end: run demo.py as a learner does: six routed messages plus the eval report."""

import os
import subprocess
import sys
from pathlib import Path

from router_agent import Settings

ROOT = Path(__file__).resolve().parents[1]


def run_demo(*args: str) -> str:
    env = {**os.environ, "LLM_PROVIDER": "mock", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("ROUTER_THRESHOLD", None)
    return subprocess.run([sys.executable, str(ROOT / "demo.py"), *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60, check=True).stdout


def test_demo_routes_samples_and_prints_the_eval():
    out = run_demo()
    assert "threshold: 0.6 | specialists: billing, tech_support, sales + fallback" in out
    assert "[route ] billing" in out and "via rule" in out
    assert "(fallback) I can help with that. Is this mainly about billing or tech support?" in out
    assert "(fallback) I'm not sure I can help with that." in out
    assert "ROUTER EVAL  accuracy" in out


def test_demo_with_a_custom_message_skips_the_eval():
    out = run_demo("I want a refund please")
    assert "[route ] billing" in out
    assert "ROUTER EVAL" not in out


def test_settings_defaults_and_overrides():
    assert Settings.from_env({}).threshold == 0.6
    assert Settings.from_env({"ROUTER_THRESHOLD": "0.8"}).threshold == 0.8
