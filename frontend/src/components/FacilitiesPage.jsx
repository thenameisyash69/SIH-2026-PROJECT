import { useEffect, useState } from 'react'
import { fetchFacilities, fetchFacilityFingerprint, fetchHotspots } from '../api'

const CRITICALITY_TONE = { low: 'low', medium: 'watch', high: 'high', critical: 'critical' }

export default function FacilitiesPage() {
  const [facilities, setFacilities] = useState([])
  const [selected, setSelected] = useState(null)
  const [fingerprint, setFingerprint] = useState(null)
  const [latestHotspot, setLatestHotspot] = useState(null)
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    fetchFacilities()
      .then((data) => { setFacilities(data); setStatus('ready'); if (data.length) selectFacility(data[0]) })
      .catch(() => setStatus('error'))
  }, [])

  async function selectFacility(facility) {
    setSelected(facility)
    setFingerprint(null)
    setLatestHotspot(null)
    try {
      const [fp, hotspots] = await Promise.all([
        fetchFacilityFingerprint(facility.id),
        fetchHotspots({ facility_id: facility.id, limit: 1 }),
      ])
      setFingerprint(fp)
      setLatestHotspot(hotspots[0] || null)
    } catch {
      setFingerprint(null)
    }
  }

  if (status === 'loading') return <p className="empty">Loading facilities…</p>
  if (status === 'error') return <p className="empty">Could not load facilities — is the backend running?</p>

  return (
    <div className="facilities-page">
      <div className="facilities-list">
        {facilities.map((f) => (
          <button
            key={f.id}
            className={`facility-card ${selected?.id === f.id ? 'facility-card--active' : ''}`}
            onClick={() => selectFacility(f)}
          >
            <div className="facility-card__name">{f.name}</div>
            <div className="facility-card__meta">
              {f.type.replace('_', ' ')} · {f.state}
            </div>
            <span className={`badge badge--risk-${CRITICALITY_TONE[f.criticality] || 'low'}`}>
              {f.criticality} criticality
            </span>
            <span className="facility-card__source">{f.source === 'curated_demo' ? 'curated demo' : f.source}</span>
          </button>
        ))}
      </div>

      <div className="facility-detail">
        {!selected && <p className="empty">Select a facility to view its thermal fingerprint.</p>}
        {selected && (
          <>
            <h2>{selected.name}</h2>
            <p className="facility-detail__identity">
              {selected.type.replace('_', ' ')} · {selected.state} · {selected.lat.toFixed(4)}, {selected.lon.toFixed(4)}
              {' · '}<span className={`badge badge--risk-${CRITICALITY_TONE[selected.criticality] || 'low'}`}>{selected.criticality}</span>
              {' '}<span className="badge badge--source">{selected.source}</span>
            </p>

            {!fingerprint && <p className="empty">Loading thermal fingerprint…</p>}

            {fingerprint && (
              <>
                <h3>Thermal fingerprint</h3>
                {fingerprint.behavior_label === 'INSUFFICIENT_HISTORY' ? (
                  <p className="empty">Insufficient historical observations for a reliable baseline yet
                    ({fingerprint.observation_count} observation(s) so far — need at least 8).</p>
                ) : (
                  <>
                    {fingerprint.behavior_label === 'PROVISIONAL' && (
                      <p className="empty">Provisional baseline — {fingerprint.observation_count} observation(s),
                        {fingerprint.recent_30d_count} in last 30d — still accumulating history
                        (need at least 8 across 8 unique days).
                      </p>
                    )}
                    <div className="fingerprint-grid">
                      <div><strong>{fingerprint.observation_count}</strong><span>observations</span></div>
                      <div><strong>{fingerprint.baseline_mean != null ? fingerprint.baseline_mean.toFixed(1) : '—'}</strong><span>baseline mean</span></div>
                      <div><strong>{fingerprint.baseline_median != null ? fingerprint.baseline_median.toFixed(1) : '—'}</strong><span>baseline median</span></div>
                      <div><strong>{fingerprint.baseline_p95 != null ? fingerprint.baseline_p95.toFixed(1) : '—'}</strong><span>baseline P95</span></div>
                      <div><strong>{fingerprint.persistence_score}</strong><span>persistence score</span></div>
                      <div><strong>{fingerprint.recurrence_rate}</strong><span>recurrence rate</span></div>
                    </div>
                  </>
                )}

                <div className="behavior-label-row">
                  <span className={`badge behavior-badge--${fingerprint.behavior_label}`}>
                    {fingerprint.behavior_label.replace(/_/g, ' ')}
                  </span>
                  {fingerprint.behavior_label === 'PERSISTENT_EXPECTED' && (
                    <p className="detail__disclaimer">This facility is persistently hot AND that has always been
                      normal for it — Kavach does not treat persistence itself as suspicious.</p>
                  )}
                  {fingerprint.behavior_label === 'PERSISTENT_UNEXPECTED' && (
                    <p className="detail__disclaimer">This facility is persistently active but recent readings
                      diverge from its own historical pattern — worth investigating.</p>
                  )}
                  {fingerprint.behavior_label === 'PROVISIONAL' && (
                    <p className="detail__disclaimer">Provisional baseline — recent readings are compared against
                      an incomplete history. Re-evaluate once 8+ observations across 8+ days exist.</p>
                  )}
                </div>

                <h3>Recent activity</h3>
                <div className="fingerprint-grid">
                  <div><strong>{fingerprint.recent_7d_count}</strong><span>last 7 days</span></div>
                  <div><strong>{fingerprint.recent_30d_count}</strong><span>last 30 days</span></div>
                  <div><strong>{fingerprint.recent_60d_count}</strong><span>last 60 days</span></div>
                  <div><strong>{fingerprint.historical_anomaly_count}</strong><span>historical anomalies</span></div>
                </div>

                <h3>Current assessment</h3>
                {latestHotspot ? (
                  <div className="baseline-row">
                    <div><strong>{latestHotspot.category.replace(/_/g, ' ')}</strong><span>classification</span></div>
                    <div><strong>{latestHotspot.risk_level}</strong><span>risk ({latestHotspot.risk_score})</span></div>
                    <div><strong>{latestHotspot.baseline_status}</strong><span>baseline status</span></div>
                    <div><strong>{latestHotspot.data_quality}</strong><span>data quality</span></div>
                  </div>
                ) : (
                  <p className="empty">No hotspot observations recorded for this facility yet.</p>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
