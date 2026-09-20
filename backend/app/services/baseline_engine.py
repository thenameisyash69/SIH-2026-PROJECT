"""
Computes a facility's statistical thermal baseline and evaluates a new
reading against it. Per spec §6: never calculate misleading statistics
from too little history — INSUFFICIENT_HISTORY is a first-class,
honest answer, not an edge case to hide.

Baseline-level statuses (describe the quality of the baseline history):
  INSUFFICIENT_HISTORY — no observations available
  PROVISIONAL          — some observations exist but < 8 obs / < 8 unique
                         active days; stats are mathematically computed but
                         not yet stable
  ESTABLISHED          — >= 8 observations across >= 8 unique active days

Reading-level statuses (per-reading evaluation returned by
evaluate_against_baseline):
  INSUFFICIENT_HISTORY / NORMAL / ELEVATED / ABNORMAL
  (PROVISIONAL baselines yield INSUFFICIENT_HISTORY at the reading level
  so the pipeline never misclassifies a reading from a small sample,
  but the baseline-level stats are still returned for display.)
"""
import statistics
from dataclasses import dataclass, field

MIN_OBSERVATIONS_FOR_BASELINE = 8
Z_ELEVATED = 1.5
Z_ABNORMAL = 2.5

# --- Baseline-level statuses ---
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
PROVISIONAL = "PROVISIONAL"
ESTABLISHED = "ESTABLISHED"


@dataclass
class Baseline:
    observation_count: int
    mean: float | None = None
    median: float | None = None
    std: float | None = None
    p95: float | None = None
    unique_days: int | None = None
    status: str = INSUFFICIENT_HISTORY


def compute_baseline(history: list[float], unique_days: int | None = None) -> Baseline:
    n = len(history)
    if n == 0:
        return Baseline(observation_count=0, unique_days=unique_days,
                        status=INSUFFICIENT_HISTORY)

    sorted_h = sorted(history)
    p95_index = max(0, int(round(0.95 * (n - 1))))
    mean = statistics.mean(history)
    median = statistics.median(history)
    std = statistics.pstdev(history) or 1e-6
    p95 = sorted_h[p95_index]

    meets_count = n >= MIN_OBSERVATIONS_FOR_BASELINE
    meets_days = unique_days is None or unique_days >= MIN_OBSERVATIONS_FOR_BASELINE
    status = ESTABLISHED if (meets_count and meets_days) else PROVISIONAL

    return Baseline(
        observation_count=n,
        mean=mean,
        median=median,
        std=std,
        p95=p95,
        unique_days=unique_days,
        status=status,
    )


def baseline_confidence(observation_count: int, unique_days: int | None = None) -> tuple[str, str]:
    """
    Returns (baseline_status, explanation) for a set of observations.

    The explanation is a human-readable confidence / limitations statement
    suitable for direct display in API responses and the UI.
    """
    if observation_count == 0:
        return INSUFFICIENT_HISTORY, (
            "No observations available to calculate a baseline. "
            "No statistics are computed — showing raw observations only."
        )

    meets_count = observation_count >= MIN_OBSERVATIONS_FOR_BASELINE
    meets_days = unique_days is None or unique_days >= MIN_OBSERVATIONS_FOR_BASELINE

    if meets_count and meets_days:
        days_str = str(unique_days) if unique_days is not None else "unknown"
        return ESTABLISHED, (
            f"Established baseline — sufficient data: {observation_count} observations "
            f"across {days_str} unique active calendar day(s) "
            f"(requires at least {MIN_OBSERVATIONS_FOR_BASELINE} of each)."
        )

    reasons = []
    if not meets_count:
        reasons.append(
            f"only {observation_count} observation(s) "
            f"(minimum {MIN_OBSERVATIONS_FOR_BASELINE} required)"
        )
    if not meets_days:
        reasons.append(
            f"{unique_days} unique active day(s) "
            f"(minimum {MIN_OBSERVATIONS_FOR_BASELINE} required)"
        )

    return PROVISIONAL, (
        f"Provisional baseline — statistics are computed from available "
        f"history but are not yet stable. Limitations: {', '.join(reasons)}. "
        "Values are real observations, never fabricated."
    )


def evaluate_against_baseline(value: float, baseline: Baseline) -> dict:
    """
    Returns z_score, deviation_percentage, baseline_status.
    Honest about insufficient history rather than guessing.

    Only ESTABLISHED baselines produce a real z-score. PROVISIONAL and
    INSUFFICIENT_HISTORY baselines return z_score=0.0 and
    baseline_status=INSUFFICIENT_HISTORY so the pipeline never
    misclassifies a reading from an unreliable small sample. The
    baseline-level status (PROVISIONAL vs ESTABLISHED) is available
    separately via baseline.status and the thermal-history API.
    """
    if baseline.status != ESTABLISHED or baseline.mean is None:
        return {
            "z_score": 0.0,
            "deviation_percentage": 0.0,
            "baseline_status": INSUFFICIENT_HISTORY,
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
