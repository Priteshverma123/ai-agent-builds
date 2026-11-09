"""Run the real HTTP server: `gateway serve`, `python -m gateway.serve` (from src/), or uvicorn gateway.serve:app."""
from __future__ import annotations

import uvicorn

from gateway.api.app import create_app
from gateway.config import Settings

app = create_app()

if __name__ == "__main__":
    settings = Settings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)
