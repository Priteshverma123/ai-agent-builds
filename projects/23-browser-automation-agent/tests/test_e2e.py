"""End-to-end: the demo flow (goal -> snapshot -> tool calls -> placed order) as a learner runs it."""

import os
import subprocess
import sys

from browser_agent.cli import GOAL, main, run
from browser_agent.config import Settings, load_settings
from conftest import ROOT


def test_demo_script_places_the_order_offline():
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}  # force the offline MockLLM
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for expected in ("model: mock", 'searchbox "Search products"', "(HTTP 422)", "Order A1001: $24.00",
                     "SERVER SIDE: what the shop actually received", "terms accepted: yes"):
        assert expected in out


def test_run_returns_answer_and_the_server_side_order(capsys):
    answer, site = run(GOAL, Settings(), max_steps=25)
    assert "Order A1001: $24.00" in answer
    assert site.orders[0]["items"] == {"MUG-BLUE": 2}
    assert "[answer]" in capsys.readouterr().out


def test_cli_step_budget_stops_without_ordering(capsys):
    assert main(["--max-steps", "2"]) == 0
    out = capsys.readouterr().out
    assert "Stopped after 2 steps without finishing." in out and "SERVER SIDE" not in out


def test_settings_from_env():
    assert load_settings({}) == Settings()
    s = load_settings({"LLM_PROVIDER": "Anthropic", "AGENT_MAX_STEPS": "7", "LLM_MODEL": "claude-x"})
    assert (s.llm_provider, s.llm_model, s.max_steps) == ("anthropic", "claude-x", 7)
