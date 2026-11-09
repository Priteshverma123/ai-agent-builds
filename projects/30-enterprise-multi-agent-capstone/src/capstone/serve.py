"""ASGI entry point: uvicorn capstone.serve:app (used by the Dockerfile and `capstone serve`)."""
from __future__ import annotations

from capstone.api.app import create_app
from capstone.config import Settings
from capstone.container import build

settings = Settings.from_env()
app = create_app(build(trace_path=settings.trace_file, settings=settings))
