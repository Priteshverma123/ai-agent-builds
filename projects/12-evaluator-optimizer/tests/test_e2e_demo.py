"""End-to-end: run demo.py as a learner does and check the draft climbs to the target score."""

import os
import re
import subprocess
import sys
from pathlib import Path

from eval_optimizer import Settings

ROOT = Path(__file__).resolve().parents[1]


def run_demo(**extra_env: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPT_")}
    env.update({"LLM_PROVIDER": "mock", "PYTHONDONTWRITEBYTECODE": "1", **extra_env})
    return subprocess.run([sys.executable, str(ROOT / "demo.py")], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=60, check=True).stdout


def test_demo_improves_the_draft_until_the_target_is_reached():
    out = run_demo()
    assert "target 90/100 | max 6 iterations" in out
    totals = [float(t) for t in re.findall(r"^\[score \]\s+\d+\s+([\d.]+)", out, re.MULTILINE)]
    assert len(totals) >= 2 and totals == sorted(totals) and totals[-1] >= 90
    assert "[fix   ] writer gets the top" in out
    assert "stopped: target reached" in out


def test_env_settings_change_the_loop_budget():
    out = run_demo(OPT_TARGET="101", OPT_MAX_ITERATIONS="2", OPT_PATIENCE="5")
    assert "stopped: max iterations (2) reached" in out


def test_settings_defaults():
    s = Settings.from_env({})
    assert (s.target, s.max_iterations, s.patience, s.min_delta, s.fixes_per_round) == (90.0, 6, 2, 1.0, 2)
