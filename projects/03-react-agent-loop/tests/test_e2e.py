"""End-to-end: the demo flow (cli -> ReActAgent.run -> MockLLM -> parser -> tools) and the config layer."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from react_agent.cli import main
from react_agent.config import Settings
from react_agent.llm import MockLLM, make_llm

PROJECT = Path(__file__).resolve().parents[1]
SETTINGS_ENV = ("LLM_PROVIDER", "LLM_MODEL", "REACT_MAX_STEPS")


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_demo_runs_the_full_loop_on_every_question(capsys):
    main([])
    out = capsys.readouterr().out
    assert "03 - ReAct agent loop | model: MockLLM | tools: search, calculator" in out
    assert "action  : search[Golden Gate Bridge]" in out
    assert "action  : calculator[1937 - 1889]" in out
    assert "answer  : 48 years" in out
    assert "result    : answered in 4 step(s)" in out
    assert "No results for 'Atlantis'." in out
    assert "STOPPED" not in out


def test_step_limit_from_env_stops_the_agent(monkeypatch, capsys):
    monkeypatch.setenv("REACT_MAX_STEPS", "2")
    main(["How many years after the Eiffel Tower was completed did the Golden Gate Bridge open?"])
    assert "STOPPED: hit the 2-step limit without an answer" in capsys.readouterr().out


def test_settings_defaults_and_validation(monkeypatch):
    settings = Settings.from_env()
    assert settings == Settings(llm_provider="mock", llm_model=None, max_steps=6)
    assert isinstance(make_llm(settings), MockLLM)
    monkeypatch.setenv("REACT_MAX_STEPS", "zero")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_demo_script_runs_as_a_subprocess():
    """`python demo.py` works from a clean checkout with no install and no env vars."""
    env = {k: v for k, v in os.environ.items() if k not in SETTINGS_ENV}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "demo.py"], cwd=PROJECT, capture_output=True, text=True, timeout=30, env=env
    )
    assert result.returncode == 0, result.stderr
    assert "answered in 4 step(s)" in result.stdout
