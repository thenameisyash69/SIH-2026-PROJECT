# Kavach Scoring Methodology

All formulas below are implemented exactly as described — nothing here is
aspirational or hand-waved. Code references are the source of truth.

## 1. Baseline (`app/services/baseline_engine.py`)

For a facility with ≥ 8 historical brightness readings:
- `mean`, `median`, `std` (population stdev), `p95` computed directly from history.
- Fewer than 8 readings → `baseline_status = INSUFFICIENT_HISTORY`, and no
  z-score/deviation is calculated at all (returning a fabricated number from
  too little data would be worse than admitting we don't know yet).

## 2. Deviation

```
z_score = (new_brightness - baseline_mean) / baseline_std
deviation_percentage = ((new_brightness - baseline_mean) / baseline_mean) * 100

baseline_status:
  |z| >= 2.5  -> ABNORMAL
  |z| >= 1.5  -> ELEVATED
  else        -> NORMAL
```

These thresholds (1.5 / 2.5 standard deviations) are a standard statistical
convention for "notable" vs. "extreme" deviation — they are a reasonable
starting point, not a validated operational threshold. This is explicitly
called out in `docs/LIMITATIONS.md`.

## 3. Facility Behavior Label (`facility_fingerprint.py`)

```
persistence_score = min(1.0, observation_count / days_spanned)
recurrence_rate   = recent_30_day_count / 30

behavior_label:
  observation_count < 8              -> INSUFFICIENT_HISTORY
  persistence >= 0.6 AND
    historical_anomaly_rate < 15%    -> PERSISTENT_EXPECTED
  persistence >= 0.6 (otherwise)     -> PERSISTENT_UNEXPECTED
  else                               -> IRREGULAR
```

This is the mechanism that prevents "this facility is always hot" from being
treated as inherently suspicious — the naive mistake a pure anomaly-on-brightness
system makes.

## 4. Evidence Score (`evidence_engine.py`)

Each independent signal (facility proximity, baseline deviation, source
confidence, land-cover context, seasonal pattern, facility behavior label,
data quality) contributes either to `supporting_evidence` or
`contradicting_evidence`, each tagged with a short `reason_code`.

```
evidence_score = count(supporting) - count(contradicting)
```

This is deliberately simple and auditable — every point either supports or
contradicts, in plain English, rather than being folded into an opaque
weighted sum.

## 5. Anomaly Score (`anomaly_engine.py`)

```
if baseline_status == INSUFFICIENT_HISTORY:
    anomaly_status = UNKNOWN, score = 0

if behavior_label == PERSISTENT_EXPECTED and baseline_status != ABNORMAL:
    anomaly_status = NORMAL, score = 5   # persistent ≠ automatically flagged

else:
    base_score = {NORMAL: 10, ELEVATED: 45, ABNORMAL: 80}[baseline_status]
    score = clamp(base_score + evidence_score * 4, 0, 100)
    anomaly_status = ABNORMAL if score>=70 else ELEVATED if score>=35 else NORMAL
```

## 6. Risk Score (`risk_engine.py`) — explicitly NOT the same as anomaly score

```
criticality_weight = {low: 0.6, medium: 0.8, high: 1.0, critical: 1.25}
data_quality_factor = {good: 1.0, degraded: 0.85, poor: 0.6, unknown: 0.75}
confidence_factor = min(1.0, source_confidence / 100)

risk_score = anomaly_score
           * criticality_weight[facility.criticality]
           * data_quality_factor
           * (0.5 + 0.5 * confidence_factor)

risk_level:
  score >= 75 -> CRITICAL
  score >= 50 -> HIGH
  score >= 25 -> WATCH
  else        -> LOW
  (UNKNOWN anomaly status always maps to WATCH, never LOW or CRITICAL)
```

**This is explicitly called an "operational prioritization score."** It does
not predict casualties, financial loss, or disaster outcomes — it exists only
to help an analyst decide what to look at first.

## 7. Classification confidence

The ML model's `predict_proba()` output is stored and displayed as a
**"model score,"** never as "probability" or "confidence" in the calibrated-
statistics sense, because the model has not been calibrated (e.g. via
Platt scaling) against real-world outcomes. See `docs/ML_EVALUATION.md`
for what would be needed to justify calling it a true probability.
