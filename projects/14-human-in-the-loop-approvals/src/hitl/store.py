"""Run checkpoints. A paused run is just a JSON file, so it survives restarts and can wait for days."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .approvals import ApprovalRequest


@dataclass
class RunState:
    id: str
    task: str
    requested_by: str
    status: str = "running"  # running | waiting_approval | done | failed
    messages: list[dict[str, str]] = field(default_factory=list)
    step: int = 0
    pending: ApprovalRequest | None = None
    in_flight: dict[str, Any] | None = None  # an action we committed to run but haven't recorded yet
    answer: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = dict(vars(self))
        data["pending"] = self.pending.to_dict() if self.pending else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunState":
        pending = ApprovalRequest.from_dict(data["pending"]) if data.get("pending") else None
        return cls(**{**data, "pending": pending})


class RunStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def path(self, run_id: str) -> Path:
        return self.folder / f"{run_id}.json"

    def save(self, state: RunState) -> None:
        """Write atomically: a crash mid-write leaves the previous checkpoint, never half a file."""
        tmp = self.path(state.id).with_suffix(".tmp")
        tmp.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, self.path(state.id))

    def load(self, run_id: str) -> RunState:
        return RunState.from_dict(json.loads(self.path(run_id).read_text(encoding="utf-8")))

    def all(self) -> list[RunState]:
        return [self.load(p.stem) for p in sorted(self.folder.glob("*.json"))]
