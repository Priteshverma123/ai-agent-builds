from __future__ import annotations

from pathlib import Path

import pytest

from sre_agent.adapters.approval import ScriptedApprover
from sre_agent.adapters.infra import MockInfra
from sre_agent.adapters.llm import MockLLM
from sre_agent.adapters.telemetry import FileTelemetry, load_alert
from sre_agent.domain.models import Decision
from sre_agent.services.agent import IncidentAgent

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(scope="session")
def telemetry() -> FileTelemetry:
    return FileTelemetry(EXAMPLES / "incident")


@pytest.fixture
def alert():
    return load_alert(EXAMPLES / "alert.json")


def make_agent(telemetry: FileTelemetry, answers: dict[str, bool], infra: MockInfra | None = None,
               events: list | None = None) -> tuple[IncidentAgent, ScriptedApprover, MockInfra]:
    approver = ScriptedApprover({k: Decision(v, "tester", "ok" if v else "no") for k, v in answers.items()})
    infra = infra or MockInfra()
    hook = (lambda kind, data: events.append((kind, data))) if events is not None else None
    return IncidentAgent(MockLLM(), telemetry, infra, approver, EXAMPLES / "runbooks.json", hook), approver, infra
