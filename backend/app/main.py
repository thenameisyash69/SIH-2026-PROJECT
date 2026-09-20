from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import asyncio
import os
import sys
import runpy

from app.database import init_db, SessionLocal, get_db
from app.config import settings
from app.routers import (
    hotspots,
    alerts,
    chatbot,
    stats,
    facilities,
    data_sources,
    model_performance,
    ml_labeling,
    admin,
)
from app.services import firms_ingestion

app = FastAPI(
    title="Industrial Fire & Thermal Anomaly Detection API",
    description="SIH 2026 — PS 162: AI-enabled geospatial system for classifying "
                "industrial fires and persistent thermal sources.",
    version="0.1.0",
)

# Enable CORS for all frontend origins (including dynamic Vercel deployments)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registration
app.include_router(hotspots.router)
app.include_router(alerts.router)
app.include_router(chatbot.router)
app.include_router(stats.router)
app.include_router(facilities.router)
app.include_router(data_sources.router)
app.include_router(model_performance.router)
app.include_router(ml_labeling.router)
app.include_router(admin.router)


@app.on_event("startup")
async def on_startup():
    init_db()
    _log_firms_diagnostics()

    # Auto-seed demo records on startup if needed
    try:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        script_path = os.path.join(backend_dir, "scripts", "seed.py")
        if os.path.exists(script_path):
            runpy.run_path(script_path, run_name="__main__")
            print("Database auto-seeded successfully!")
    except Exception as e:
        print(f"Auto-seed status: {e}")

    if settings.firms_enabled and settings.firms_configured:
        try:
            asyncio.create_task(_firms_sync_loop())
        except NameError:
            pass
    else:
        reason = "FIRMS_ENABLED is false" if not settings.firms_enabled else "FIRMS_MAP_KEY not set"
        print(f"[startup] Automatic FIRMS sync NOT started: {reason}.")


def _log_firms_diagnostics():
    d = settings.diagnostic_snapshot()
    print("[startup] --- FIRMS configuration diagnostics ---")
    print(f"[startup] FIRMS enabled: {d['firms_enabled']}")
    print(f"[startup] FIRMS key configured: {d['firms_configured']} (length: {d['firms_map_key_length']})")
    print(f"[startup] FIRMS area: {d['firms_area']}")
    print(f"[startup] FIRMS sources: {d['firms_sources']}")
    print("[startup] --- end FIRMS diagnostics ---")


async def _firms_sync_loop():
    interval_seconds = max(60, settings.firms_sync_interval_minutes * 60)
    while True:
        db = SessionLocal()
        try:
            result = firms_ingestion.sync_once(db)
            if result.get("success"):
                logger_msg = (f"[firms_sync_loop] OK — fetched {result.get('fetched')}, "
                              f"inserted {result.get('inserted')}, "
                              f"duplicates {result.get('duplicates_skipped')}, "
                              f"outside_india {result.get('skipped_outside_india')}, "
                              f"duration {result.get('duration_seconds'):.1f}s")
                src_details = result.get("source_details", {})
                if src_details:
                    logger_msg += f", sources: {src_details}"
                if result.get("errors"):
                    logger_msg += f", errors: {result['errors']}"
                print(logger_msg)
            else:
                print(f"[firms_sync_loop] FAILED — {result.get('error')}")
        except Exception as e:
            print(f"[firms_sync_loop] Unexpected error: {e}")
        finally:
            db.close()
        await asyncio.sleep(interval_seconds)


@app.get("/")
def root():
    return {"status": "ok", "service": "industrial-fire-ai-backend"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/seed")
def seed():
    try:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(app_dir)
        script_path = os.path.join(backend_dir, "scripts", "seed.py")
        
        if not os.path.exists(script_path):
            script_path = os.path.join(os.getcwd(), "backend", "scripts", "seed.py")

        runpy.run_path(script_path, run_name="__main__")
        return {"status": "success", "message": "Database seeded successfully!"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/sync-now")
def sync_firms_now(db: Session = Depends(get_db)):
    try:
        result = firms_ingestion.sync_once(db)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/classify-now")
def classify_all_now(db: Session = Depends(get_db)):
    try:
        from app.models import Hotspot
        hotspots_list = db.query(Hotspot).all()
        count = 0
        for h in hotspots_list:
            if hasattr(h, 'is_classified'):
                h.is_classified = True
                count += 1
        db.commit()
        return {"status": "success", "classified_count": count}
    except Exception as e:
        db.rollback()
        return {"status": "error", "detail": str(e)}