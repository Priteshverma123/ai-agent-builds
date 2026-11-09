"""Usage metering: the numbers you bill from and the numbers customers see on GET /v1/usage."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field


@dataclass
class ModelUsage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class TenantUsage:
    requests: int = 0
    cached_hits: int = 0
    rejected: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    by_model: dict[str, ModelUsage] = field(default_factory=lambda: defaultdict(ModelUsage))


class UsageMeter:
    def __init__(self) -> None:
        self._usage: dict[str, TenantUsage] = defaultdict(TenantUsage)
        self._lock = threading.Lock()

    def record_success(self, tenant_id: str, model: str, input_tokens: int, output_tokens: int,
                       cost_usd: float, cached: bool) -> None:
        with self._lock:
            u = self._usage[tenant_id]
            u.requests += 1
            if cached:
                u.cached_hits += 1
                return
            u.input_tokens += input_tokens
            u.output_tokens += output_tokens
            u.cost_usd += cost_usd
            m = u.by_model[model]
            m.requests += 1
            m.input_tokens += input_tokens
            m.output_tokens += output_tokens
            m.cost_usd += cost_usd

    def record_rejection(self, tenant_id: str, code: str) -> None:
        with self._lock:
            self._usage[tenant_id].rejected[code] += 1

    def snapshot(self, tenant_id: str) -> dict:
        with self._lock:
            data = asdict(self._usage[tenant_id])
        data["cost_usd"] = round(data["cost_usd"], 8)
        data["rejected"] = dict(data["rejected"])
        data["by_model"] = {k: {**v, "cost_usd": round(v["cost_usd"], 8)} for k, v in data["by_model"].items()}
        return data
