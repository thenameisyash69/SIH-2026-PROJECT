import { useState, useEffect } from 'react'
import Timeline from './Timeline'
import ThermalHistoryChart, { SuddenRiseIndicator } from './ThermalHistoryChart'
import DeepInvestigationMap from './DeepInvestigationMap'
import ThermalIntelligenceCard from './ThermalIntelligenceCard'
import { fetchAssessment, verifyHotspot, fetchFacilityThermalHistory, fetchGeographicContext, fetchDataSourceStatus } from '../api'
import { getThermalSeverity } from '../utils/thermalSeverity'

const CATEGORY_LABEL = {
  industrial_alert: 'Industrial — Alert',
  industrial_new: 'Industrial — New / Unverified',
  industrial_normal: 'Industrial — Normal',
  wildfire: 'Wildfire',
  agricultural_burning: 'Agricultural Burning',
  unknown: 'Unknown — insufficient evidence',
}

const RISK_TONE = { LOW: 'low', WATCH: 'watch', HIGH: 'high', CRITICAL: 'critical' }

// Kept for the compact evidence-summary grid below — a coarse read only.
// The authoritative display triage now lives in getThermalSeverity().
function thermalSignalLabel(brightness) {
  if (brightness >= 340) return 'Strong'
  if (brightness >= 310) return 'Moderate'
  return 'Weak'
}

function formatAcqDate(hotspot) {
  if (!hotspot.acq_date) return '—'
  const d = new Date(hotspot.acq_date)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC'
}

function facilityAssociationLabel(hotspot) {
  if (!hotspot.facility) return 'No facility'
  if (hotspot.distance_to_facility_km !== null && hotspot.distance_to_facility_km <= 0.5) return 'Exact mapped facility context'
  return 'Nearby facility'
}

const VERIFY_OPTIONS = [
  { value: 'confirmed_industrial_fire', label: 'Confirm industrial fire' },
  { value: 'confirmed_normal_industrial_heat', label: 'Confirm normal industrial heat' },
  { value: 'wildfire', label: 'Mark wildfire' },
  { value: 'agricultural', label: 'Mark agricultural' },
  { value: 'false_positive', label: 'Mark false positive' },
  { value: 'unknown', label: 'Mark unknown' },
]

export default function DetailPanel({ hotspot, hotspots = [], deep = false, compact = false }) {
  const [assessment, setAssessment] = useState(null)
  const [assessing, setAssessing] = useState(false)
  const [verifyStatus, setVerifyStatus] = useState(null)
  const [thermalHistory, setThermalHistory] = useState(null)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [geoContext, setGeoContext] = useState(null)
  const [loadingGeo, setLoadingGeo] = useState(false)
  const [syncStatus, setSyncStatus] = useState(null)

  // 90-day NASA thermal history + nearby geographic features are
  // investigation-level concerns: they belong to Deep Analysis, not to the
  // compact Command Center detail view. They are only fetched when deep=true,
  // so a normal Command Center click never triggers extra investigation
  // requests.
  useEffect(() => {
    if (!deep || !hotspot || hotspot.source !== 'nasa_firms' || !hotspot.facility) {
      setThermalHistory(null)
      return
    }
    let cancelled = false
    setLoadingHistory(true)
    fetchFacilityThermalHistory(hotspot.facility.id, 90, 'nasa_firms')
      .then((data) => { if (!cancelled) setThermalHistory(data) })
      .catch(() => { if (!cancelled) setThermalHistory(null) })
      .finally(() => { if (!cancelled) setLoadingHistory(false) })
    return () => { cancelled = true }
  }, [deep, hotspot])

  useEffect(() => {
    if (!deep || !hotspot) {
      setGeoContext(null)
      return
    }
    let cancelled = false
    setLoadingGeo(true)
    fetchGeographicContext(hotspot.id)
      .then((data) => { if (!cancelled) setGeoContext(data) })
      .catch(() => { if (!cancelled) setGeoContext(null) })
      .finally(() => { if (!cancelled) setLoadingGeo(false) })
    return () => { cancelled = true }
  }, [deep, hotspot])

  // Track last successful FIRMS sync for baseline context.
  useEffect(() => {
    let cancelled = false
    fetchDataSourceStatus()
      .then((data) => {
        if (cancelled) return
        const firms = data.find((s) => s.name === 'NASA FIRMS')
        setSyncStatus(firms || null)
      })
      .catch(() => { /* sync status is display-only */ })
    return () => { cancelled = true }
  }, [])

  if (!hotspot) {
    return <p className="empty">Click any hotspot on the map to open its full investigation view — classification, evidence, baseline deviation, satellite context, and history.</p>
  }

  async function handleAssess() {
    setAssessing(true)
    try {
      const result = await fetchAssessment(hotspot.id)
      setAssessment(result)
    } catch {
      setAssessment(null)
    } finally {
      setAssessing(false)
    }
  }

  async function handleVerify(decision) {
    try {
      await verifyHotspot(hotspot.id, decision, '')
      setVerifyStatus(`Recorded: ${decision.replace(/_/g, ' ')}`)
    } catch {
      setVerifyStatus('Could not save verification — is the backend running?')
    }
  }

  const reasonCodes = (hotspot.reason_codes || '').split(',').filter(Boolean)
  const supportingCodes = reasonCodes.filter((c) => !c.startsWith('CONTRADICTING_') && c !== 'INSUFFICIENT_HISTORY')
  const contradictingCodes = reasonCodes.filter((c) => c.startsWith('CONTRADICTING_'))

  // When the backend has no usable history it stores z_score/deviation as
  // 0.0 (see baseline_engine.compute_baseline). Those zeros are NOT real
  // measurements — they mean "not calculated". Show them as unavailable
  // instead of implying a measured zero deviation.
  const insufficient = hotspot.baseline_status === 'INSUFFICIENT_HISTORY'
  const zDisplay = (insufficient || hotspot.z_score == null) ? '—' : hotspot.z_score
  const devDisplay = (insufficient || hotspot.deviation_percentage == null) ? '—' : hotspot.deviation_percentage

  // 5. LIKELY CAUSE — evidence-based interpretation, NOT confirmed ground truth.
  const likelyCauseLabel = {
    industrial_normal: 'Normal industrial heat',
    industrial_alert: 'Industrial combustion / flare',
    industrial_new: 'Suspected industrial fire',
    wildfire: 'Wildland vegetation burning',
    agricultural_burning: 'Agricultural burning',
    unknown: 'Unknown',
  }
  const likelyCause = likelyCauseLabel[hotspot.category] || 'Other'

  // 4. WHY THIS RISK? — explain the stored risk calculation without
  // inventing new weights. Mirrors backend risk_engine.assess_risk.
  const criticalityWeight = { low: 0.6, medium: 0.8, high: 1.0, critical: 1.25 }
  const qualityPenalty = { good: 1.0, degraded: 0.85, poor: 0.6, unknown: 0.75 }
  const facilityCrit = hotspot.facility ? hotspot.facility.criticality : 'low'
  const dataQuality = hotspot.data_quality || 'unknown'
  const critWeight = criticalityWeight[facilityCrit] ?? 0.6
  const qualFactor = qualityPenalty[dataQuality] ?? 0.75
  const confFactor = Math.min(1.0, ((hotspot.classification_confidence || 50) / 100))

  return (
    <div className="detail">
      <div className="detail__source-flag">
        {hotspot.source === 'nasa_firms' ? '🛰 REAL — NASA FIRMS' : '◆ DEMO — synthetic data'}
      </div>

      <h3>{hotspot.facility ? hotspot.facility.name : 'Unregistered location'}</h3>

      {/* RAW NASA THERMAL SIGNAL — display-only triage from raw brightness/frp.
          This is NOT a fire diagnosis, NOT a KAVACH risk score. */}
      <div className="thermal-signal-block">
        <div className="thermal-signal-block__head">
          <span className="thermal-signal-block__eyebrow">RAW NASA THERMAL SIGNAL</span>
        </div>
        <div className={`thermal-signal-badge thermal-sev--${getThermalSeverity(hotspot.brightness, hotspot.frp).key}`}>
          <span className="thermal-signal-badge__dot" />
          <span className="thermal-signal-badge__label">{getThermalSeverity(hotspot.brightness, hotspot.frp).label.toUpperCase()} THERMAL SIGNAL</span>
        </div>
        <div className="thermal-signal-readings">
          <div className="thermal-signal-reading">
            <span className="thermal-signal-reading__label">Brightness</span>
            <span className="thermal-signal-reading__value">{hotspot.brightness != null ? hotspot.brightness.toFixed(2) : '—'} K</span>
          </div>
          <div className="thermal-signal-reading">
            <span className="thermal-signal-reading__label">FRP</span>
            <span className="thermal-signal-reading__value">{hotspot.frp != null ? hotspot.frp.toFixed(2) : '—'} MW</span>
          </div>
          <div className="thermal-signal-reading">
            <span className="thermal-signal-reading__label">Satellite</span>
            <span className="thermal-signal-reading__value">{hotspot.satellite || '—'}</span>
          </div>
          <div className="thermal-signal-reading">
            <span className="thermal-signal-reading__label">Acquired</span>
            <span className="thermal-signal-reading__value">{formatAcqDate(hotspot)}</span>
          </div>
        </div>
        <p className="thermal-signal-block__note">
          Thermal signal indicates satellite-observed intensity only.
          It is not a fire diagnosis or KAVACH risk score.
        </p>
      </div>

      <div className="evidence-summary">
        <div><span className="evidence-summary__label">Facility</span><strong>{facilityAssociationLabel(hotspot)}</strong></div>
        <div><span className="evidence-summary__label">Baseline</span><strong>{hotspot.baseline_status.replace(/_/g, ' ')}</strong></div>
        <div><span className="evidence-summary__label">Classification</span><strong>{(CATEGORY_LABEL[hotspot.category] || hotspot.category)}</strong></div>
        <div><span className="evidence-summary__label">Risk</span><strong>{hotspot.risk_level}</strong></div>
        <div><span className="evidence-summary__label">Source</span><strong>{hotspot.source === 'nasa_firms' ? 'NASA FIRMS' : 'Demo'}</strong></div>
      </div>

      <div className="detail__badges">
        <span className="section-divider section-divider--kavach">KAVACH ASSESSMENT</span>
        <span className={`badge badge--${hotspot.category}`}>{CATEGORY_LABEL[hotspot.category] || hotspot.category}</span>
        <span className={`badge badge--risk-${RISK_TONE[hotspot.risk_level] || 'low'}`}>
          Risk: {hotspot.risk_level} ({hotspot.risk_score})
        </span>
        <span className="badge badge--source">
          {hotspot.classification_method === 'ml_model' ? 'ML model' : 'Rule engine'}
          {' · score '}{hotspot.classification_confidence}
        </span>
        <SuddenRiseIndicator hotspot={hotspot} thermalHistory={thermalHistory} />
      </div>

      <p className="detail__reason">{hotspot.reason}</p>

      {reasonCodes.length > 0 && (
        <div className="detail__codes">
          {reasonCodes.map((c) => <span key={c} className="code-chip">{c}</span>)}
        </div>
      )}

      {/* Investigation / location map — the selected event's location context.
          Detail map (no API key). Centres on the facility/event,
          always shows the selected thermal observation and the facility marker,
          plus the 5 km facility association context radius. Compact —
          approximately 380-440px high. */}
      <div className="investigation-two-col">
        <div className="investigation-map-pane">
          <DeepInvestigationMap hotspot={hotspot} hotspots={hotspots} />
        </div>
      </div>

      {/* The full investigation narrative (WHERE / WHAT / WHY / HOW SERIOUS /
          LIKELY CAUSE / baseline + histogram / map / action / evidence /
          verification) belongs ONLY to the Deep Analysis workspace. In the
          compact Command Center detail view we stop here after the concise
          event summary above. */}
      {deep && (
        <>
          {/* 1. WHERE — geographic context. */}
          <h4>Where</h4>
      <div className="where-block">
        <div className="where-row"><span>Coordinates</span><strong>{hotspot.lat.toFixed(4)}, {hotspot.lon.toFixed(4)}</strong></div>
        <div className="where-row"><span>Facility / area</span><strong>{hotspot.facility ? hotspot.facility.name : 'No mapped facility association'}</strong></div>
        <div className="where-row"><span>Facility distance</span><strong>{hotspot.distance_to_facility_km != null ? hotspot.distance_to_facility_km.toFixed(2) + ' km' : '—'}</strong></div>
        <div className="where-row"><span>Geographic context</span><strong>{hotspot.state || '—'}</strong></div>
        <div className="where-row"><span>Map</span><strong>Deep Investigation map below — Detailed map, 5 km context radius</strong></div>
        <div className="where-row"><span>Nearby mapped features</span><strong>
          {loadingGeo ? 'Looking up…'
            : geoContext && geoContext.features.length > 0
              ? `${geoContext.feature_count} found (OpenStreetMap / Overpass)`
              : 'No mapped geographic feature identified near this observation.'}
        </strong></div>
      </div>

      {/* Nearby mapped features — feature name + distance + source.
          A "nearby feature" is NEVER presented as a confirmed source of fire. */}
      {geoContext && geoContext.features.length > 0 && (
        <div className="nearby-features">
          <div className="nearby-features__eyebrow">
            Nearby mapped features — NOT confirmed source of fire
          </div>
          {geoContext.features.slice(0, 6).map((f) => (
            <div key={f.name + f.kind} className="nearby-feature">
              <span className="nearby-feature__name">{f.name}</span>
              <span className="nearby-feature__kind">{f.kind.replace(/_/g, ' ')}</span>
              <span className="nearby-feature__dist">{f.distance_m < 1000 ? `${f.distance_m.toFixed(0)} m` : `${(f.distance_m / 1000).toFixed(2)} km`}</span>
              <span className="nearby-feature__src">{f.source}</span>
            </div>
          ))}
        </div>
      )}
      {!loadingGeo && geoContext && geoContext.features.length === 0 && (
        <p className="nearby-features__none">
          No mapped geographic feature identified near this observation.
        </p>
      )}

      {/* 2. WHAT — the raw thermal observation. (Also shown in the
          RAW NASA THERMAL SIGNAL block above; repeated here for the
          investigation narrative.) */}
      <h4>What</h4>
      <div className="what-block">
        <div className="what-row"><span>Thermal observation</span><strong>NASA FIRMS satellite-detected thermal signal</strong></div>
        <div className="what-row"><span>Brightness</span><strong>{hotspot.brightness != null ? hotspot.brightness.toFixed(2) : '—'} K</strong></div>
        <div className="what-row"><span>FRP</span><strong>{hotspot.frp != null ? hotspot.frp.toFixed(2) : '—'} MW</strong></div>
        <div className="what-row"><span>Acquisition date/time</span><strong>{formatAcqDate(hotspot)}</strong></div>
        <div className="what-row"><span>Satellite</span><strong>{hotspot.satellite || '—'}</strong></div>
        <div className="what-row"><span>Classification</span><strong>{(CATEGORY_LABEL[hotspot.category] || hotspot.category)}</strong></div>
      </div>

      {/* 3. WHY — why this event is flagged. */}
      <h4>Why</h4>
      <div className="why-block">
        <div className="why-row"><span>Baseline status</span><strong>{hotspot.baseline_status.replace(/_/g, ' ')}</strong></div>
        <div className="why-row"><span>Observation / history sufficiency</span><strong>
          {loadingHistory ? 'Loading…'
            : thermalHistory ? (thermalHistory.insufficient_history ? 'INSUFFICIENT HISTORY' : 'Sufficient')
            : '—'}
        </strong></div>
        <div className="why-row"><span>Baseline median</span><strong>
          {thermalHistory && !insufficient && thermalHistory.median != null ? thermalHistory.median.toFixed(1) + ' K' : '—'}
        </strong></div>
        <div className="why-row"><span>Baseline P95</span><strong>
          {thermalHistory && !insufficient && thermalHistory.p95 != null ? thermalHistory.p95.toFixed(1) + ' K' : '—'}
        </strong></div>
        <div className="why-row"><span>Z-score</span><strong>{zDisplay}</strong></div>
        <div className="why-row"><span>Deviation %</span><strong>{devDisplay}{devDisplay !== '—' ? '%' : ''}</strong></div>
        <div className="why-row"><span>Persistence</span><strong>{hotspot.persistence_score != null ? hotspot.persistence_score.toFixed(2) : '—'}</strong></div>
        <div className="why-row"><span>Recurrence</span><strong>{thermalHistory ? `${thermalHistory.observation_count} observation(s)` : '—'}</strong></div>
        <div className="why-row"><span>Supporting evidence</span><strong>{supportingCodes.length ? supportingCodes.join(', ') : 'None'}</strong></div>
        <div className="why-row"><span>Contradicting evidence</span><strong>{contradictingCodes.length ? contradictingCodes.join(', ') : 'None'}</strong></div>
      </div>

      {/* Insufficient-history explanation — never show fake 0 z-score/deviation. */}
      {insufficient && (
        <p className="why-insufficient">
          There are not enough historical observations to reliably calculate
          baseline deviation or recurrence. The current brightness/FRP are
          real stored values; z-score and deviation are shown as unavailable.
        </p>
      )}

      {/* Compact thermal-intelligence card — part of WHY. Uses ONLY the
          existing thermal-history API; no second baseline calculation. */}
      <ThermalIntelligenceCard hotspot={hotspot} />

      {/* 4. HOW SERIOUS — risk level and the stored calculation behind it.
          No new risk weights are invented here; this restates the backend
          risk_engine.assess_risk formula. */}
      <h4>How serious</h4>
      <div className="how-serious">
        <div className="how-serious__level">
          <span className={`badge badge--risk-${RISK_TONE[hotspot.risk_level] || 'low'}`}>
            RISK: {hotspot.risk_level}
          </span>
          <span className="how-serious__score">Score {hotspot.risk_score} / 100</span>
        </div>
        <p className="how-serious__why">
          Why this risk? Stored calculation (risk_engine):
        </p>
        <ul className="how-serious__factors">
          <li>Anomaly contribution: anomaly score drives the base.</li>
          <li>Facility criticality: {facilityCrit} (weight {critWeight}).</li>
          <li>Data quality: {dataQuality} (factor {qualFactor}).</li>
          <li>Classification / model: {hotspot.classification_method} · confidence {hotspot.classification_confidence} (factor {0.5 + 0.5 * confFactor}).</li>
        </ul>
        <p className="how-serious__note">
          This is an operational prioritization score, not a casualty predictor.
        </p>
      </div>

      {/* 5. LIKELY CAUSE — evidence-based interpretation, NOT confirmed
          ground truth. */}
      <h4>Likely cause</h4>
      <p className="likely-cause">
        {likelyCause}
      </p>
      <p className="detail__disclaimer detail__disclaimer--cause">
        This is an evidence-based interpretation, not confirmed ground truth.
      </p>

      <h4>Baseline comparison</h4>
      <div className="baseline-row">
        <div><strong>{hotspot.baseline_status}</strong><span>status</span></div>
        <div><strong>{zDisplay}</strong><span>z-score</span></div>
        <div><strong>{devDisplay}{devDisplay !== '—' ? '%' : ''}</strong><span>deviation</span></div>
        <div><strong>{hotspot.distance_to_facility_km ?? '—'} km</strong><span>to facility</span></div>
      </div>

      {/* INSUFFICIENT_HISTORY context — real observed values only.
          z-score/deviation are deliberately shown as unavailable because the
          backend never calculated them; the raw thermal readings below are
          the actual stored observations, never fabricated. */}
      {insufficient && (
        <div className="baseline-insufficient">
          <span className="baseline-insufficient__eyebrow">
            No baseline available — recurrence and deviation cannot be computed.
          </span>
          {thermalHistory && (
            <span className="baseline-insufficient__stat">
              {thermalHistory.observation_count} observation(s) in the 90-day window
            </span>
          )}
          <span className="baseline-insufficient__stat">
            Brightness {hotspot.brightness != null ? hotspot.brightness.toFixed(1) : '—'} K
          </span>
          <span className="baseline-insufficient__stat">
            FRP {hotspot.frp != null ? hotspot.frp.toFixed(1) : '—'} MW
          </span>
          <span className="baseline-insufficient__stat">
            Confidence {hotspot.classification_confidence != null ? hotspot.classification_confidence.toFixed(2) : '—'}
          </span>
        </div>
      )}

      {/* THERMAL HISTORY / BAR CHART — real NASA FIRMS rows only.
          Shown BEFORE the baseline block so the chart drives the baseline. */}
      {hotspot.source === 'nasa_firms' && hotspot.facility && (
        thermalHistory ? (
          thermalHistory.insufficient_history ? (
            <p className="empty">
              Insufficient NASA FIRMS history for this facility — only{' '}
              {thermalHistory.observation_count} observation(s) in the 90-day window.
              Baseline statistics are not shown to avoid misleading conclusions.
            </p>
          ) : (
            <ThermalHistoryChart
              observations={thermalHistory.observations || []}
              baseline={{
                mean: thermalHistory.mean,
                p95: thermalHistory.p95,
              }}
              selectedHotspotId={hotspot.id}
            />
          )
        ) : loadingHistory ? (
          <p className="empty">Loading NASA FIRMS thermal history…</p>
        ) : (
          <p className="empty">Could not load NASA FIRMS thermal history for this facility.</p>
        )
      )}

      {/* 90-DAY NASA FIRMS THERMAL BASELINE + HISTOGRAM
          Shown ONLY for real NASA FIRMS observations that are facility-associated
          and have sufficient history. Never fabricated. */}
      {hotspot.source === 'nasa_firms' && hotspot.facility && (
        <div className="thermal-baseline-block">
          <div className="thermal-baseline-block__head">
            <span className="thermal-baseline-block__eyebrow">90-DAY NASA FIRMS THERMAL BASELINE</span>
            <span className="thermal-baseline-block__source">Source: NASA FIRMS</span>
          </div>

          {loadingHistory ? (
            <p className="thermal-baseline-block__note">Loading 90-day NASA thermal history…</p>
          ) : thermalHistory ? (
            thermalHistory.insufficient_history ? (
              <p className="thermal-baseline-block__note">
                Insufficient NASA history for 90-day baseline —
                only {thermalHistory.observation_count} NASA observation(s) in window
                (minimum {8} required).
              </p>
            ) : (
              <>
                <div className="thermal-baseline-stats">
                  <div className="thermal-baseline-stat">
                    <span className="thermal-baseline-stat__label">Observations</span>
                    <span className="thermal-baseline-stat__value">{thermalHistory.observation_count}</span>
                  </div>
                  <div className="thermal-baseline-stat">
                    <span className="thermal-baseline-stat__label">Window</span>
                    <span className="thermal-baseline-stat__value">{thermalHistory.window_days}d</span>
                  </div>
                  <div className="thermal-baseline-stat">
                    <span className="thermal-baseline-stat__label">Mean</span>
                    <span className="thermal-baseline-stat__value">{thermalHistory.mean != null ? thermalHistory.mean.toFixed(1) : '—'}K</span>
                  </div>
                  <div className="thermal-baseline-stat">
                    <span className="thermal-baseline-stat__label">Median</span>
                    <span className="thermal-baseline-stat__value">{thermalHistory.median != null ? thermalHistory.median.toFixed(1) : '—'}K</span>
                  </div>
                  <div className="thermal-baseline-stat">
                    <span className="thermal-baseline-stat__label">P95</span>
                    <span className="thermal-baseline-stat__value">{thermalHistory.p95 != null ? thermalHistory.p95.toFixed(1) : '—'}K</span>
                  </div>
                  <div className="thermal-baseline-stat">
                    <span className="thermal-baseline-stat__label">Current</span>
                    <span className="thermal-baseline-stat__value thermal-baseline-stat__value--current">
                      {thermalHistory.current_brightness != null ? thermalHistory.current_brightness.toFixed(1) : '—'}K
                    </span>
                  </div>
                </div>

                <p className="thermal-baseline-block__note thermal-baseline-block__dates">
                  {thermalHistory.date_start} → {thermalHistory.date_end}
                </p>
                <p className="thermal-baseline-block__note">
                  Window anchored to latest observation, not today
                  {syncStatus && syncStatus.last_success
                    ? ` · Last FIRMS sync: ${new Date(syncStatus.last_success).toLocaleString()}`
                    : ' · No FIRMS sync recorded'}
                </p>

                <div className="thermal-baseline-histogram">
                  {thermalHistory.histogram.map((bin) => {
                    const maxCount = Math.max(...thermalHistory.histogram.map((b) => b.count), 1)
                    const pct = (bin.count / maxCount) * 100
                    return (
                      <div key={bin.bin_start} className="histogram-bar" title={`${bin.bin_start}-${bin.bin_end}K: ${bin.count}`}>
                        <span className="histogram-bar__label">{bin.bin_start}-{bin.bin_end}K</span>
                        <div className="histogram-bar__track">
                          <div className="histogram-bar__fill" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="histogram-bar__count">{bin.count}</span>
                      </div>
                    )
                  })}
                </div>

                <p className="thermal-baseline-block__note">
                  NASA FIRMS only · {thermalHistory.observation_count} real observations ·
                  Std {thermalHistory.std != null ? thermalHistory.std.toFixed(1) : '—'}K
                </p>
              </>
            )
          ) : (
            <p className="thermal-baseline-block__note">
              Could not load NASA thermal history for this facility.
            </p>
          )}
        </div>
      )}

      <p className="detail__disclaimer">
        Coordinate reflects the satellite-detected observation location — not a confirmed
        fire boundary or verified facility ownership.
      </p>

      {/* 6. WHAT TO DO — risk-tier actions. No automatic emergency dispatch. */}
      <h4>What to do</h4>
      <div className="what-to-do what-to-do--${RISK_TONE[hotspot.risk_level] || 'low'}">
        {hotspot.risk_level === 'LOW' && (
          <p>Continue monitoring and retain in thermal history.</p>
        )}
        {hotspot.risk_level === 'WATCH' && (
          <ul>
            <li>Review recurrence, baseline deviation, satellite context.</li>
            <li>Check geographic context and supporting evidence.</li>
          </ul>
        )}
        {hotspot.risk_level === 'HIGH' && (
          <ul>
            <li>Analyst verification required.</li>
            <li>Review satellite imagery + baseline + evidence.</li>
            <li>Escalate according to operational SOP if confirmed.</li>
          </ul>
        )}
        {hotspot.risk_level === 'CRITICAL' && (
          <ul>
            <li>Immediate analyst review.</li>
            <li>Confirm satellite / geographic evidence.</li>
            <li>Cross-check facility context and thermal history.</li>
            <li>Escalate according to operational SOP.</li>
          </ul>
        )}
        <p className="what-to-do__note">
          This is an evidence-based interpretation, not confirmed ground truth.
          No automatic emergency dispatch is triggered by this score.
        </p>
      </div>

      <h4>Thermal history</h4>
      <Timeline hotspotId={hotspot.id} />

      <h4>Assessment</h4>
      {!assessment && (
        <button className="btn-secondary" onClick={handleAssess} disabled={assessing}>
          {assessing ? 'Generating…' : 'Generate assessment'}
        </button>
      )}
      {assessment && (
        <pre className="assessment-box">
{`Event: ${assessment.event_id}
Facility: ${assessment.facility}
Assessment: ${assessment.assessment}
Risk: ${assessment.risk_level} (${assessment.risk_score})
Data quality: ${assessment.data_quality}
Data source: ${assessment.data_source}
Recommended action: ${assessment.recommended_analyst_action}`}
        </pre>
      )}

      {/* 7. EVIDENCE NEEDED — gaps the analyst should look for. No fabrication. */}
      <h4>Evidence needed</h4>
      <ul className="evidence-needed">
        <li>Additional FIRMS observations to establish recurrence.</li>
        <li>Higher-resolution imagery where available.</li>
        <li>Operator / ground confirmation.</li>
        <li>Weather / wind context where available.</li>
        <li>Additional geographic / context evidence.</li>
      </ul>

        {/* 8. ANALYST VERIFICATION */}
        <h4>Analyst verification</h4>
        <div className="verify-buttons">
          {VERIFY_OPTIONS.map((opt) => (
            <button key={opt.value} className="btn-chip" onClick={() => handleVerify(opt.value)}>
              {opt.label}
            </button>
          ))}
        </div>
        {verifyStatus && <p className="verify-status">{verifyStatus}</p>}
        </>
      )}
    </div>
  )
}
