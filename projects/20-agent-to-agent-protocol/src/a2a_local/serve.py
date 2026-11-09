"""Run several FastAPI agents on real localhost ports, in background threads (for the demo)."""

from __future__ import annotations

import socket
import threading
import time
from typing import Callable

import uvicorn
from fastapi import FastAPI


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LocalAgentServer:
    """Start ``build(url)`` on a free port; use as a context manager."""

    def __init__(self, build: Callable[[str], FastAPI]) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(build(self.url), host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "LocalAgentServer":
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError(f"agent on port {self.port} did not start")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)
