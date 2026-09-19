"""
The core differentiator (spec §5). Builds a facility-specific thermal
profile from its observation history, and distinguishes:

  PERSISTENT + EXPECTED    -> normal industrial activity (a refinery
                               flare that's ALWAYS been this bright)
  PERSISTENT + UNEXPECTED  -> potential industrial anomaly (persistent
                               but behavior has recently shifted)
  INSUFFICIENT_HISTORY     -> honest "we don't know yet" state

This is deliberately NOT "persistent = safe" or "persistent = alert" —
both of those are the naive mistake the spec calls out.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app import models
from app.services.baseline_engine import compute_baseline, evaluate_against_baseline, MIN_OBSERVATIONS_FOR_BASELINE


def _recent_count(hotspots: list, days: int, now: datetime) -> int:
    cutoff = now - timedelta(days=days)
    return sum(1 for h in hotspots if h.acq_date and h.acq_date >= cutoff)


def _compute_persistence_score(hotspots: list) -> float:
    """
    Computes persistence as the fraction of unique active calendar days
    within the most recent 30-day operational window ending at the latest
    available observation date.

    Multiple observations on the same calendar day count as ONE active day,
    so a facility detected twice in one satellite pass is not mistaken for
    two days of persistence.

    The window is anchored to the latest observation date rather than
    datetime.utcnow() so that historical backfilled data is evaluated
    honestly — a facility whose last detection was 60 days ago is not
    penalized for the passage of wall-clock time since ingestion.
    """
    if not hotspots:
        return 0.0

    valid = [h for h in hotspots if h.acq_date is not None]
    if not valid:
        return 0.0

    latest = max(h.acq_date for h in valid)
    window_start = latest - timedelta(days=30)

    active_days = {
        h.acq_date.date()
        for h in valid
        if h.acq_date >= window_start
    }

    return round(min(1.0, len(active_days) / 30.0), 2)


def build_fingerprint(db: Session, facility: models.Facility, source: str | None = None) -> dict:
    query = db.query(models.Hotspot).filter(models.Hotspot.facility_id == facility.id)
    if source is not None:
        query = query.filter(models.Hotspot.source == source)
    hotspots = query.order_by(models.Hotspot.acq_date.asc()).all()
    now = datetime.utcnow()
    history = [h.brightness for h in hotspots]
    unique_days = len({h.acq_date.date() for h in hotspots if h.acq_date is not None})
    baseline = compute_baseline(history, unique_days=unique_days)

    recent_7d = _recent_count(hotspots, 7, now)
    recent_30d = _recent_count(hotspots, 30, now)
    recent_60d = _recent_count(hotspots, 60, now)

    persistence_score = _compute_persistence_score(hotspots)
    recurrence_rate = round(recent_30d / 30, 2)

    historical_anomaly_count = sum(1 for h in hotspots if h.is_anomaly)

    if (baseline.observation_count < MIN_OBSERVATIONS_FOR_BASELINE
            or (baseline.unique_days is not None
                and baseline.unique_days < MIN_OBSERVATIONS_FOR_BASELINE)):
        behavior_label = "INSUFFICIENT_HISTORY"
    elif persistence_score >= 0.6 and historical_anomaly_count / max(1, len(hotspots)) < 0.15:
        behavior_label = "PERSISTENT_EXPECTED"
    elif persistence_score >= 0.6:
        behavior_label = "PERSISTENT_UNEXPECTED"
    else:
        behavior_label = "IRREGULAR"

    return {
        "facility_id": facility.id,
        "facility_name": facility.name,
        "observation_count": baseline.observation_count,
        "baseline_mean": round(baseline.mean, 2) if baseline.mean is not None else None,
        "baseline_median": round(baseline.median, 2) if baseline.median is not None else None,
        "baseline_std": round(baseline.std, 2) if baseline.std is not None else None,
        "baseline_p95": round(baseline.p95, 2) if baseline.p95 is not None else None,
        "recent_7d_count": recent_7d,
        "recent_30d_count": recent_30d,
        "recent_60d_count": recent_60d,
        "persistence_score": persistence_score,
        "recurrence_rate": recurrence_rate,
        "behavior_label": behavior_label,
        "historical_anomaly_count": historical_anomaly_count,
    }


def get_baseline_for_new_reading(db: Session, facility_id: int | None,
                                 exclude_hotspot_id: int | None = None,
                                 baseline_window_days: int | None = None,
                                 source: str | None = None):
    """
    Used at ingestion time: baseline computed from history EXCLUDING the
    reading being evaluated.

    When baseline_window_days is set, the history is restricted to a
    rolling calendar window anchored to the latest observation in the
    (filtered) set. This prevents stale observations from dominating the
    baseline and makes it a true rolling window rather than an ever-growing
    cumulative statistic.

    When source is set, only observations of that source are considered.
    This is essential so demo_synthetic data never pollutes the NASA
    FIRMS baseline.

    When baseline_window_days is None, the full unfiltered history is
    returned (existing behavior — used for demo data and any caller that
    explicitly wants all-source history).
    """
    if facility_id is None:
        return compute_baseline([])

    query = db.query(models.Hotspot).filter(models.Hotspot.facility_id == facility_id)
    if source is not None:
        query = query.filter(models.Hotspot.source == source)
    if exclude_hotspot_id is not None:
        query = query.filter(models.Hotspot.id != exclude_hotspot_id)

    all_rows = query.all()

    if baseline_window_days is None:
        history = [h.brightness for h in all_rows]
        unique_days = len({h.acq_date.date() for h in all_rows if h.acq_date is not None})
        return compute_baseline(history, unique_days=unique_days)

    # Rolling window: anchor to the latest observation in the filtered set
    # so historical backfill is evaluated honestly (wall-clock time since
    # ingestion does not artificially age the window).
    valid = [h for h in all_rows if h.acq_date is not None]
    if not valid:
        return compute_baseline([])

    latest = max(h.acq_date for h in valid)
    cutoff = latest - timedelta(days=baseline_window_days - 1)

    in_window = [h for h in valid if h.acq_date >= cutoff]
    history = [h.brightness for h in in_window]
    unique_days = len({h.acq_date.date() for h in in_window})
    return compute_baseline(history, unique_days=unique_days)
