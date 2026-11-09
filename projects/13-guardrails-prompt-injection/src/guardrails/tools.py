"""Sandboxed tools: a local fake web, the user's private notes and an outbox we can inspect."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Outputs of these tools come from third parties, so they are untrusted data.
UNTRUSTED_TOOLS = frozenset({"fetch_page"})


@dataclass
class ToolBox:
    web: dict[str, str]
    notes: str
    outbox: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def from_examples(cls, folder: Path) -> "ToolBox":
        index = json.loads((folder / "web" / "index.json").read_text(encoding="utf-8"))
        web = {url: (folder / "web" / name).read_text(encoding="utf-8") for url, name in index.items()}
        return cls(web=web, notes=(folder / "notes.txt").read_text(encoding="utf-8").strip())

    def fetch_page(self, url: str) -> str:
        return self.web.get(url, f"404: nothing at {url}")

    def read_notes(self) -> str:
        return self.notes

    def send_email(self, to: str, body: str) -> str:
        self.outbox.append({"to": to, "body": body})
        return f"email sent to {to}"

    def call(self, name: str, args: dict[str, Any]) -> str:
        handlers = {"fetch_page": self.fetch_page, "read_notes": self.read_notes, "send_email": self.send_email}
        if name not in handlers:
            return f"error: unknown tool {name!r}"
        try:
            return handlers[name](**args)
        except TypeError as exc:
            return f"error: bad arguments for {name}: {exc}"
