from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)   # refinery, steel_plant, power_plant, mine, lng_terminal
    state = Column(String, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)

    # --- Phase 1 additions: provenance + criticality (spec §9) ---
    criticality = Column(String, default="medium")   # low / medium / high / critical — drives risk engine, not just anomaly
    source = Column(String, default="curated_demo")  # curated_demo / osm_derived / external — never claim these 12 are exhaustive
    source_id = Column(String, nullable=True)        # external dataset reference id, if applicable

    hotspots = relationship("Hotspot", back_populates="facility")


class Hotspot(Base):
    __tablename__ = "hotspots"

    id = Column(Integer, primary_key=True, index=True)

    # --- Raw observation (never overwritten by derived values — spec §7) ---
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    brightness = Column(Float, nullable=False)
    confidence = Column(Float, default=0.0)
    frp = Column(Float, nullable=True)               # Fire Radiative Power, if available from source
    acq_date = Column(DateTime, default=datetime.utcnow)
    satellite = Column(String, default="VIIRS_SNPP")
    source = Column(String, default="demo_synthetic")  # demo_synthetic / nasa_firms — spec §28, never blur this line
    source_resolution_m = Column(Integer, default=375)

    # --- Geospatial context ---
    land_cover = Column(String, default="unknown")
    facility_id = Column(Integer, ForeignKey("facilities.id"), nullable=True)
    distance_to_facility_km = Column(Float, nullable=True)   # stored, not just computed-and-discarded (spec §10)
    state = Column(String, index=True, default="unknown")

    # --- Classification (spec §12-13) ---
    category = Column(String, default="unknown")  # industrial_normal / industrial_alert / industrial_new / wildfire / agricultural_burning / unknown
    classification_method = Column(String, default="rules")  # "rules" or "ml_model" — never hidden from the user
    classification_confidence = Column(Float, default=0.0)   # explicitly a "model score", not a calibrated probability unless proven
    model_version = Column(String, nullable=True)             # e.g. "kavach-xgb-v0.1" — null when classified_by rules

    # --- Baseline / anomaly (spec §6, §16) ---
    baseline_status = Column(String, default="INSUFFICIENT_HISTORY")  # NORMAL / ELEVATED / ABNORMAL / INSUFFICIENT_HISTORY
    z_score = Column(Float, default=0.0)
    deviation_percentage = Column(Float, default=0.0)
    persistence_score = Column(Float, default=0.0)

    # --- Evidence + risk (spec §15, §17) ---
    is_anomaly = Column(Boolean, default=False)
    reason = Column(String, default="")
    reason_codes = Column(String, default="")   # comma-separated short codes, e.g. "NEAR_FACILITY,HIGH_DEVIATION"
    risk_score = Column(Float, default=0.0)     # 0-100, "operational prioritization score" — spec §17
    risk_level = Column(String, default="LOW")  # LOW / WATCH / HIGH / CRITICAL

    data_quality = Column(String, default="unknown")  # good / degraded / poor — drives UNKNOWN class eligibility

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    facility = relationship("Facility", back_populates="hotspots")
    alerts = relationship("Alert", back_populates="hotspot")
    verification = relationship("Verification", back_populates="hotspot", uselist=False)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    hotspot_id = Column(Integer, ForeignKey("hotspots.id"))
    severity = Column(String, default="low")   # low / medium / high / critical
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    hotspot = relationship("Hotspot", back_populates="alerts")


class Verification(Base):
    """Human-in-the-loop analyst feedback — spec §22-23. Never auto-retrains; just stores labels."""
    __tablename__ = "verifications"

    id = Column(Integer, primary_key=True, index=True)
    hotspot_id = Column(Integer, ForeignKey("hotspots.id"), unique=True)
    decision = Column(String, nullable=False)  # confirmed_industrial_fire / confirmed_normal_industrial_heat / wildfire / agricultural / false_positive / unknown
    note = Column(String, default="")
    analyst_name = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    hotspot = relationship("Hotspot", back_populates="verification")


class IngestionRun(Base):
    """
    Real record of every FIRMS sync attempt — this is what /data-sources/status
    and POST /data-sources/firms/sync report from. A sync is only ever called
    "successful" here if a real NASA request actually returned 200 and parsed
    without error; there is no code path that marks this row successful
    without that having happened.
    """
    __tablename__ = "ingestion_runs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, default="nasa_firms")
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    success = Column(Boolean, default=False)
    fetched_count = Column(Integer, default=0)
    inserted_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    error_message = Column(String, default="")
