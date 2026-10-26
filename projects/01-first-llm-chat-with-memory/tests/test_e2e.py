"""End-to-end: the demo flow (CLI -> ChatSession -> ConversationMemory -> MockLLM) and the config layer."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from chat_memory.cli import main
from chat_memory.config import Settings
from chat_memory.llm import MockLLM, make_llm

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    for name in ("LLM_PROVIDER", "LLM_MODEL", "CHAT_BUDGET"):
        monkeypatch.delenv(name, raising=False)


def test_scripted_demo_remembers_then_forgets(capsys):
    main([])
    out = capsys.readouterr().out
    assert "model: MockLLM | budget: 140 tokens" in out
    assert "Your name is Priya." in out  # turn 4: name still in the window
    assert "scrolled out of my context" in out  # turn 7: name fell out
    assert 'fell out of the window: "I live in Pune."' in out
    assert "Full transcript: 14 messages. On the last turn the model saw only 9." in out


def test_big_budget_never_forgets(capsys):
    main(["--budget", "1000"])
    out = capsys.readouterr().out
    assert out.count("Your name is Priya.") == 2
    assert "scrolled out" not in out


def test_budget_comes_from_env(monkeypatch, capsys):
    monkeypatch.setenv("CHAT_BUDGET", "1000")
    main([])
    assert "budget: 1000 tokens" in capsys.readouterr().out


def test_settings_defaults_and_validation(monkeypatch):
    settings = Settings.from_env()
    assert settings == Settings(llm_provider="mock", llm_model=None, chat_budget=140)
    assert isinstance(make_llm(settings), MockLLM)
    assert settings.model_for("openai") == "gpt-4.1-mini"
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_demo_script_runs_as_a_subprocess():
    """`python demo.py` works from a clean checkout with no install and no env vars."""
    env = {k: v for k, v in os.environ.items() if k not in ("LLM_PROVIDER", "LLM_MODEL", "CHAT_BUDGET")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "demo.py"], cwd=PROJECT, capture_output=True, text=True, timeout=30, env=env
    )
    assert result.returncode == 0, result.stderr
    assert "That is AI 'forgetting'." in result.stdout
