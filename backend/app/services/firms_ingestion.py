"""
Production-style FIRMS ingestion service. This is the ONLY place that
should ever call firms_fetcher.fetch_firms_hotspots() — both the manual
sync endpoint and the background scheduler go through sync_once() here,
so there is exactly one code path for "what happens when we sync."

Deliberately does NOT duplicate any classification/anomaly/risk logic —
every fetched observation is normalized here and then handed to
app.services.pipeline.process_observation(), the same single orchestrator
seed.py uses. This module's only responsibilities are: fetch, normalize,
enforce India scope, record the attempt (success or failure) in IngestionRun,
and count inserted vs. duplicate.

CRITICAL HONESTY RULE (spec's own Final Rule): a sync is only ever marked
`success=True` if a real NASA HTTP request actually returned 200 and parsed
without error. If FIRMS_MAP_KEY is missing, or the request fails, this
records success=False with a real error_message — it never fabricates a
successful sync, and it never deletes previously stored observations.
"""
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app import models
from app.config import settings
from app.services.firms_fetcher import fetch_firms_hotspots
from app.services.landcover_fetcher import tag_land_cover
from app.services.pipeline import process_observation
from app.services.india_scope import is_in_india

logger = logging.getLogger(__name__)

STALE_AFTER_MINUTES_DEFAULT = 60


def sync_once(db: Session) -> dict:
    """
    Performs one real FIRMS sync attempt across all configured sources.
    Returns a result dict matching the spec's POST /data-sources/firms/sync contract.
    """
    started_at = datetime.utcnow()
    run = models.IngestionRun(source="nasa_firms", started_at=started_at, success=False)
    db.add(run)
    db.flush()

    if not settings.firms_enabled:
        return _finish_run(db, run, started_at, success=False,
                           error="FIRMS_ENABLED is false in configuration.")

    if not settings.firms_configured:
        return _finish_run(db, run, started_at, success=False,
                           error="FIRMS_MAP_KEY is not set — cannot make a real NASA request.")

    try:
        fetch_result = fetch_firms_hotspots()
    except Exception as e:
        logger.error("[firms_ingestion] Sync failed — exception: %s", str(e)[:200])
        return _finish_run(db, run, started_at, success=False, error=str(e))

    raw_observations = fetch_result.get("observations", [])
    source_results = fetch_result.get("sources", {})
    errors = fetch_result.get("errors", {})

    fetched_count = len(raw_observations)
    inserted_count = 0
    duplicate_count = 0
    skipped_outside_india = 0

    for raw in raw_observations:
        if not is_in_india(raw["lat"], raw["lon"]):
            skipped_outside_india += 1
            continue

        land_cover = tag_land_cover(raw["lat"], raw["lon"])
        hotspot = process_observation(db, {
            **raw,
            "land_cover": land_cover,
            "source": "nasa_firms",
        }, commit=False)

        if getattr(hotspot, "_was_duplicate", False):
            duplicate_count += 1
        else:
            inserted_count += 1

    db.commit()

    error_messages = []
    if errors:
        for sensor, msg in errors.items():
            error_messages.append(f"{sensor}: {msg}")
        run.error_message = "; ".join(error_messages)

    run.fetched_count = fetched_count
    run.inserted_count = inserted_count
    run.duplicate_count = duplicate_count
    run.success = True
    run.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(run)

    logger.info("[firms_ingestion] Sync complete — fetched=%d, inserted=%d, duplicates=%d, outside_india=%d, errors=%s",
                fetched_count, inserted_count, duplicate_count, skipped_outside_india,
                error_messages if error_messages else "none")

    sync_result = {
        "success": True,
        "fetched": fetched_count,
        "inserted": inserted_count,
        "duplicates_skipped": duplicate_count,
        "skipped_outside_india": skipped_outside_india,
        "last_successful_sync": run.finished_at.isoformat(),
        "sources": settings.firms_sources,
        "duration_seconds": (run.finished_at - started_at).total_seconds(),
        "error": None,
        "source_details": source_results,
    }
    if error_messages:
        sync_result["errors"] = errors

    return sync_result


def _finish_run(db: Session, run: models.IngestionRun, started_at: datetime, success: bool, error: str) -> dict:
    run.success = success
    run.error_message = error
    run.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    logger.warning("[firms_ingestion] Sync FAILED — %s", error)
    return {
        "success": success,
        "fetched": 0,
        "inserted": 0,
        "duplicates_skipped": 0,
        "last_successful_sync": None,
        "sources": settings.firms_sources,
        "duration_seconds": (run.finished_at - started_at).total_seconds(),
        "error": error,
        "source_details": {},
    }


def get_firms_status(db: Session) -> dict:
    """Real, checked status — never reports 'live' without a real successful sync on record."""
    last_run = db.query(models.IngestionRun).filter(
        models.IngestionRun.source == "nasa_firms"
    ).order_by(models.IngestionRun.started_at.desc()).first()

    last_success_run = db.query(models.IngestionRun).filter(
        models.IngestionRun.source == "nasa_firms", models.IngestionRun.success.is_(True)
    ).order_by(models.IngestionRun.finished_at.desc()).first()

    total_real = db.query(models.Hotspot).filter(models.Hotspot.source == "nasa_firms").all()
    total_real = sum(1 for h in total_real if is_in_india(h.lat, h.lon))

    latest_real_hotspot = db.query(models.Hotspot).filter(
        models.Hotspot.source == "nasa_firms"
    ).order_by(models.Hotspot.acq_date.desc()).first()

    stale = True
    minutes_since_success = None
    if last_success_run and last_success_run.finished_at:
        minutes_since_success = (datetime.utcnow() - last_success_run.finished_at).total_seconds() / 60
        stale = minutes_since_success > STALE_AFTER_MINUTES_DEFAULT

    # Truthful OFFLINE reason using config diagnostics
    offline_reason = None
    if not settings.firms_configured:
        diag = settings.diagnostic_snapshot()
        if diag.get("firms_map_key_pre_existed_in_os_environ"):
            offline_reason = ("FIRMS_MAP_KEY not set — an empty value for this variable already existed "
                              "in the OS/shell environment before .env was loaded, so .env's value was "
                              "not applied. Run `python -m scripts.test_firms` to diagnose.")
        elif not diag.get("env_file_found"):
            offline_reason = f"FIRMS_MAP_KEY not set — no .env file was found at {diag.get('env_file_expected_path')}."
        else:
            offline_reason = "FIRMS_MAP_KEY not set in backend/.env."

    return {
        "enabled": settings.firms_enabled,
        "configured": settings.firms_configured,
        "offline_reason": offline_reason,
        "last_attempt": last_run.started_at.isoformat() if last_run else None,
        "last_success": last_success_run.finished_at.isoformat() if last_success_run and last_success_run.finished_at else None,
        "last_error": last_run.error_message if last_run and not last_run.success else None,
        "observations_last_sync": last_success_run.inserted_count if last_success_run else 0,
        "total_real_observations": total_real,
        "latest_acquisition_time": latest_real_hotspot.acq_date.isoformat() if latest_real_hotspot else None,
        "sources_configured": settings.firms_sources,
        "stale": stale if last_success_run else True,
        "stale_after_minutes": STALE_AFTER_MINUTES_DEFAULT,
        "minutes_since_last_success": round(minutes_since_success, 1) if minutes_since_success is not None else None,
    }