"""A tamper-evident audit log: append-only JSONL where each entry hashes the one before it.

Editing or deleting any past line breaks every hash after it, and `verify()` says where.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

GENESIS = "0" * 16


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


class AuditLog:
    def __init__(self, path: Path, clock: Callable[[], str] = utc_now) -> None:
        self.path, self.clock = path, clock
        path.parent.mkdir(parents=True, exist_ok=True)

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def append(self, event: str, run_id: str, **data: Any) -> dict[str, Any]:
        previous = self.entries()
        entry = {
            "seq": len(previous) + 1, "at": self.clock(), "run_id": run_id, "event": event, "data": data,
            "prev": previous[-1]["hash"] if previous else GENESIS,
        }
        entry["hash"] = _digest(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self) -> tuple[bool, str]:
        prev = GENESIS
        for entry in self.entries():
            if entry["prev"] != prev:
                return False, f"chain broken before entry {entry['seq']}"
            if _digest(entry) != entry["hash"]:
                return False, f"entry {entry['seq']} was modified"
            prev = entry["hash"]
        return True, "audit chain intact"
