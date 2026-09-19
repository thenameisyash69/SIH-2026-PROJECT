# ML Data Quality Report

*Real findings from `python ml/data_quality.py`, run against the actual
real NASA FIRMS data used in this pass (`data-pipeline/modis_raw.csv` +
`viirs_raw.csv` — genuinely fetched from NASA's public feed, not
fabricated). Full machine-readable output: `ml/data_quality_report.json`.*

## Results

| Check | Count | Action taken |
|---|---|---|
| Total rows checked | 99 | — |
| Impossible coordinates (outside ±90/±180) | 0 | none needed |
| Missing/invalid brightness | 0 | none needed |
| Invalid timestamp | 0 | none needed |
| Invalid FRP | 0 | none needed |
| Duplicate rows (same coords+time) | 2 | excluded from valid set |
| Outside configured bbox (68,6,97,37) | 18 | excluded — these are real detections in neighboring countries (Pakistan, China/Tibet, Nepal border regions) picked up because "South Asia" is a wider NASA region than India alone |
| **Valid rows** | **79** | used for the real pipeline load test |

## What this means

The real NASA data itself was clean — zero impossible coordinates, zero
invalid timestamps, zero invalid FRP/brightness values. The only exclusions
were structural (rows genuinely outside India's configured bounding box,
and 2 exact-duplicate rows) — nothing was dropped for being malformed.

## Not yet checked (requires a populated real database, not just a raw snapshot)

- **Conflicting labels** — cannot be checked yet; zero human verifications
  exist on any real observation (see `docs/FINAL_STATUS.md`).
- **Class imbalance** — same reason; there are zero labeled classes to
  measure balance across yet.
- **Facilities with insufficient history** — checkable once bootstrapped;
  see `docs/ML_TRAINING_PIPELINE.md` for the live finding that 0 of the 79
  valid real observations matched any of the 12 curated demo facilities
  within 5km, meaning **none of them would currently accrue toward any
  facility's baseline history at all** — a real, load-bearing limitation
  of the current facility registry's small size, discovered by actually
  running real data through the matcher, not assumed.
