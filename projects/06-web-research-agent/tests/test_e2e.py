"""End-to-end: the demo flow (cli -> ResearchAgent.run -> LocalWeb search/fetch -> MockResearchLLM ->
SourceTracker citation check -> brief) and the config layer."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from research_agent import MockResearchLLM, ResearchConfig, Settings, make_llm
from research_agent.cli import research
from research_agent.config import EXAMPLES_DIR
from research_agent.sources import CITATION

PROJECT = Path(__file__).resolve().parents[1]
SETTINGS_ENV = (
    "LLM_PROVIDER", "LLM_MODEL", "RESEARCH_WEB_DIR", "RESEARCH_RESULTS_PER_QUERY", "RESEARCH_MAX_FETCHES",
)


@pytest.fixture(autouse=True)
def offline_env(monkeypatch):
    for name in SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)


def test_demo_plans_searches_reads_and_writes_a_cited_brief(capsys):
    brief = research([])
    out = capsys.readouterr().out
    assert "Q: Are heat pumps worth it in cold climates?" in out
    assert "model: mock | budget: 5 fetches" in out
    assert "[think ] plan -> 3 search queries" in out
    assert '[tool  ] search("heat pump cold climate evidence study")' in out
    assert "[read  ] fetch https://coldclimate-lab.example.org/field-study-2025" in out
    assert "[check ] citations verified:" in out
    assert "RESEARCH BRIEF" in out and "Contested claims" in out
    assert brief.fetched == 5
    cited = {int(n) for n in CITATION.findall(brief.text)}
    assert cited == set(range(1, len(brief.bibliography) + 1))


def test_budget_from_env_and_flag(monkeypatch, capsys):
    monkeypatch.setenv("RESEARCH_MAX_FETCHES", "2")
    assert research([]).fetched == 2
    assert research(["--max-fetches", "3", "heat", "pump", "cost"]).fetched == 3
    out = capsys.readouterr().out
    assert "budget reached" in out
    assert "Q: heat pump cost" in out


def test_settings_defaults_and_validation(monkeypatch):
    settings = Settings.from_env()
    assert settings == Settings(
        llm_provider="mock", llm_model=None, web_dir=EXAMPLES_DIR / "web", results_per_query=2, max_fetches=5
    )
    assert settings.research_config() == ResearchConfig()
    assert isinstance(make_llm(settings), MockResearchLLM)
    monkeypatch.setenv("RESEARCH_MAX_FETCHES", "-1")
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
    assert "RESEARCH BRIEF" in result.stdout
