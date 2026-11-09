"""End-to-end: the real demo (two uvicorn servers on free ports + the planner), as a learner runs it."""

import os
import subprocess
import sys

from a2a_local.cli import REQUEST, agent_builders, run_demo
from a2a_local.config import Settings, load_settings
from conftest import ROOT


def test_demo_script_runs_over_real_http():
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}  # force the offline MockLLM
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for expected in ("1. DISCOVERY", "card: FX Desk v1.0.0", "[input-required]: Which dollars",
                     "the answer is: CAD", "500 CAD = 54,562 JPY", "Tokyo in April: 19C / 10C",
                     "3. WHAT THE PROTOCOL GUARANTEES"):
        assert expected in out


def test_run_demo_returns_the_planners_answer(capsys):
    answer = run_demo(REQUEST, Settings(weather_work_seconds=0.05))
    assert answer.startswith("Here's your trip brief: 500 CAD = 54,562 JPY")
    assert "(slow: ~0.05 s per task)" in capsys.readouterr().out


def test_settings_from_env():
    assert load_settings({}) == Settings()
    s = load_settings({"LLM_PROVIDER": "OpenAI", "WEATHER_WORK_SECONDS": "0", "A2A_PORT": "9000"})
    assert (s.llm_provider, s.model, s.weather_work_seconds, s.port) == ("openai", "gpt-4.1-mini", 0.0, 9000)
    assert set(agent_builders(s)) == {"fx", "weather"}
