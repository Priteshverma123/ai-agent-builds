from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gateway.adapters.clock import FakeClock
from gateway.api.app import create_app
from gateway.container import Container, build
from gateway.domain.models import ChatRequest, Plan, Tenant

ACME = "sk-acme-demo-0001"
HOBBY = "sk-hobby-demo-0002"
OPS = "sk-ops-admin-0003"


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def req(text: str = "What is a token bucket?", **kw) -> ChatRequest:
    return ChatRequest(messages=[{"role": "user", "content": text}], **kw)


def make_tenant(burst: int = 5, rpm: int = 60, budget: float = 1.0,
                models: tuple[str, ...] = ("alpha-fast", "beta-fast", "alpha-pro", "beta-pro")) -> Tenant:
    return Tenant("t1", "Test", Plan("test", rpm, burst, budget, models))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def container(clock: FakeClock) -> Container:
    return build(clock=clock)


@pytest.fixture
def client(container: Container) -> TestClient:
    return TestClient(create_app(container))
