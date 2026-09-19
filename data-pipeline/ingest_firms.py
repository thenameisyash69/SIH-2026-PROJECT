"""
Thin CLI wrapper for a manual/cron-triggered FIRMS sync. All real logic
lives in backend/app/services/firms_ingestion.py — this script exists so
you can run a sync from a scheduler (cron, Task Scheduler) without going
through the HTTP API, but it is the exact same code path as
POST /data-sources/firms/sync.

Run with:  python data-pipeline/ingest_firms.py
Requires:  FIRMS_MAP_KEY set in backend/.env
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import SessionLocal, init_db
from app.services import firms_ingestion


def run():
    init_db()
    db = SessionLocal()
    result = firms_ingestion.sync_once(db)

    if result["success"]:
        print(f"Sync succeeded: fetched {result['fetched']}, inserted {result['inserted']}, "
              f"skipped {result['duplicates_skipped']} duplicates, "
              f"took {result['duration_seconds']:.1f}s.")
    else:
        print(f"Sync FAILED: {result['error']}")
        print("No previously stored observations were affected — failures never delete data.")


if __name__ == "__main__":
    run()
