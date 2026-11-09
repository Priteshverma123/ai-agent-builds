"""Per-tenant spend ceilings with a *hard* stop.

The naive version ("check spent < budget, then call the model, then add the cost") lets 50 concurrent
requests all pass the check and overspend together. Instead we RESERVE the worst-case cost before the
call, then COMMIT the actual cost (or RELEASE on failure). Reserved + spent can never exceed the budget.
"""
from __future__ import annotations

import itertools
import threading
from collections import defaultdict
from dataclasses import dataclass

from gateway.domain.errors import BudgetExceeded
from gateway.domain.models import Tenant


@dataclass(frozen=True)
class Reservation:
    id: int
    tenant_id: str
    amount: float


class BudgetLedger:
    def __init__(self) -> None:
        self._spent: dict[str, float] = defaultdict(float)
        self._reserved: dict[str, float] = defaultdict(float)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def reserve(self, tenant: Tenant, amount: float) -> Reservation:
        limit = tenant.plan.monthly_budget_usd
        with self._lock:
            committed = self._spent[tenant.id] + self._reserved[tenant.id]
            if committed + amount > limit + 1e-12:
                raise BudgetExceeded(
                    f"budget for '{tenant.id}' exhausted: spent ${self._spent[tenant.id]:.6f} of "
                    f"${limit:.6f}, this request may cost up to ${amount:.6f}")
            self._reserved[tenant.id] += amount
            return Reservation(next(self._ids), tenant.id, amount)

    def commit(self, reservation: Reservation, actual: float) -> None:
        with self._lock:
            self._reserved[reservation.tenant_id] -= reservation.amount
            self._spent[reservation.tenant_id] += min(actual, reservation.amount)

    def release(self, reservation: Reservation) -> None:
        with self._lock:
            self._reserved[reservation.tenant_id] -= reservation.amount

    def spent(self, tenant_id: str) -> float:
        with self._lock:
            return self._spent[tenant_id]

    def remaining(self, tenant: Tenant) -> float:
        with self._lock:
            used = self._spent[tenant.id] + self._reserved[tenant.id]
            return max(0.0, tenant.plan.monthly_budget_usd - used)
