import { useMemo } from 'react'

/**
 * Deterministic "sudden-rise" indicator derived ONLY from already-stored
 * backend values. This is NOT a fire detector — it is a display triage
 * label for unusual thermal activity so the analyst can spot it quickly.
 *
 * Levels (mutually exclusive, evaluated in order):
 *   INSUFFICIENT_HISTORY — no usable baseline
 *   PROVISIONAL          — some history exists but < 8 obs / < 8 unique
 *                          days; baseline stats are computed but not stable
 *   SUDDEN_THERMAL_SPIKE  — z-score above the abnormal threshold
 *   ELEVATED              — z-score above the elevated threshold
 *   NORMAL_RANGE          — otherwise
 */
export function suddenRiseLevel(hotspot, thermalHistory) {
  if (!thermalHistory) return 'UNKNOWN'
  if (thermalHistory.insufficient_history) return 'INSUFFICIENT_HISTORY'
  if (thermalHistory.baseline_status === 'PROVISIONAL') return 'PROVISIONAL'

  const z = hotspot?.z_score
  if (z == null) return 'NORMAL_RANGE'

  // Z_ABNORMAL = 2.5, Z_ELEVATED = 1.5 (baseline_engine constants)
  if (z >= 2.5) return 'SUDDEN_THERMAL_SPIKE'
  if (z >= 1.5) return 'ELEVATED'
  return 'NORMAL_RANGE'
}

const LEVEL_META = {
  NORMAL_RANGE: { label: 'Normal range', tone: 'normal', note: 'Within historical operating band.' },
  ELEVATED: { label: 'Elevated', tone: 'elevated', note: 'Above the facility\'s elevated threshold — unusual for this site.' },
  SUDDEN_THERMAL_SPIKE: { label: 'Sudden thermal spike', tone: 'spike', note: 'Well above the facility\'s historical baseline. This is unusual thermal activity, NOT a confirmed fire.' },
  PROVISIONAL: { label: 'Provisional — limited history', tone: 'provisional', note: 'Some NASA FIRMS history exists but is not yet sufficient for a stable baseline (minimum 8 observations across 8 unique active days). Statistics are real but not yet stable.' },
  INSUFFICIENT_HISTORY: { label: 'Insufficient history', tone: 'insufficient', note: 'Not enough NASA FIRMS history to establish a baseline for this facility.' },
  UNKNOWN: { label: 'Unknown', tone: 'unknown', note: 'No baseline data available.' },
}

export function SuddenRiseIndicator({ hotspot, thermalHistory }) {
  const level = suddenRiseLevel(hotspot, thermalHistory)
  const meta = LEVEL_META[level] || LEVEL_META.UNKNOWN
  return (
    <div className={`sudden-rise sudden-rise--${meta.tone}`}>
      <span className="sudden-rise__badge">{meta.label}</span>
      <span className="sudden-rise__note">{meta.note}</span>
    </div>
  )
}

/**
 * Compact bar chart of per-observation brightness over time.
 * Uses ONLY real NASA FIRMS rows returned by the API. Never fabricates.
 */
export default function ThermalHistoryChart({ observations, baseline, selectedHotspotId, baselineStatus }) {
  const { max, min, rows } = useMemo(() => {
    const vals = observations.map((o) => o.brightness).filter((v) => v != null)
    const maxV = Math.max(...vals, baseline?.p95 || 0, 1)
    const minV = Math.min(...vals, 1)
    return { max: maxV, min: minV, rows: observations }
  }, [observations, baseline])

  if (!rows || rows.length === 0) {
    return <p className="empty">No observation-level history available for this chart.</p>
  }

  const range = (max - min) || 1

  return (
    <div className="thermal-chart">
      {baselineStatus === 'PROVISIONAL' && (
        <div className="thermal-chart__provisional-banner">
          <span className="thermal-chart__provisional-flag">PROVISIONAL — limited history</span>
          <span className="thermal-chart__provisional-note">
            {observations.length} observation(s) shown — minimum {8} required for a stable baseline.
            Statistics are real but not yet reliable.
          </span>
        </div>
      )}
      <div className="thermal-chart__bars">
        {rows.map((o) => {
          const heightPct = 12 + ((o.brightness - min) / range) * 88
          const isSelected = o.hotspot_id === selectedHotspotId
          const aboveP95 = baseline?.p95 != null && o.brightness > baseline.p95
          const aboveMean = baseline?.mean != null && o.brightness > baseline.mean
          const isAnomaly = o.is_anomaly
          let cls = 'thermal-chart__bar'
          if (isSelected) cls += ' thermal-chart__bar--selected'
          else if (isAnomaly) cls += ' thermal-chart__bar--anomaly'
          else if (aboveP95) cls += ' thermal-chart__bar--above'

          const titleParts = [
            `Date: ${o.acq_date ? new Date(o.acq_date).toLocaleString() : '—'}`,
            `Brightness: ${o.brightness != null ? o.brightness.toFixed(1) + ' K' : '—'}`,
            `FRP: ${o.frp != null ? o.frp.toFixed(1) + ' MW' : '—'}`,
            `z-score: ${o.z_score != null ? o.z_score.toFixed(2) : '—'}`,
            `Deviation: ${o.deviation_percentage != null ? o.deviation_percentage.toFixed(1) + '%' : '—'}`,
            `Baseline: ${o.baseline_status || '—'}`,
            isSelected ? '★ SELECTED observation' : '',
          ].filter(Boolean)

          return (
            <div
              key={o.hotspot_id}
              className={cls}
              style={{ height: `${heightPct}%` }}
              title={titleParts.join('\n')}
            >
              {aboveP95 && !isSelected && (
                <span className="thermal-chart__flag" title="Above historical baseline">↑</span>
              )}
              {aboveMean && !aboveP95 && !isSelected && (
                <span className="thermal-chart__flag thermal-chart__flag--mean" title="Above mean baseline">↑</span>
              )}
            </div>
          )
        })}
      </div>
      <div className="thermal-chart__labels">
        <span>{new Date(rows[0].acq_date).toLocaleDateString()}</span>
        <span>{new Date(rows[rows.length - 1].acq_date).toLocaleDateString()}</span>
      </div>
      {baseline && (
        <div className="thermal-chart__baseline">
          {baseline.mean != null && (
            <span>Mean {baseline.mean.toFixed(1)} K</span>
          )}
          {baseline.p95 != null && (
            <span>P95 {baseline.p95.toFixed(1)} K</span>
          )}
          <span className="thermal-chart__legend">
            <i className="thermal-chart__dot thermal-chart__dot--selected" /> Selected
            <i className="thermal-chart__dot thermal-chart__dot--above" /> Above baseline
            <i className="thermal-chart__dot thermal-chart__dot--anomaly" /> Anomaly
          </span>
        </div>
      )}
    </div>
  )
}