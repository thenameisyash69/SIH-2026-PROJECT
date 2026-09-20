"""
Pulls active thermal anomaly detections from NASA FIRMS' Area API and
static daily CSV mirrors.

Area API: https://firms.modaps.eosdis.nasa.gov/api/area/
Static mirrors: https://firms.modaps.eosdis.nasa.gov/data/active_fire/

Primary sensor is VIIRS_NOAA21_NRT (spec requirement — NOAA-21 is NASA's
newest VIIRS platform; Suomi-NPP is being phased out of NRT products).
Secondary is VIIRS_NOAA20_NRT. Both are pulled by default via
settings.firms_sources — configurable, not hardcoded.

If no map key is set, the Area API returns an empty list rather than
raising — callers fall back to demo data. The static CSV mirrors require
NO MAP_KEY and are used for historical backfill.

This function makes ONE request per configured sensor over the configured
bounding box — never one request per point.
"""
import csv
import io
import logging
import os
from datetime import datetime, timedelta
import requests
from app.config import settings

logger = logging.getLogger(__name__)

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_STATIC_BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"

# Map internal sensor names to FIRMS static-mirror directory/file prefixes.
STATIC_SENSOR_MAP = {
    "VIIRS_NOAA21_NRT": "VIIRS_NOAA21_NRT",
    "VIIRS_NOAA20_NRT": "VIIRS_NOAA20_NRT",
    "VIIRS_SNPP_NRT": "VIIRS_SNPP_NRT",
    "MODIS_Terra": "MODIS_Terra",
    "MODIS_Aqua": "MODIS_Aqua",
}

STATIC_MAX_RETRIES = 3
STATIC_RETRY_BACKOFF_SECONDS = 2


def fetch_firms_static_csv(date, sensor: str = "VIIRS_NOAA21_NRT") -> list[dict]:
    """
    Fetches a single day of FIRMS data from NASA's static daily CSV mirror.

    These mirrors require NO MAP_KEY and contain full global daily
    detections, making them the only viable source for genuine
    multi-day historical backfill (the Area API's day_range always
    counts back from 'now' and NRT retention is ~5 days).

    Args:
        date: datetime.date or datetime — the acquisition date to fetch.
        sensor: internal sensor name (e.g. 'VIIRS_NOAA21_NRT').

    Returns:
        list of dicts with lat, lon, brightness, confidence, frp,
        satellite, acq_date, source_sensor.

    Raises:
        ValueError if the sensor is not supported for static mirrors.
        requests.RequestException on network failure (after retries).
    """
    if isinstance(date, datetime):
        date = date.date()

    if sensor not in STATIC_SENSOR_MAP:
        raise ValueError(
            f"Sensor '{sensor}' is not supported by FIRMS static CSV mirrors. "
            f"Supported: {sorted(STATIC_SENSOR_MAP)}"
        )

    fir_sensor = STATIC_SENSOR_MAP[sensor]
    url = (
        f"{FIRMS_STATIC_BASE}/{fir_sensor}"
        f"/C{date.year}/{fir_sensor}_C{date.strftime('%Y%m%d')}.csv"
    )

    last_exc = None
    for attempt in range(STATIC_MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 404:
                # Date not yet available (future date or data gap) — not an error
                return []
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            last_exc = e
            if attempt < STATIC_MAX_RETRIES - 1:
                import time
                time.sleep(STATIC_RETRY_BACKOFF_SECONDS * (attempt + 1))
    else:
        raise last_exc

    text = resp.text
    if not text or text.strip().lower().startswith(("invalid", "error")):
        return []

    reader = csv.DictReader(io.StringIO(text))
    results = []
    for row in reader:
        try:
            results.append({
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "brightness": float(row.get("bright_ti4", row.get("brightness", 0))),
                "confidence": _parse_confidence(row.get("confidence", "0")),
                "frp": _safe_float(row.get("frp"), default=None) if row.get("frp") else None,
                "satellite": _map_satellite(row.get("satellite", ""), sensor),
                "acq_date": _parse_acq_datetime(row.get("acq_date"), row.get("acq_time")),
                "source_sensor": sensor,
            })
        except (KeyError, ValueError):
            continue
    return results


def fetch_firms_hotspots(day_range: int = 1, sources: list | None = None) -> dict:
    if not settings.firms_map_key:
        return {
            "observations": [],
            "sources": {},
            "errors": {},
        }

    sensors = sources or settings.firms_sources
    all_results = []
    source_results = {}
    errors = {}

    for sensor in sensors:
        try:
            result = _fetch_one_sensor(sensor, day_range)
            rows = result["rows"]
            all_results.extend(rows)
            source_results[sensor] = {
                "rows": len(rows),
                "http_status": result["http_status"],
                "byte_count": result["byte_count"],
                "parse_errors": result["parse_errors"],
            }
            logger.info("[firms_fetcher] Source %s: %d rows, HTTP %s",
                        sensor, len(rows), result["http_status"])
        except Exception as e:
            error_msg = str(e)[:200]
            errors[sensor] = error_msg
            logger.warning("[firms_fetcher] Source %s FAILED: %s", sensor, error_msg)

    return {
        "observations": all_results,
        "sources": source_results,
        "errors": errors,
    }


def _fetch_one_sensor(sensor: str, day_range: int) -> dict:
    url = f"{FIRMS_BASE_URL}/{settings.firms_map_key}/{sensor}/{settings.firms_area}/{day_range}"

    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except requests.Timeout as e:
        logger.warning("[firms_fetcher] Request timed out for %s: %s", sensor, e)
        raise TimeoutError(f"FIRMS request for {sensor} timed out after 60s") from e
    except requests.RequestException as e:
        logger.warning("[firms_fetcher] Request failed for %s: HTTP %s — %s",
                         sensor, getattr(e.response, 'status_code', 'N/A'), str(e)[:200])
        raise

    text = resp.text
    byte_count = len(text.encode('utf-8')) if text else 0
    status_code = resp.status_code

    if text.strip().lower().startswith(("invalid", "error")):
        logger.error("[firms_fetcher] API error for %s — HTTP %s, %d bytes, response: %s",
                      sensor, status_code, byte_count, text[:200])
        raise ValueError(f"FIRMS API returned an error for {sensor}: {text[:200]}")

    reader = csv.DictReader(io.StringIO(text))
    results = []
    parse_errors = 0
    for row in reader:
        try:
            results.append({
                "lat": float(row["latitude"]),
                "lon": float(row["longitude"]),
                "brightness": float(row.get("bright_ti4", row.get("brightness", 0))),
                "confidence": _parse_confidence(row.get("confidence", "0")),
                "frp": _safe_float(row.get("frp"), default=None) if row.get("frp") else None,
                "satellite": _map_satellite(row.get("satellite", ""), sensor),
                "acq_date": _parse_acq_datetime(row.get("acq_date"), row.get("acq_time")),
                "source_sensor": sensor,
            })
        except (KeyError, ValueError):
            parse_errors += 1
            continue

    logger.info("[firms_fetcher] %s — HTTP %s, %d bytes, %d rows parsed, %d parse errors",
                sensor, status_code, byte_count, len(results), parse_errors)

    return {
        "sensor": sensor,
        "rows": results,
        "http_status": status_code,
        "byte_count": byte_count,
        "parse_errors": parse_errors,
    }


def _parse_acq_datetime(acq_date_str, acq_time_str):
    """FIRMS gives acq_date as 'YYYY-MM-DD' and acq_time as e.g. '1345' (HHMM, UTC)."""
    if not acq_date_str:
        return datetime.utcnow()
    try:
        date_part = datetime.strptime(acq_date_str, "%Y-%m-%d")
        if acq_time_str:
            acq_time_str = str(acq_time_str).zfill(4)
            hour, minute = int(acq_time_str[:2]), int(acq_time_str[2:])
            return date_part.replace(hour=hour, minute=minute)
        return date_part
    except (ValueError, TypeError):
        return datetime.utcnow()


def _map_satellite(code: str, sensor: str) -> str:
    mapping = {"N": "Suomi NPP", "1": "NOAA-20", "2": "NOAA-21", "Terra": "Terra", "Aqua": "Aqua"}
    return mapping.get(code) or sensor


def _parse_confidence(raw: str) -> float:
    # VIIRS gives categorical confidence: 'l'/'n'/'h' (single-letter) or
    # 'low'/'nominal'/'high' (full-word). MODIS gives a 0-100 number.
    # The 30/60/90 values are an internal ordinal encoding of NASA's
    # categorical signal — NOT a calibrated probability or percentage.
    mapping = {
        "l": 30.0, "low": 30.0,
        "n": 60.0, "nominal": 60.0,
        "h": 90.0, "high": 90.0,
    }
    if raw is None:
        return 0.0
    try:
        return mapping.get(str(raw).lower(), _safe_float(raw))
    except (ValueError, TypeError):
        return 0.0


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
