"""The outside world: services our agent has side effects on.

They live in their own SQLite file because the outside world does not crash when our worker
does. The email and CRM services accept an **idempotency key**, like Stripe's or most payment
APIs: the same key twice returns the original receipt instead of doing the work again. That is
what makes "re-run the step that was interrupted" safe.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from pathlib import Path

WORLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    idempotency_key TEXT PRIMARY KEY,
    message_id      TEXT NOT NULL,
    recipient       TEXT NOT NULL,
    subject         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS crm_notes (
    idempotency_key TEXT PRIMARY KEY,
    account         TEXT NOT NULL,
    note            TEXT NOT NULL
);
"""

TICKETS = {
    "acme": [
        {"id": "T-101", "title": "Billing export fails for March", "status": "open", "priority": "high"},
        {"id": "T-102", "title": "Add SSO for new team", "status": "resolved", "priority": "medium"},
        {"id": "T-103", "title": "Typo in invoice footer", "status": "resolved", "priority": "low"},
    ],
}


class TransientError(RuntimeError):
    """A failure worth retrying: timeouts, 429s, 503s."""


class PermanentError(RuntimeError):
    """A failure retries won't fix: bad input, 404, permission denied."""


class World:
    def __init__(self, path: Path, ticket_failures: int = 2) -> None:
        self.conn = sqlite3.connect(Path(path), isolation_level=None)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.conn.executescript(WORLD_SCHEMA)
        self.ticket_failures = ticket_failures  # the ticket API is flaky for the first N calls
        self.ticket_calls = 0

    async def fetch_tickets(self, account: str) -> list[dict]:
        """Read-only and flaky. Safe to retry any number of times."""
        await asyncio.sleep(0.01)
        self.ticket_calls += 1
        if self.ticket_calls <= self.ticket_failures:
            raise TransientError("503 from ticket API")
        if account not in TICKETS:
            raise PermanentError(f"unknown account {account!r}")
        return TICKETS[account]

    async def send_email(self, recipient: str, subject: str, body: str, idempotency_key: str) -> dict:
        """Send once per key. A repeated key returns the original receipt, marked ``duplicate``."""
        await asyncio.sleep(0.01)
        row = self.conn.execute("SELECT message_id FROM emails WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if row:
            return {"message_id": row[0], "duplicate": True}
        message_id = "msg-" + hashlib.sha1(idempotency_key.encode()).hexdigest()[:8]
        self.conn.execute("INSERT INTO emails VALUES (?, ?, ?, ?)", (idempotency_key, message_id, recipient, subject))
        return {"message_id": message_id, "duplicate": False}

    async def add_crm_note(self, account: str, note: str, idempotency_key: str) -> dict:
        await asyncio.sleep(0.01)
        cursor = self.conn.execute("INSERT OR IGNORE INTO crm_notes VALUES (?, ?, ?)", (idempotency_key, account, note))
        return {"account": account, "duplicate": cursor.rowcount == 0}

    def emails_sent(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]

    def crm_notes(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM crm_notes").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
