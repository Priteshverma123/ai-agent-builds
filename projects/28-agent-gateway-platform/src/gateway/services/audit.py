"""Tamper-evident audit log.

Every entry stores the hash of the previous entry, so editing or deleting any line breaks the chain
from that point on (the same idea a git history or a ledger uses). Prompts are never stored, only a
SHA-256 fingerprint, because audit logs are read by many more people than the data they describe.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _entry_hash(prev_hash: str, body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self._entries: list[dict[str, Any]] = []
        self._path = path
        self._lock = threading.Lock()

    def append(self, event: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            prev = self._entries[-1]["hash"] if self._entries else GENESIS
            body = {"seq": len(self._entries) + 1, "event": event, **fields}
            entry = {**body, "prev_hash": prev, "hash": _entry_hash(prev, body)}
            self._entries.append(entry)
            if self._path:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
            return entry

    def entries(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._entries)
        return [e for e in rows if tenant_id is None or e.get("tenant") == tenant_id]

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the chain. Returns (ok, first_bad_seq)."""
        prev = GENESIS
        for entry in self.entries():
            body = {k: v for k, v in entry.items() if k not in ("prev_hash", "hash")}
            if entry["prev_hash"] != prev or _entry_hash(prev, body) != entry["hash"]:
                return False, entry["seq"]
            prev = entry["hash"]
        return True, None
