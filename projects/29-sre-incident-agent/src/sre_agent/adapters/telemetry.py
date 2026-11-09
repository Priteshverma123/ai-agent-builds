"""Read-only telemetry from files: metrics, logs, deploy history and the service map.

In production these would be Prometheus/Datadog, Loki/Elastic and your CD system. The interface is the same.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sre_agent.domain.models import Alert, Deploy, LogEvent, Series, parse_ts

LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}


class FileTelemetry:
    def __init__(self, folder: Path) -> None:
        folder = Path(folder)
        metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
        start, step = parse_ts(metrics["start"]), metrics["resolution_s"]
        self._series = {name: Series(name, start, step, tuple(values))
                        for name, values in metrics["series"].items()}
        self._logs = [LogEvent(parse_ts(e["ts"]), e["service"], e["level"], e["message"])
                      for e in map(json.loads, (folder / "logs.jsonl").read_text(encoding="utf-8").splitlines())]
        self._deploys = [Deploy(d["id"], d["service"], d["version"], d["previous_version"], parse_ts(d["ts"]),
                                d["change"], d["pr"])
                         for d in json.loads((folder / "deploys.json").read_text(encoding="utf-8"))]
        self.services: dict[str, dict] = json.loads((folder / "services.json").read_text(encoding="utf-8"))

    def series(self, name: str) -> Series:
        return self._series[name]

    def all_series(self) -> list[Series]:
        return list(self._series.values())

    def logs(self, since: datetime | None = None, until: datetime | None = None,
             service: str | None = None, min_level: str = "INFO") -> list[LogEvent]:
        floor = LEVELS[min_level]
        return [e for e in self._logs
                if (since is None or e.ts >= since) and (until is None or e.ts <= until)
                and (service is None or e.service == service) and LEVELS.get(e.level, 0) >= floor]

    def deploys(self, since: datetime | None = None, until: datetime | None = None) -> list[Deploy]:
        return [d for d in self._deploys
                if (since is None or d.ts >= since) and (until is None or d.ts <= until)]

    def dependencies(self, service: str) -> list[str]:
        return self.services.get(service, {}).get("depends_on", [])

    def slo(self, service: str) -> dict[str, float]:
        return self.services.get(service, {}).get("slo", {})


def load_alert(path: Path) -> Alert:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Alert(data["id"], parse_ts(data["fired_at"]), data["service"], data["rule"])
