"""End-to-end: the demo flow runs exactly as a learner (or the Docker image) would run it."""

import os
import subprocess
import sys
from pathlib import Path

from supervisor.cli import main
from supervisor.config import Settings, load_settings
from supervisor.llm import MockSupervisorLLM, llm_from_env

ROOT = Path(__file__).resolve().parents[1]


def test_demo_script_runs_offline_and_ships_approved_code():
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLM_")}  # force the offline MockLLM
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for expected in ("MULTI-AGENT SUPERVISOR", "researcher x2 in parallel", "v1 FAILED", "v2 PASSED",
                     "status : APPROVED", "def slugify"):
        assert expected in out


def test_cli_main_respects_step_budget(capsys):
    assert main(["--max-steps", "2"]) == 1  # research + v1 only: never reviewed, so not approved
    assert "status : INCOMPLETE" in capsys.readouterr().out


def test_settings_load_from_env_with_safe_defaults():
    assert load_settings({}) == Settings()
    s = load_settings({"LLM_PROVIDER": " Anthropic ", "LLM_MODEL": "", "SUPERVISOR_MAX_STEPS": "3"})
    assert (s.llm_provider, s.llm_model, s.max_steps, s.use_mock) == ("anthropic", None, 3, False)
    mock = MockSupervisorLLM()
    assert llm_from_env(mock, load_settings({"LLM_PROVIDER": "mock"})) is mock
