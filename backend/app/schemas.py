from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class FacilityOut(BaseModel):
    id: int
    name: str
    type: str
    state: str
    lat: float
    lon: float
    criticality: str
    source: str

    class Config:
        from_attributes = True


class HotspotOut(BaseModel):
    id: int
    lat: float
    lon: float
    brightness: float
    confidence: float
    frp: Optional[float] = None
    acq_date: datetime
    satellite: str
    source: str                      # demo_synthetic / nasa_firms — always shown, never hidden
    land_cover: str
    facility: Optional[FacilityOut] = None
    distance_to_facility_km: Optional[float] = None
    state: str

    category: str
    classification_method: str
    classification_confidence: float
    model_version: Optional[str] = None

    baseline_status: str
    z_score: float
    deviation_percentage: float
    persistence_score: float

    is_anomaly: bool
    reason: str
    reason_codes: str
    risk_score: float
    risk_level: str
    data_quality: str

    class Config:
        from_attributes = True


class AlertOut(BaseModel):
    id: int
    hotspot_id: int
    severity: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    matched_count: int


class VerificationIn(BaseModel):
    decision: str   # confirmed_industrial_fire / confirmed_normal_industrial_heat / wildfire / agricultural / false_positive / unknown
    note: Optional[str] = ""
    analyst_name: Optional[str] = ""


class VerificationOut(BaseModel):
    id: int
    hotspot_id: int
    decision: str
    note: str
    analyst_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class FacilityFingerprintOut(BaseModel):
    facility_id: int
    facility_name: str
    observation_count: int
    baseline_status: str = "INSUFFICIENT_HISTORY"  # INSUFFICIENT_HISTORY / PROVISIONAL / ESTABLISHED
    baseline_mean: Optional[float] = None
    baseline_median: Optional[float] = None
    baseline_std: Optional[float] = None
    baseline_p95: Optional[float] = None
    recent_7d_count: int
    recent_30d_count: int
    recent_60d_count: int
    persistence_score: float
    recurrence_rate: float
    behavior_label: str   # PERSISTENT_EXPECTED / PERSISTENT_UNEXPECTED / INSUFFICIENT_HISTORY / IRREGULAR / PROVISIONAL
    historical_anomaly_count: int


class ThermalHistoryBin(BaseModel):
    bin_start: float
    bin_end: float
    count: int


class ThermalObservationRow(BaseModel):
    hotspot_id: int
    acq_date: Optional[str] = None
    brightness: Optional[float] = None
    frp: Optional[float] = None
    confidence: Optional[float] = None
    z_score: Optional[float] = None
    deviation_percentage: Optional[float] = None
    baseline_status: Optional[str] = None
    is_anomaly: bool = False


class ThermalHistoryOut(BaseModel):
    facility_id: int
    facility_name: str
    source: str
    window_days: int
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    observation_count: int
    unique_active_days: Optional[int] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    p95: Optional[float] = None
    current_brightness: Optional[float] = None
    insufficient_history: bool = False
    baseline_status: str = "INSUFFICIENT_HISTORY"
    confidence: str = ""
    limitations: str = ""
    histogram: List[ThermalHistoryBin] = []
    observations: List[ThermalObservationRow] = []
    sudden_rise_level: Optional[str] = None


class GeographicFeatureOut(BaseModel):
    name: str
    kind: str
    distance_m: float
    source: str
    tags: dict = {}


class GeographicContextOut(BaseModel):
    hotspot_id: int
    lat: float
    lon: float
    radius_m: int
    feature_count: int
    features: List[GeographicFeatureOut] = []


class DataSourceStatusOut(BaseModel):
    name: str
    status: str          # ok / degraded / not_configured / error
    detail: str
    last_checked: datetime
