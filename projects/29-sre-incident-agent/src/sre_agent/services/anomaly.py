"""Anomaly detection with a robust z-score and a 'sustained' rule.

Why median/MAD instead of mean/stddev? One past spike inflates the stddev and hides the next real
incident. The median and the median absolute deviation (MAD) barely move. Why 'sustained'? A single bad
minute (a GC pause, one slow query) should not page anyone; three in a row should.
"""
from __future__ import annotations

from statistics import median

from sre_agent.domain.models import Anomaly, Series

MAD_TO_SIGMA = 1.4826  # makes MAD comparable to a standard deviation for normal data


def robust_baseline(window: list[float]) -> tuple[float, float]:
    """Return (center, scale). Scale has a floor so near-constant series don't explode."""
    center = median(window)
    mad = median(abs(v - center) for v in window)
    return center, max(MAD_TO_SIGMA * mad, 0.02 * abs(center), 1e-6)


def detect(series: Series, window: int = 20, threshold: float = 4.0, sustain: int = 3) -> Anomaly | None:
    """First sustained deviation in the series, or None.

    The baseline is frozen when a candidate run starts, so anomalous points never leak into it.
    """
    values = list(series.values)
    run_start, center, scale = None, 0.0, 1.0
    for i in range(window, len(values)):
        if run_start is None:
            center, scale = robust_baseline(values[i - window:i])
        z = (values[i] - center) / scale
        if abs(z) <= threshold:
            run_start = None
            continue
        if run_start is None:
            run_start = i
        if i - run_start + 1 >= sustain:
            run = values[run_start:]
            peak = max(run, key=lambda v: abs(v - center))
            return Anomaly(series.name, series.ts_at(run_start), round(center, 2), round(peak, 2),
                           round((peak - center) / scale, 1))
    return None


def detect_all(series_list: list[Series], **kwargs: float) -> list[Anomaly]:
    """Anomalies across every series, earliest first."""
    found = [a for s in series_list if (a := detect(s, **kwargs))]
    return sorted(found, key=lambda a: (a.start, -abs(a.z_score)))
