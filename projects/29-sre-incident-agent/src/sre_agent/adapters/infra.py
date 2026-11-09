"""A pretend production environment that mutating runbook steps act on.

It encodes the scenario's ground truth: checkout-api v2.14.0 opens 100 DB connections per pod and exhausts
payments-db. Only rolling back fixes it; restarting pods or raising max_connections just moves the pain.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BAD_VERSION = "v2.14.0"


@dataclass
class MockInfra:
    versions: dict[str, str] = field(default_factory=lambda: {
        "checkout-api": BAD_VERSION, "inventory-api": "v3.1.0", "payments-db": "pg-15.4"})
    replicas: dict[str, int] = field(default_factory=lambda: {"checkout-api": 6, "inventory-api": 4})
    max_connections: dict[str, int] = field(default_factory=lambda: {"payments-db": 200})
    frozen: set[str] = field(default_factory=set)
    restarts: dict[str, int] = field(default_factory=dict)
    changes: list[str] = field(default_factory=list)

    # ---------------------------------------------------------- mutations
    def freeze_deploys(self, service: str) -> str:
        self.frozen.add(service)
        self.changes.append(f"deploy freeze on {service}")
        return f"deploys to {service} frozen"

    def restart(self, service: str) -> str:
        self.restarts[service] = self.restarts.get(service, 0) + 1
        self.changes.append(f"restart {service}")
        return f"{service}: {self.replicas.get(service, 1)} pods restarted"

    def rollback(self, service: str, to_version: str) -> str:
        before = self.versions[service]
        self.versions[service] = to_version
        self.changes.append(f"rollback {service} {before} -> {to_version}")
        return f"{service} rolled back {before} -> {to_version}"

    def set_max_connections(self, service: str, value: int) -> str:
        self.max_connections[service] = value
        self.changes.append(f"{service} max_connections -> {value}")
        return f"{service} max_connections set to {value}"

    def scale(self, service: str, replicas: int) -> str:
        self.replicas[service] = replicas
        self.changes.append(f"scale {service} -> {replicas}")
        return f"{service} scaled to {replicas} replicas"

    # ---------------------------------------------------------- live health
    def health(self, service: str) -> dict[str, float]:
        """Current p95 latency and error rate as they would look right now."""
        if service != "checkout-api" or self.versions["checkout-api"] != BAD_VERSION:
            return {"latency_p95_ms": 184.0, "error_rate_pct": 0.4}
        # More pods or more DB connections means *more* pool contention with the bad config.
        pressure = self.replicas["checkout-api"] / 6 * (self.max_connections["payments-db"] / 200) ** 0.5
        return {"latency_p95_ms": round(930 * pressure, 1), "error_rate_pct": round(11.4 * pressure, 1)}
