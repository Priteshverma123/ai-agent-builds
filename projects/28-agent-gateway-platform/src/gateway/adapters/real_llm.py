"""Optional real providers (Anthropic / OpenAI) behind the same `Provider` protocol.

Selected with LLM_PROVIDER=anthropic|openai. Gateway model names (alpha-fast, ...) are mapped to real
model ids with env vars, e.g. MODEL_MAP="alpha-fast=claude-haiku-4-5,alpha-pro=claude-sonnet-4-5".
Keys, model map and timeout all arrive through `gateway.config.Settings`.
"""
from __future__ import annotations

import httpx

from gateway.config import Settings
from gateway.domain.errors import ProviderError
from gateway.domain.models import Completion, Message


class HttpProvider:
    """One class, two wire formats. Any non-2xx or network error becomes ProviderError (-> fallback)."""

    def __init__(self, name: str, kind: str, settings: Settings | None = None) -> None:
        settings = settings or Settings.from_env()
        self.name, self.kind = name, kind
        self._client = httpx.Client(timeout=settings.provider_timeout_s)
        self._map = settings.model_map
        self._key = settings.anthropic_api_key if kind == "anthropic" else settings.openai_api_key

    def complete(self, model: str, messages: list[Message], max_tokens: int, temperature: float) -> Completion:
        real_model = self._map.get(model, model)
        try:
            if self.kind == "anthropic":
                return self._anthropic(real_model, messages, max_tokens, temperature)
            return self._openai(real_model, messages, max_tokens, temperature)
        except (httpx.HTTPError, KeyError) as exc:
            raise ProviderError(f"{self.name}: {exc}") from exc

    def _anthropic(self, model: str, messages: list[Message], max_tokens: int, temperature: float) -> Completion:
        system = "\n".join(m.content for m in messages if m.role == "system")
        body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": [m.model_dump() for m in messages if m.role != "system"]}
        if system:
            body["system"] = system
        r = self._client.post("https://api.anthropic.com/v1/messages", json=body, headers={
            "x-api-key": self._key, "anthropic-version": "2023-06-01"})
        r.raise_for_status()
        data = r.json()
        text = "".join(b.get("text", "") for b in data["content"])
        return Completion(text, data["usage"]["input_tokens"], data["usage"]["output_tokens"])

    def _openai(self, model: str, messages: list[Message], max_tokens: int, temperature: float) -> Completion:
        body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                "messages": [m.model_dump() for m in messages]}
        r = self._client.post("https://api.openai.com/v1/chat/completions", json=body, headers={
            "Authorization": f"Bearer {self._key}"})
        r.raise_for_status()
        data = r.json()
        return Completion(data["choices"][0]["message"]["content"],
                          data["usage"]["prompt_tokens"], data["usage"]["completion_tokens"])
