# Kavach vs. NASA FIRMS — What Each Actually Does

Kavach does not compete with NASA FIRMS on thermal detection. FIRMS is the
observation infrastructure; Kavach is the interpretation layer built on top of it.

| Capability | NASA FIRMS | Kavach |
|---|---|---|
| Detects thermal anomalies from satellite data | ✅ Yes (VIIRS/MODIS) | Consumes FIRMS' output — does not re-detect |
| Shows hotspots on a map | ✅ Yes (Worldview) | ✅ Yes, same underlying detections |
| Basic timeline of past detections | ✅ Yes | ✅ Yes, plus baseline overlay (see below) |
| Distinguishes fire type (industrial/wildfire/agricultural) | ❌ No — every hotspot looks the same | ✅ Rule engine + optional trained model |
| Associates a hotspot with a specific known facility | ❌ No | ✅ `facility_matcher.py`, with stored distance, not a guess |
| Facility-specific "what's normal for THIS site" baseline | ❌ No | ✅ `facility_fingerprint.py` + `baseline_engine.py` |
| Explains *why* something was flagged | ❌ No | ✅ `evidence_engine.py` — supporting/contradicting evidence, not just a score |
| Risk prioritization weighted by facility importance | ❌ No | ✅ `risk_engine.py` — a CRITICAL refinery's deviation outranks a minor mine's |
| Human analyst feedback loop | ❌ No | ✅ `/hotspots/{id}/verify` — stored, not auto-retrained |
| Explicit "not enough evidence" state | ❌ Not applicable | ✅ `UNKNOWN` category + `INSUFFICIENT_HISTORY` baseline status |

**We do not claim FIRMS lacks a timeline, a thermal anomaly layer, or persistent-source
visibility — it has all of these.** What it does not do is tell an analyst whether a
given persistent industrial heat source is behaving normally for *that specific site*,
or explain in plain language why an event might be worth investigating.

**One-line summary:** *NASA FIRMS detects the thermal observation. Kavach determines
its industrial context, compares it against that facility's own historical behavior,
and produces an explainable, risk-weighted assessment for a human analyst to verify.*
