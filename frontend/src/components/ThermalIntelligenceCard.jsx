import { useEffect, useState } from 'react'
import { fetchFacilityThermalHistory } from '../api'

/**
 * Compact baseline-intelligence card for the Command Center.
 *
 * Shows the CURRENT thermal reading alongside the 90-day baseline for the
 * selected hotspot's facility. Uses ONLY the existing thermal-history API —
 * it does NOT duplicate or recalculate any baseline logic.
 *
 * For insufficient history it shows "INSUFFICIENT HISTORY" plus the real
 * observation count and current thermal values. It never fabricates a
 * z-score or deviation percentage.
 */
export default function ThermalIntelligenceCard({ hotspot }) {
  const [history, setHistory] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!hotspot || hotspot.source !== 'nasa_firms' || !hotspot.facility) {
      setHistory(null)
      return
    }
    let cancelled = false
    setLoading(true)
    fetchFacilityThermalHistory(hotspot.facility.id, 90, 'nasa_firms')
      .then((data) => { if (!cancelled) setHistory(data) })
      .catch(() => { if (!cancelled) setHistory(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [hotspot])

  if (!hotspot) {
    return (
      <div className="thermal-intel-card thermal-intel-card--empty">
        <span className="thermal-intel-card__eyebrow">THERMAL INTELLIGENCE</span>
        <p>Select a hotspot to see baseline intelligence.</p>
      </div>
    )
  }

  const insufficient = hotspot.baseline_status === 'INSUFFICIENT_HISTORY'
  const zDisplay = (insufficient || hotspot.z_score == null) ? '—' : hotspot.z_score
  const devDisplay = (insufficient || hotspot.deviation_percentage == null) ? '—' : hotspot.deviation_percentage

  return (
    <div className="thermal-intel-card">
      <div className="thermal-intel-card__head">
        <span className="thermal-intel-card__eyebrow">THERMAL INTELLIGENCE</span>
        <span className="thermal-intel-card__facility">
          {hotspot.facility ? hotspot.facility.name : 'Unregistered location'}
        </span>
      </div>

      <div className="thermal-intel-card__current">
        <span className="thermal-intel-card__label">Current brightness</span>
        <span className="thermal-intel-card__value">
          {hotspot.brightness != null ? hotspot.brightness.toFixed(1) : '—'} K
        </span>
      </div>

      <div className="thermal-intel-card__row">
        <div>
          <span className="thermal-intel-card__label">90-day median</span>
          <span className="thermal-intel-card__value">
            {history && !insufficient && history.median != null ? history.median.toFixed(1) : '—'}K
          </span>
        </div>
        <div>
          <span className="thermal-intel-card__label">Baseline P95</span>
          <span className="thermal-intel-card__value">
            {history && !insufficient && history.p95 != null ? history.p95.toFixed(1) : '—'}K
          </span>
        </div>
      </div>

      <div className="thermal-intel-card__row">
        <div>
          <span className="thermal-intel-card__label">Z-score</span>
          <span className="thermal-intel-card__value">{zDisplay}</span>
        </div>
        <div>
          <span className="thermal-intel-card__label">Deviation %</span>
          <span className="thermal-intel-card__value">{devDisplay}{devDisplay !== '—' ? '%' : ''}</span>
        </div>
      </div>

      <div className="thermal-intel-card__row">
        <div>
          <span className="thermal-intel-card__label">Persistence</span>
          <span className="thermal-intel-card__value">
            {hotspot.persistence_score != null ? hotspot.persistence_score.toFixed(2) : '—'}
          </span>
        </div>
        <div>
          <span className="thermal-intel-card__label">History sufficiency</span>
          <span className={`thermal-intel-card__value ${insufficient ? 'thermal-intel-card__value--insufficient' : ''}`}>
            {loading ? 'Loading…' : insufficient ? 'INSUFFICIENT HISTORY' : 'Sufficient'}
          </span>
        </div>
      </div>

      <div className="thermal-intel-card__row">
        <div>
          <span className="thermal-intel-card__label">Baseline status</span>
          <span className="thermal-intel-card__value">{hotspot.baseline_status.replace(/_/g, ' ')}</span>
        </div>
        <div>
          <span className="thermal-intel-card__label">Observations</span>
          <span className="thermal-intel-card__value">
            {history ? history.observation_count : '—'}
          </span>
        </div>
      </div>

      {insufficient && (
        <p className="thermal-intel-card__note">
          Insufficient history — recurrence and deviation cannot be computed.
          Current brightness/FRP are real stored values.
        </p>
      )}
    </div>
  )
}