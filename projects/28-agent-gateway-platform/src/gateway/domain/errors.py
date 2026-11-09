"""Typed failures. Each gateway error knows its HTTP status, so the API layer stays a thin mapper."""
from __future__ import annotations


class GatewayError(Exception):
    """Base class for errors that are returned to the client."""

    status: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers or {}


class Unauthorized(GatewayError):
    status, code = 401, "invalid_api_key"


class Forbidden(GatewayError):
    status, code = 403, "forbidden"


class BudgetExceeded(GatewayError):
    status, code = 402, "budget_exceeded"


class RateLimited(GatewayError):
    status, code = 429, "rate_limited"

    def __init__(self, message: str, retry_after_s: float) -> None:
        super().__init__(message, headers={"Retry-After": str(max(1, round(retry_after_s + 0.5)))})
        self.retry_after_s = retry_after_s


class AllProvidersFailed(GatewayError):
    status, code = 503, "all_providers_failed"


class ProviderError(Exception):
    """Raised by a provider adapter (timeout, 5xx, overload). Never shown to clients directly."""
