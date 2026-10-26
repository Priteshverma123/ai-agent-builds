"""End-to-end: the demo flow (cli -> agent.run -> MockLLM -> ToolRegistry -> answer) and the config layer."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from toolcall.cli import main
from toolcall.config import Settings
from toolcall.llm import MockLLM, make_llm

PROJECT = Path(__file__).resolve().parents[1]
SETTINGS_ENV = ("LLM_PROVIDER", "LLM_MODEL", "MAX_TOOL_ROUNDS")


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_demo_answers_every_question_with_tools(capsys):
    main([])
    out = capsys.readouterr().out
    assert "02 - Tool calling from scratch | model: MockLLM" in out
    assert '"name": "get_weather"' in out  # the schema the model sees is printed
    assert 'get_weather({"city": "Paris"})' in out and 'get_weather({"city": "Tokyo"})' in out
    assert "Paris: 18 C and cloudy. Tokyo: 24 C and sunny." in out
    assert "250.00 USD = 230.00 EUR (rate 0.92)." in out
    assert "17 * 23 + 4 = 395." in out
    assert "error <-" in out  # an unknown city becomes an error result, not a crash
    assert out.count("model call(s)") == 5


def test_own_question_and_round_limit_from_env(monkeypatch, capsys):
    monkeypatch.setenv("MAX_TOOL_ROUNDS", "1")
    main(["What's the weather in London?"])
    out = capsys.readouterr().out
    assert "Q1 | 1 model call(s)" in out
    assert "[stopped: too many tool rounds]" in out


def test_settings_defaults_and_validation(monkeypatch):
    settings = Settings.from_env()
    assert settings == Settings(llm_provider="mock", llm_model=None, max_rounds=5)
    assert isinstance(make_llm(settings), MockLLM)
    monkeypatch.setenv("LLM_PROVIDER", "nope")
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
    assert "Q5 | 1 model call(s)" in result.stdout
