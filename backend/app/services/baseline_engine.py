"""
Computes a facility's statistical thermal baseline and evaluates a new
reading against it. Per spec §6: never calculate misleading statistics
from too little history — INSUFFICIENT_HISTORY is a first-class,
honest answer, not an edge case to hide.
"""
import statistics
from dataclasses import dataclass

MIN_OBSERVATIONS_FOR_BASELINE = 8
Z_ELEVATED = 1.5
Z_ABNORMAL = 2.5


@dataclass
class Baseline:
    observation_count: int
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    p95: float | None = None
    unique_days: int | None = None


def compute_baseline(history: list[float], unique_days: int | None = None) -> Baseline:
    n = len(history)
    if n < MIN_OBSERVATIONS_FOR_BASELINE:
        return Baseline(observation_count=n, unique_days=unique_days)

    sorted_h = sorted(history)
    p95_index = max(0, int(round(0.95 * (n - 1))))
    return Baseline(
        observation_count=n,
        mean=statistics.mean(history),
        median=statistics.median(history),
        std=statistics.pstdev(history) or 1e-6,
        p95=sorted_h[p95_index],
        unique_days=unique_days,
    )


def evaluate_against_baseline(value: float, baseline: Baseline) -> dict:
    """
    Returns z_score, deviation_percentage, baseline_status.
    Honest about insufficient history rather than guessing.
    """
    if (baseline.observation_count < MIN_OBSERVATIONS_FOR_BASELINE
            or baseline.mean is None
            or (baseline.unique_days is not None
                and baseline.unique_days < MIN_OBSERVATIONS_FOR_BASELINE)):
        return {
            "z_score": 0.0,
            "deviation_percentage": 0.0,
            "baseline_status": "INSUFFICIENT_HISTORY",
        }

    z = (value - baseline.mean) / (baseline.std or 1e-6)
    deviation_pct = ((value - baseline.mean) / baseline.mean) * 100 if baseline.mean else 0.0

    if z >= Z_ABNORMAL:
        status = "ABNORMAL"
    elif z >= Z_ELEVATED:
        status = "ELEVATED"
    else:
        status = "NORMAL"

    # z is mathematically unbounded — a facility with very low natural
    # variance can produce |z| in the dozens for a moderate absolute change.
    # This does NOT affect status (still correctly ABNORMAL either way) or
    # downstream risk (anomaly_engine keys off baseline_status, not raw z —
    # verified in tests/run_pipeline_scenarios.py Scenario B). Clamped here
    # purely so the number shown to an analyst stays interpretable.
    z_display = max(-10.0, min(10.0, z))

    return {
        "z_score": round(z_display, 2),
        "deviation_percentage": round(deviation_pct, 1),
        "baseline_status": status,
    }
