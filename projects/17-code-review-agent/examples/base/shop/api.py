"""HTTP handlers."""

import json


def health() -> dict:
    return {"ok": True}


def parse_body(raw: bytes) -> dict:
    return json.loads(raw)
