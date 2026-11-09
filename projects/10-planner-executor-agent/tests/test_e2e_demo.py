"""End-to-end: run demo.py as a learner does and check the plan -> fail -> re-plan -> done story."""

import os
import subprocess
import sys
from pathlib import Path

from planner_executor import Settings

ROOT = Path(__file__).resolve().parents[1]


def run_demo(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "LLM_PROVIDER": "mock", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("AGENT_MAX_REPLANS", None)
    return subprocess.run([sys.executable, str(ROOT / "demo.py"), *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60)


def test_demo_replans_around_the_sold_out_hotel():
    proc = run_demo()
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "[plan  ] v1  (5 steps)" in out
    assert "[FAIL  ] s4" in out and "Alfama Patio Hotel is sold out" in out
    assert "plan v1 -> v2" in out
    assert "status: DONE" in out
    assert "Booked: TAP 07:05; Baixa House x2 nights  |  total 378 EUR" in out


def test_cli_reports_an_unrecoverable_goal_with_exit_code_1():
    proc = run_demo("--goal", "Book a 2-night trip from London to Atlantis for 2026-11-12, email a@b.co")
    assert proc.returncode == 1
    assert "status: ABORTED" in proc.stdout


def test_settings_defaults_and_overrides():
    assert Settings.from_env({}).max_replans == 2
    assert Settings.from_env({"AGENT_MAX_REPLANS": "5", "LLM_PROVIDER": "OPENAI"}).llm_provider == "openai"
