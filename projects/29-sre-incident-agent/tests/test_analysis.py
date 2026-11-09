"""Detection, log grouping and hypothesis ranking."""
from __future__ import annotations

from datetime import datetime, timezone

from sre_agent.domain.models import LogEvent, Series, parse_ts
from sre_agent.services import anomaly, hypotheses, logs

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _series(values: list[float]) -> Series:
    return Series("svc.metric", T0, 60, tuple(values))


def test_sustained_shift_is_detected_at_its_start() -> None:
    values = [100 + (i % 3) for i in range(30)] + [400] * 5
    a = anomaly.detect(_series(values))
    assert a is not None and a.start == _series(values).ts_at(30)
    assert a.peak == 400 and a.z_score > 4


def test_single_spike_is_ignored() -> None:
    values = [100 + (i % 3) for i in range(30)] + [900] + [101] * 5
    assert anomaly.detect(_series(values)) is None


def test_flat_noisy_series_has_no_anomaly() -> None:
    values = [50 + ((i * 7) % 5) for i in range(60)]
    assert anomaly.detect(_series(values)) is None


def test_scenario_finds_the_three_real_anomalies(telemetry) -> None:
    found = anomaly.detect_all(telemetry.all_series())
    assert {a.series for a in found} == {"checkout-api.latency_p95_ms", "checkout-api.error_rate_pct",
                                         "payments-db.active_connections"}
    assert all(a.start == parse_ts("2026-10-21T14:05:00Z") for a in found)


def test_log_templates_group_by_shape() -> None:
    evts = [LogEvent(T0, "api", "ERROR", f"timeout after {n}ms (waiting={n // 10})") for n in (5000, 5000, 3000)]
    evts.append(LogEvent(T0, "api", "INFO", "all good"))
    sigs = logs.signatures(evts)
    assert len(sigs) == 1 and sigs[0].count == 3
    assert sigs[0].template == "timeout after <n>ms (waiting=<n>)"


def test_ranking_puts_the_checkout_deploy_first(telemetry) -> None:
    found = anomaly.detect_all(telemetry.all_series())
    sigs = logs.signatures(telemetry.logs(since=parse_ts("2026-10-21T13:55:00Z"), min_level="WARN"))
    ranked = hypotheses.rank(telemetry, found, sigs, telemetry.deploys())
    assert ranked[0].kind == "bad_deploy" and ranked[0].params["version"] == "v2.14.0"
    assert ranked[0].score >= 0.8
    surge = next(h for h in ranked if h.kind == "traffic_surge")
    assert surge.score < 0.2  # traffic was flat: evidence against
    db = next(h for h in ranked if h.title.startswith("payments-db"))
    assert any(e.weight < 0 for e in db.evidence)  # recognised as a symptom


def test_no_anomalies_means_no_hypotheses(telemetry) -> None:
    assert hypotheses.rank(telemetry, [], [], telemetry.deploys()) == []
