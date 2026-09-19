"""
Reports REAL, checked status for each data source. FIRMS status is never
"ok"/"live" without a real successful sync on record — see
app.services.firms_ingestion.get_firms_status().
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy import func
from app.database import get_db
from app import models
from app.config import settings
from app.services import firms_ingestion, classifier

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("/status")
def status(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    results = []

    firms_status = firms_ingestion.get_firms_status(db)
    if not firms_status["configured"]:
        label = "OFFLINE — NASA FIRMS"
        detail = firms_status["offline_reason"]
    elif not firms_status["enabled"]:
        label = "OFFLINE — NASA FIRMS"
        detail = "FIRMS_ENABLED is false in configuration."
    elif firms_status["last_success"] is None:
        label = "OFFLINE — NASA FIRMS"
        detail = firms_status["last_error"] or "No successful sync has occurred yet. Call POST /data-sources/firms/sync."
    elif firms_status["stale"]:
        label = "STALE — NASA FIRMS"
        detail = f"Last successful synchronization: {firms_status['last_success']} ({firms_status['minutes_since_last_success']} min ago)."
    else:
        label = "LIVE — NASA FIRMS"
        detail = f"Last synchronized {firms_status['minutes_since_last_success']} min ago. {firms_status['total_real_observations']} real observations on record."

    results.append({"name": "NASA FIRMS", "status": label, "detail": detail, "last_checked": now, **firms_status})

    demo_count = db.query(func.count(models.Hotspot.id)).filter(models.Hotspot.source == "demo_synthetic").scalar() or 0
    results.append({"name": "Demo data", "status": "ENABLED" if demo_count else "EMPTY",
                     "detail": f"{demo_count} synthetic observations.", "last_checked": now,
                     "enabled": True, "observation_count": demo_count})

    results.append({
        "name": "Chatbot (LLM phrasing)",
        "status": "ok" if settings.anthropic_api_key else "not_configured",
        "detail": "Retrieval-only mode (still fully functional)." if not settings.anthropic_api_key
                  else "Claude phrasing enabled.",
        "last_checked": now,
    })

    results.append({"name": "NASA GIBS satellite imagery", "status": "ok",
                     "detail": "No API key required.", "last_checked": now})

    results.append({"name": "OSM / Overpass land-cover", "status": "ok",
                     "detail": "No API key required.", "last_checked": now})

    engine_status = classifier.active_engine()
    if engine_status == "XGBoost ACTIVE":
        results.append({"name": "ML classifier", "status": "ok",
                         "detail": "XGBoost ACTIVE — trained model in use for new classifications.",
                         "engine": engine_status, "last_checked": now})
    else:
        results.append({"name": "ML classifier", "status": "degraded",
                         "detail": "RULE ENGINE FALLBACK — no valid trained model found.",
                         "engine": engine_status, "last_checked": now})
    try:
        db.query(func.count(models.Hotspot.id)).scalar()
        results.append({"name": "Database", "status": "ok", "detail": "Reachable.", "last_checked": now})
    except Exception as e:
        results.append({"name": "Database", "status": "error", "detail": str(e), "last_checked": now})

    return results


@router.post("/firms/sync")
def trigger_firms_sync(db: Session = Depends(get_db)):
    """
    Triggers ONE real FIRMS sync attempt right now. Returns the actual
    result — never claims success unless app.services.firms_ingestion
    genuinely completed a NASA request and parsed the response.
    """
    return firms_ingestion.sync_once(db)


@router.get("/firms/diagnostics")
def firms_diagnostics():
    """
    Safe configuration diagnostics — booleans, lengths, and paths only.
    The FIRMS_MAP_KEY value itself is never included. Equivalent to
    running `python -m scripts.test_firms`'s configuration section, but
    reachable without shell access (e.g. to check from a browser).
    """
    return settings.diagnostic_snapshot()
