from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from app.database import init_db, SessionLocal
from app.config import settings
from app.routers import hotspots, alerts, chatbot, stats, facilities, data_sources, model_performance, ml_labeling
from app.services import firms_ingestion

app = FastAPI(
    title="Industrial Fire & Thermal Anomaly Detection API",
    description="SIH 2026 — PS 162: AI-enabled geospatial system for classifying "
                "industrial fires and persistent thermal sources.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hotspots.router)
app.include_router(alerts.router)
app.include_router(chatbot.router)
app.include_router(stats.router)
app.include_router(facilities.router)
app.include_router(data_sources.router)
app.include_router(model_performance.router)
app.include_router(ml_labeling.router)

@app.get("/seed")
def seed():
    try:
        import os, sys, importlib.util
        
        # Locate script directory relative to main.py location
        app_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(app_dir)
        root_dir = os.path.dirname(backend_dir)
        
        paths_to_check = [
            os.path.join(backend_dir, "scripts", "seed_demo.py"),
            os.path.join(root_dir, "scripts", "seed_demo.py"),
            os.path.join(app_dir, "scripts", "seed_demo.py"),
        ]
        
        target_path = next((p for p in paths_to_check if os.path.exists(p)), None)
        
        if not target_path:
            return {"status": "error", "detail": f"seed_demo.py not found at searched locations: {paths_to_check}"}

        spec = importlib.util.spec_from_file_location("seed_demo_module", target_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, "main"):
            module.main()
            
        return {"status": "success", "message": "Database seeded successfully!"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.on_event("startup")
async def on_startup():
    init_db()
    _log_firms_diagnostics()

    # Auto-seed demo records on startup
    try:
        import sys, os, importlib
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
            
        seed_module = importlib.import_module("scripts.seed_demo")
        seed_module.main()
        print("Demo database auto-seeded successfully!")
    except Exception as e:
        print(f"Auto-seed status: {e}")

    if settings.firms_enabled and settings.firms_configured:
        try:
            asyncio.create_task(_firms_sync_loop())
        except NameError:
            pass
    else:
        reason = "FIRMS_ENABLED is false" if not settings.firms_enabled else "FIRMS_MAP_KEY not set"
        print(f"[startup] Automatic FIRMS sync NOT started: {reason}. "
              f"Use POST /data-sources/firms/sync to trigger a manual sync once configured, "
              f"or run `python -m scripts.test_firms` to diagnose why the key isn't being read.")


def _log_firms_diagnostics():
    """
    Task 1's required diagnostic log — safe fields only, the key value
    itself is never printed. Printed unconditionally on every startup so
    a mismatch between "the .env file has it" and "the app sees it" is
    visible immediately in the terminal, not something you have to dig for.
    """
    d = settings.diagnostic_snapshot()
    print("[startup] --- FIRMS configuration diagnostics ---")
    print(f"[startup] FIRMS enabled: {d['firms_enabled']}")
    print(f"[startup] FIRMS key configured: {d['firms_configured']} (length: {d['firms_map_key_length']})")
    print(f"[startup] FIRMS area: {d['firms_area']}")
    print(f"[startup] FIRMS sources: {d['firms_sources']}")
    print(f"[startup] Resolved .env path: {d['env_file_expected_path']} (found: {d['env_file_found']})")
    print(f"[startup] Working directory at startup: {d['resolved_working_directory']}")
    print(f"[startup] config.py actually loaded from: {d['config_module_actual_path']}")
    if d["firms_map_key_pre_existed_in_os_environ"] and not d["firms_configured"]:
        print("[startup] WARNING: FIRMS_MAP_KEY already existed as an OS/shell environment variable "
              "BEFORE .env was loaded, and it was EMPTY — since real env vars take precedence over "
              ".env by design, your .env file's value is being ignored. Check for a stray "
              "`FIRMS_MAP_KEY=` in your shell profile, a previous `set`/`export`, or an IDE 'envFile' "
              "setting pointing elsewhere. Run `python -m scripts.test_firms` for the full diagnosis.")
    if d["firms_enable_typo_pre_existed_in_os_environ"] and not d["firms_enabled_pre_existed_in_os_environ"]:
        print("[startup] NOTE: found FIRMS_ENABLE (no 'D') but not FIRMS_ENABLED in your environment — "
              "the misspelled variant is accepted as an alias, but please rename it to FIRMS_ENABLED "
              "in your .env for clarity going forward.")
    print("[startup] --- end FIRMS diagnostics ---")


async def _firms_sync_loop():
    """
    Real background sync, not a decorative timer. Runs immediately on
    startup, then every FIRMS_SYNC_INTERVAL_MINUTES. Each iteration is a
    genuine call into firms_ingestion.sync_once() — failures are logged
    and retried next cycle, never silently marked successful.
    """
    interval_seconds = max(60, settings.firms_sync_interval_minutes * 60)
    while True:
        db = SessionLocal()
        try:
            result = firms_ingestion.sync_once(db)
            if result["success"]:
                print(f"[firms_sync_loop] OK — fetched {result['fetched']}, "
                      f"inserted {result['inserted']}, duplicates {result['duplicates_skipped']}")
            else:
                print(f"[firms_sync_loop] FAILED — {result['error']}")
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
import os, sys, runpy

@app.get("/seed")
def trigger_db_seed():
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(current_dir)
        root_dir = os.path.dirname(backend_dir)
        
        candidates = [
            os.path.join(backend_dir, "scripts", "seed_demo.py"),
            os.path.join(root_dir, "backend", "scripts", "seed_demo.py"),
            os.path.join(os.getcwd(), "scripts", "seed_demo.py"),
            os.path.join(os.getcwd(), "backend", "scripts", "seed_demo.py"),
        ]
        
        for script_path in candidates:
            if os.path.exists(script_path):
                if backend_dir not in sys.path:
                    sys.path.insert(0, backend_dir)
                runpy.run_path(script_path, run_name="__main__")
                return {"status": "success", "message": "Database seeded successfully!"}
                
        return {"status": "error", "detail": f"seed_demo.py not found at searched paths"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/sync-now")
def trigger_firms_sync_get():
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(current_dir)
        
        candidates = [
            os.path.join(backend_dir, "scripts", "test_firms.py"),
            os.path.join(os.getcwd(), "scripts", "test_firms.py"),
            os.path.join(os.getcwd(), "backend", "scripts", "test_firms.py"),
        ]
        
        for script_path in candidates:
            if os.path.exists(script_path):
                if backend_dir not in sys.path:
                    sys.path.insert(0, backend_dir)
                runpy.run_path(script_path, run_name="__main__")
                return {"status": "success", "message": "Live FIRMS sync completed!"}
                
        return {"status": "error", "detail": "test_firms.py script not found"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
