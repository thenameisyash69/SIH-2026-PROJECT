from fastapi import APIRouter, HTTPException
from app.database import SessionLocal
from app.models import Facility, Hotspot
from datetime import datetime
import random

router = APIRouter(prefix="/admin", tags=["Admin Seeding"])

@router.get("/seed-baselines")
def seed_baselines_and_labels():
    db = SessionLocal()
    try:
        # 1. Update facilities with active historical baseline statistics
        facilities = db.query(Facility).all()
        for facility in facilities:
            facility.baseline_mean = 315.5
            facility.baseline_std = 8.2
            facility.baseline_sample_size = 142
            facility.baseline_status = "active"
            facility.last_baseline_update = datetime.utcnow()

        # 2. Update hotspots with Z-scores and analyst statuses
        statuses = ["VERIFIED_INDUSTRIAL", "FALSE_POSITIVE", "ROUTINE_PROCESS"]
        hotspots = db.query(Hotspot).limit(20).all()

        for idx, hp in enumerate(hotspots):
            hp.z_score = round(random.uniform(1.5, 4.2), 2)
            hp.baseline_mean = 315.5
            hp.baseline_std = 8.2
            if idx < 10:
                hp.status = statuses[idx % len(statuses)]

        db.commit()
        return {
            "status": "success",
            "message": "Historical baselines and analyst labels applied successfully!",
            "facilities_updated": len(facilities),
            "hotspots_updated": len(hotspots)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()