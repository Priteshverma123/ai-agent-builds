"""Domain objects for incident response. Plain data, no I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def hhmm(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%H:%M")


class Risk(str, Enum):
    """How bad is it if this step is wrong? Drives the approval prompt and the audit trail."""

    NONE = "none"      # read-only
    LOW = "low"        # reversible, small blast radius
    MEDIUM = "medium"  # user-visible blip possible
    HIGH = "high"      # changes production behaviour for everyone


# ---------------------------------------------------------------- telemetry
@dataclass(frozen=True)
class Alert:
    id: str
    fired_at: datetime
    service: str
    rule: str


@dataclass(frozen=True)
class LogEvent:
    ts: datetime
    service: str
    level: str
    message: str


@dataclass(frozen=True)
class Deploy:
    id: str
    service: str
    version: str
    previous_version: str
    ts: datetime
    change: str
    pr: str


@dataclass(frozen=True)
class Series:
    name: str          # "<service>.<metric>"
    start: datetime
    step_s: int
    values: tuple[float, ...]

    @property
    def service(self) -> str:
        return self.name.split(".", 1)[0]

    @property
    def metric(self) -> str:
        return self.name.split(".", 1)[1]

    def ts_at(self, index: int) -> datetime:
        return self.start + timedelta(seconds=self.step_s * index)


# ---------------------------------------------------------------- analysis
@dataclass(frozen=True)
class Anomaly:
    series: str
    start: datetime
    baseline: float
    peak: float
    z_score: float

    @property
    def service(self) -> str:
        return self.series.split(".", 1)[0]

    @property
    def change_pct(self) -> float:
        return (self.peak - self.baseline) / abs(self.baseline) * 100 if self.baseline else float("inf")


@dataclass(frozen=True)
class ErrorSignature:
    service: str
    template: str      # message with numbers replaced by <n>
    count: int
    first_seen: datetime


@dataclass(frozen=True)
class Evidence:
    text: str
    weight: float      # positive supports the hypothesis, negative argues against it


@dataclass
class Hypothesis:
    kind: str          # matches a runbook key: bad_deploy | dependency_saturation | traffic_surge
    title: str
    params: dict[str, str]
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def score(self) -> float:
        return round(max(0.0, min(1.0, sum(e.weight for e in self.evidence))), 2)


# ---------------------------------------------------------------- actions
@dataclass(frozen=True)
class Action:
    """What the LLM decided to do next."""

    thought: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalRequest:
    tool: str
    args: dict[str, Any]
    risk: Risk
    preview: str
    why: str


@dataclass(frozen=True)
class Decision:
    approved: bool
    approver: str
    reason: str = ""


@dataclass(frozen=True)
class ActionRecord:
    ts: datetime
    tool: str
    args: dict[str, Any]
    risk: Risk
    status: str        # executed | denied | failed
    summary: str
    approver: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TimelineEntry:
    ts: datetime
    kind: str          # change | detection | symptom | action | decision | resolution
    text: str
