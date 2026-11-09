"""Response cache: LRU + TTL, keyed per tenant.

Only deterministic requests (temperature == 0) are cached. The tenant id is part of the key so one
customer can never be served another customer's answer.
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict

from gateway.adapters.clock import Clock
from gateway.domain.models import ChatRequest, ChatResponse


def cache_key(tenant_id: str, model: str, request: ChatRequest) -> str:
    payload = {"tenant": tenant_id, "model": model, "max_tokens": request.max_tokens,
               "messages": [m.model_dump() for m in request.messages]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def is_cacheable(request: ChatRequest) -> bool:
    return request.temperature == 0.0


class ResponseCache:
    def __init__(self, clock: Clock, max_entries: int = 1_000, ttl_s: float = 300.0) -> None:
        self._clock = clock
        self._max = max_entries
        self._ttl = ttl_s
        self._items: OrderedDict[str, tuple[float, ChatResponse]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> ChatResponse | None:
        with self._lock:
            item = self._items.get(key)
            if item is None or self._clock.now() - item[0] > self._ttl:
                self._items.pop(key, None)
                self.misses += 1
                return None
            self._items.move_to_end(key)
            self.hits += 1
            return item[1]

    def put(self, key: str, response: ChatResponse) -> None:
        with self._lock:
            self._items[key] = (self._clock.now(), response)
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)
