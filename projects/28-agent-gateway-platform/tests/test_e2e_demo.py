"""End-to-end: `python demo.py` exactly as learners run it, plus the settings that feed `build()`."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from gateway.config import Settings
from gateway.container import build

ROOT = Path(__file__).resolve().parents[1]


def test_demo_runs_all_nine_scenes() -> None:
    proc = subprocess.run([sys.executable, "demo.py"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    out = proc.stdout
    assert proc.returncode == 0, proc.stderr
    for n in range(1, 10):
        assert f"| {n}. " in out
    assert "<- 200  HIT" in out                          # scene 1: cache
    assert "beta-pro[ok]" in out and "[OPEN]" in out     # scene 2: fallback + circuit breaker
    assert "-> 429" in out                               # scene 3: burst limit
    assert "-> 402  budget_exceeded" in out              # scene 5: budget hard stop
    assert "admitted 10 == burst 10?  YES" in out        # scene 7: load test
    assert "hash chain verified: True" in out            # scene 9: audit
    assert "verified: False, chain breaks at #3" in out


def test_settings_are_parsed_and_wired_into_build() -> None:
    s = Settings.from_env({"LLM_PROVIDER": "OpenAI", "MODEL_MAP": "alpha-fast = a, beta-pro=b",
                           "CACHE_TTL_S": "5", "CACHE_MAX_ENTRIES": "7", "BREAKER_THRESHOLD": "1",
                           "BREAKER_COOLDOWN_S": "2", "HOST": "0.0.0.0", "PORT": "9000",
                           "PROVIDER_TIMEOUT_S": "3", "OPENAI_API_KEY": "k"})
    assert s.llm_provider == "openai" and s.model_map == {"alpha-fast": "a", "beta-pro": "b"}
    assert (s.cache_ttl_s, s.cache_max_entries, s.breaker_threshold, s.breaker_cooldown_s) == (5, 7, 1, 2)
    assert (s.host, s.port, s.provider_timeout_s, s.openai_api_key) == ("0.0.0.0", 9000, 3, "k")
    assert Settings.from_env({}) == Settings()
    container = build(settings=Settings())               # mock providers, default tenants file
    assert set(container.providers) == {"alpha", "beta"}
    assert container.service.keys.tenant("acme") is not None
