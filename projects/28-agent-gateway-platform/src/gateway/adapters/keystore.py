"""Tenant + API-key storage. Keys are kept only as SHA-256 digests, never in plain text."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from gateway.domain.errors import Unauthorized
from gateway.domain.models import Plan, Tenant


def hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class KeyStore:
    """Maps hashed API keys to tenants."""

    def __init__(self) -> None:
        self._by_hash: dict[str, Tenant] = {}
        self._tenants: dict[str, Tenant] = {}

    def add(self, tenant: Tenant, api_key: str) -> None:
        self._tenants[tenant.id] = tenant
        self._by_hash[hash_key(api_key)] = tenant

    def authenticate(self, api_key: str | None) -> Tenant:
        """Look up by digest: the raw key is never compared or stored."""
        if not api_key:
            raise Unauthorized("missing API key")
        tenant = self._by_hash.get(hash_key(api_key))
        if tenant is None:
            raise Unauthorized("unknown API key")
        return tenant

    def tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def tenants(self) -> list[Tenant]:
        return list(self._tenants.values())

    @classmethod
    def from_file(cls, path: Path) -> "KeyStore":
        """Load plans and tenants from JSON (see examples/tenants.json)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        plans = {
            name: Plan(
                name=name,
                requests_per_minute=p["requests_per_minute"],
                burst=p["burst"],
                monthly_budget_usd=p["monthly_budget_usd"],
                allowed_models=tuple(p["allowed_models"]),
            )
            for name, p in data["plans"].items()
        }
        store = cls()
        for t in data["tenants"]:
            tenant = Tenant(id=t["id"], name=t["name"], plan=plans[t["plan"]], is_admin=t.get("admin", False))
            for key in t["api_keys"]:
                store.add(tenant, key)
        return store
