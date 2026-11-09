"""What the agent knows so far. The LLM reads this to decide; tools fill it in."""
from __future__ import annotations

from dataclasses import dataclass, field

from sre_agent.domain.models import (Action, ActionRecord, Alert, Anomaly, Deploy, ErrorSignature,
                                     Hypothesis)


@dataclass
class AgentState:
    alert: Alert
    anomalies: list[Anomaly] | None = None
    signatures: list[ErrorSignature] | None = None
    deploys: list[Deploy] | None = None
    hypotheses: list[Hypothesis] | None = None
    runbook_title: str = ""
    plan: list[Action] = field(default_factory=list)   # remaining runbook steps
    records: list[ActionRecord] = field(default_factory=list)
    verified: bool | None = None
    paged: bool = False
    status: str = "investigating"

    @property
    def first_anomaly(self) -> Anomaly | None:
        return min(self.anomalies, key=lambda a: a.start) if self.anomalies else None

    @property
    def top_hypothesis(self) -> Hypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    def denied(self) -> list[ActionRecord]:
        return [r for r in self.records if r.status == "denied"]
