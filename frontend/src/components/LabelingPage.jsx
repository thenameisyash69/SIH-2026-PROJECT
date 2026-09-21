import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchHotspotById,
  fetchLabelingCandidates,
  fetchLabelingStats,
  fetchTrainingEligibility,
  verifyHotspot,
  fetchVerification,
  fetchIndustrialFireCandidates,
  fetchIndustrialFireReviewProgress,
  fetchDemoStatus,
  createDemoScenario,
  resetDemoData,
} from '../api'
import { getThermalSeverity } from '../utils/thermalSeverity'
import DeepAnalysis from './DeepAnalysis'

const THERMAL_FILTERS = ['ALL', 'WEAK', 'MODERATE', 'HIGH', 'EXTREME']
const VERIFY_FILTERS = ['ALL', 'UNVERIFIED', 'VERIFIED']
const FACILITY_FILTERS = ['ALL', 'ASSOCIATED', 'NOT ASSOCIATED']
const BASELINE_FILTERS = ['ALL', 'NORMAL', 'ELEVATED', 'ABNORMAL', 'INSUFFICIENT_HISTORY']
const ANOMALY_FILTERS = ['ALL', 'ANOMALY', 'NO ANOMALY', 'UNKNOWN']
const RISK_FILTERS = ['ALL', 'LOW', 'WATCH', 'HIGH', 'CRITICAL']
const CLASSIFICATION_FILTERS = ['ALL', 'UNKNOWN', 'NORMAL_INDUSTRIAL_HEAT', 'INDUSTRIAL_FIRE', 'WILDFIRE', 'AGRICULTURAL']
const HISTORY_FILTERS = ['ALL', 'SUFFICIENT', 'INSUFFICIENT']

const DECISIONS = [
  { value: 'confirmed_industrial_fire', label: 'Confirm industrial fire' },
  { value: 'confirmed_normal_industrial_heat', label: 'Confirm normal industrial heat' },
  { value: 'confirmed_wildfire', label: 'Mark wildfire' },
  { value: 'confirmed_agricultural', label: 'Mark agricultural' },
  { value: 'false_positive', label: 'Mark false positive' },
  { value: 'unknown', label: 'Mark unknown' },
]

const CATEGORY_LABEL = {
  industrial_alert: 'Industrial — Alert',
  industrial_new: 'Industrial — New / Unverified',
  industrial_normal: 'Industrial — Normal',
  confirmed_industrial: 'Confirmed industrial',
  confirmed_normal_industrial_heat: 'Confirmed normal industrial heat',
  wildfire: 'Wildfire',
  agricultural_burning: 'Agricultural burning',
  unknown: 'Unknown',
}

const RISK_TONE = {
  LOW: 'low',
  WATCH: 'watch',
  HIGH: 'high',
  CRITICAL: 'critical',
}

function fmtDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

function fmtNum(value, digits = 2) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : String(value)
}

function facilityText(hotspot) {
  if (!hotspot?.facility) return 'No mapped facility'
  return hotspot.facility.name || hotspot.facility.id || 'Mapped facility'
}

function thermalRank(severity) {
  return { EXTREME: 5, HIGH: 4, MODERATE: 3, WEAK: 2, UNKNOWN: 1 }[severity] || 0
}

function sortCandidates(list) {
  return [...list].sort((a, b) => {
    const aSeverity = thermalRank(getThermalSeverity(a.brightness, a.frp))
    const bSeverity = thermalRank(getThermalSeverity(b.brightness, b.frp))
    if (bSeverity !== aSeverity) return bSeverity - aSeverity

    const aVerified = a.verified ? 1 : 0
    const bVerified = b.verified ? 1 : 0
    if (aVerified !== bVerified) return aVerified - bVerified

    return Number(b.frp || 0) - Number(a.frp || 0)
  })
}

function Stat({ label, value, tone }) {
  return (
    <div className={`metrics__item ${tone ? `metrics__item--${tone}` : ''}`}>
      <strong>{value ?? '—'}</strong>
      <span>{label}</span>
    </div>
  )
}

function InvestigationCard({ hotspot, note, busy, isSearchResult, onVerify, onDeepAnalysis }) {
  const severity = getThermalSeverity(hotspot.brightness, hotspot.frp)
  const riskTone = RISK_TONE[hotspot.risk_level] || 'low'

  return (
    <article className="labeling-card">
      <div className="labeling-card__head">
        <div className="labeling-card__flag">
          {isSearchResult ? 'SEARCH RESULT' : 'CANDIDATE'}
        </div>
        <div className="labeling-card__sev">
          <span className={`thermal-signal-badge thermal-sev--${severity.key}`}>
            <span className="thermal-signal-badge__dot" />
            <span className="thermal-signal-badge__label">{severity.label.toUpperCase()} THERMAL SIGNAL</span>
          </span>
        </div>
        <div className="labeling-card__id">Hotspot #{hotspot.id}</div>
        <div className="labeling-card__source-flag">
          {hotspot.source === 'nasa_firms' ? '🛰 REAL — NASA FIRMS' : '◆ DEMO — synthetic'}
        </div>
      </div>

      <h3 className="labeling-card__title">{facilityText(hotspot)}</h3>

      <div className="labeling-card__badges">
        <span className={`badge badge--${hotspot.category || 'unknown'}`}>
          {CATEGORY_LABEL[hotspot.category] || hotspot.category || 'Unknown'}
        </span>
        <span className={`badge badge--risk-${riskTone}`}>
          Risk: {hotspot.risk_level || 'WATCH'} ({fmtNum(hotspot.risk_score)})
        </span>
        <span className="badge badge--source">
          {hotspot.verified ? 'VERIFIED' : 'UNVERIFIED'}
        </span>
      </div>

      <div className="labeling-card__deep">
        <button
          type="button"
          className="btn-chip btn-chip--deep"
          onClick={() => onDeepAnalysis && onDeepAnalysis(hotspot.id)}
        >
          Deep Analysis →
        </button>
      </div>

      <div className="labeling-section">
        <h4 className="labeling-section__title">Thermal signal</h4>
        <div className="labeling-grid">
          <div className="labeling-cell"><strong>{fmtNum(hotspot.brightness, 1)} K</strong><span>brightness</span></div>
          <div className="labeling-cell"><strong>{fmtNum(hotspot.frp)} MW</strong><span>FRP</span></div>
          <div className="labeling-cell"><strong>{fmtNum(hotspot.confidence, 0)}</strong><span>source confidence</span></div>
          <div className="labeling-cell"><strong>{fmtNum(hotspot.distance_to_facility_km)} km</strong><span>facility distance</span></div>
        </div>
      </div>

      <div className="labeling-section">
        <h4 className="labeling-section__title">Facility baseline</h4>
        <div className="labeling-grid">
          <div className="labeling-cell"><strong>{hotspot.baseline_status || '—'}</strong><span>baseline status</span></div>
          <div className="labeling-cell"><strong>{fmtNum(hotspot.z_score)}</strong><span>z-score</span></div>
          <div className="labeling-cell"><strong>{hotspot.deviation_percentage == null ? '—' : `${fmtNum(hotspot.deviation_percentage)}%`}</strong><span>deviation</span></div>
          <div className="labeling-cell"><strong>{fmtNum(hotspot.persistence_score)}</strong><span>persistence</span></div>
        </div>
      </div>

      <div className="labeling-section">
        <h4 className="labeling-section__title">Observation</h4>
        <div className="labeling-grid">
          <div className="labeling-cell"><strong>{fmtDate(hotspot.acq_date)}</strong><span>acquired</span></div>
          <div className="labeling-cell"><strong>{hotspot.satellite || '—'}</strong><span>satellite</span></div>
          <div className="labeling-cell"><strong>{CATEGORY_LABEL[hotspot.category] || hotspot.category || 'Unknown'}</strong><span>classification</span></div>
          <div className="labeling-cell"><strong>{hotspot.classification_method || '—'}</strong><span>method</span></div>
        </div>
        <p className="labeling-cell__meta">
          Model score: <strong>{fmtNum(hotspot.classification_confidence)}</strong>
        </p>
      </div>

      <div className="labeling-section">
        <h4 className="labeling-section__title">Anomaly</h4>
        <p className="labeling-cell__meta">
          Anomaly: <strong>{hotspot.is_anomaly ? 'YES' : 'NO'}</strong>
          {' · '}
          Reason: <strong>{hotspot.reason || '—'}</strong>
        </p>
      </div>

      <div className="labeling-section">
        <h4 className="labeling-section__title">Evidence</h4>
        <EvidenceList hotspot={hotspot} />
      </div>

      <div className="labeling-section">
        <h4 className="labeling-section__title">Analyst decision</h4>
        <label htmlFor={`note-${hotspot.id}`} className="labeling-note-label">
          Analyst note
        </label>
        <textarea
          id={`note-${hotspot.id}`}
          value={note}
          onChange={(event) => onVerify && onVerify.noteChange(event.target.value)}
          placeholder="Why are you assigning this label?"
          rows={3}
          className="labeling-note"
        />

        <div className="labeling-decisions">
          {DECISIONS.map((decision) => (
            <button
              key={decision.value}
              className="btn-chip"
              disabled={busy}
              onClick={() => onVerify && onVerify.click(decision.value)}
            >
              {busy ? 'Saving…' : decision.label}
            </button>
          ))}
        </div>

        {hotspot.verified && (
          <p className="verify-status">
            Existing verification: {hotspot.verification_decision || 'verified'}
          </p>
        )}
      </div>
    </article>
  )
}

function reviewEvidence(hotspot) {
  const supporting = []
  const questioning = []

  if (hotspot?.is_anomaly) supporting.push('flagged as anomaly')
  if (hotspot?.baseline_status === 'ABNORMAL') supporting.push('baseline ABNORMAL')
  if (hotspot?.baseline_status === 'ELEVATED') supporting.push('baseline ELEVATED')

  const z = Number(hotspot?.z_score)
  if (Number.isFinite(z) && z >= 1.5) supporting.push(`z-score ${z.toFixed(2)}`)
  const dev = Number(hotspot?.deviation_percentage)
  if (Number.isFinite(dev) && dev >= 5) supporting.push(`deviation ${dev.toFixed(1)}%`)
  if (hotspot?.risk_level === 'HIGH' || hotspot?.risk_level === 'CRITICAL') supporting.push(`risk ${hotspot.risk_level}`)
  if (hotspot?.facility) supporting.push('facility-associated')
  if (Number(hotspot?.confidence || 0) >= 80) supporting.push('high source confidence')

  if (hotspot?.baseline_status === 'NORMAL' && !hotspot?.is_anomaly) questioning.push('baseline NORMAL, not flagged as anomaly')
  if (hotspot?.baseline_status === 'INSUFFICIENT_HISTORY') questioning.push('insufficient baseline history')
  if (Number(hotspot?.confidence || 0) < 50) questioning.push('low source confidence')
  if (Number(hotspot?.persistence_score || 0) >= 0.8 && hotspot?.baseline_status === 'NORMAL') questioning.push('persistent heat but baseline NORMAL')
  if (hotspot?.data_quality === 'poor') questioning.push('poor data quality')

  if (supporting.length >= 3 && questioning.length === 0) {
    return {
      status: 'WELL_SUPPORTED',
      why: `Multiple independent signals agree: ${supporting.join(', ')}.`,
      action: 'KEEP LABEL',
    }
  }
  if (questioning.length >= 2 || (supporting.length === 0 && questioning.length > 0)) {
    return {
      status: 'INSUFFICIENT_EVIDENCE',
      why: `Weak or conflicting evidence: ${questioning.join(', ')}.`,
      action: 'REVIEW LABEL',
    }
  }
  return {
    status: 'QUESTIONABLE',
    why: `Mixed signals — supporting: ${supporting.join(', ') || 'none'}; questioning: ${questioning.join(', ') || 'none'}.`,
    action: 'REVIEW LABEL',
  }
}

function VerificationReviewCard({ hotspot, note, busy, onVerify }) {
  const review = hotspot ? reviewEvidence(hotspot) : null
  const severity = hotspot ? getThermalSeverity(hotspot.brightness, hotspot.frp) : null
  const riskTone = hotspot ? (RISK_TONE[hotspot.risk_level] || 'low') : 'low'

  if (!hotspot) {
    return <p className="empty">No verified hotspot selected.</p>
  }

  return (
    <article className="labeling-card labeling-card--review">
      <div className="labeling-card__head">
        <div className="labeling-card__flag">VERIFIED — REVIEW</div>
        {severity && (
          <span className={`thermal-signal-badge thermal-sev--${severity.key}`}>
            <span className="thermal-signal-badge__dot" />
            <span className="thermal-signal-badge__label">{severity.label.toUpperCase()} THERMAL SIGNAL</span>
          </span>
        )}
        <div className="labeling-card__id">Hotspot #{hotspot.id}</div>
      </div>

      <h3 className="labeling-card__title">{facilityText(hotspot)}</h3>

      <div className="labeling-card__badges">
        <span className={`badge badge--${hotspot.category || 'unknown'}`}>
          {CATEGORY_LABEL[hotspot.category] || hotspot.category || 'Unknown'}
        </span>
        <span className={`badge badge--risk-${riskTone}`}>
          Risk: {hotspot.risk_level || 'WATCH'} ({fmtNum(hotspot.risk_score)})
        </span>
        <span className="badge badge--source">VERIFIED</span>
      </div>

      <div className="labeling-grid">
        <div className="labeling-cell"><strong>{fmtNum(hotspot.brightness, 1)} K</strong><span>brightness</span></div>
        <div className="labeling-cell"><strong>{fmtNum(hotspot.frp)} MW</strong><span>FRP</span></div>
        <div className="labeling-cell"><strong>{fmtNum(hotspot.confidence, 0)}</strong><span>source confidence</span></div>
        <div className="labeling-cell"><strong>{hotspot.baseline_status || '—'}</strong><span>baseline status</span></div>
      </div>

      <div className="labeling-grid">
        <div className="labeling-cell"><strong>{fmtNum(hotspot.z_score)}</strong><span>z-score</span></div>
        <div className="labeling-cell"><strong>{hotspot.deviation_percentage == null ? '—' : `${fmtNum(hotspot.deviation_percentage)}%`}</strong><span>deviation</span></div>
        <div className="labeling-cell"><strong>{fmtNum(hotspot.persistence_score)}</strong><span>persistence</span></div>
        <div className="labeling-cell"><strong>{hotspot.is_anomaly ? 'YES' : 'NO'}</strong><span>anomaly</span></div>
      </div>

      <div className="labeling-grid">
        <div className="labeling-cell"><strong>{CATEGORY_LABEL[hotspot.category] || hotspot.category || 'Unknown'}</strong><span>classification</span></div>
        <div className="labeling-cell"><strong>{hotspot.classification_method || '—'}</strong><span>method</span></div>
        <div className="labeling-cell"><strong>{hotspot.verification_decision || '—'}</strong><span>analyst decision</span></div>
        <div className="labeling-cell"><strong>{fmtDate(hotspot.verification_created_at || hotspot.created_at)}</strong><span>verified at</span></div>
      </div>

      <p className="labeling-cell__meta">
        Analyst note: <strong>{hotspot.verification_note || '—'}</strong>
      </p>

      <div className="labeling-section">
        <h4 className="labeling-section__title">Evidence review</h4>
        <div className="labeling-card__badges">
          <span className={`badge badge--risk-${review.status === 'WELL_SUPPORTED' ? 'low' : review.status === 'QUESTIONABLE' ? 'watch' : 'high'}`}>
            {review.status.replace(/_/g, ' ')}
          </span>
          <span className="badge badge--source">{review.action.replace(/_/g, ' ')}</span>
        </div>
        <p className="labeling-cell__meta">
          {review.why}
        </p>
        <p className="labeling-cell__meta" style={{ fontStyle: 'italic' }}>
          This is an assistant review based on existing fields only. It does not change the analyst's
          decision, does not retrain any model, and does not overwrite the verification record.
        </p>
      </div>

      <div className="labeling-section">
        <h4 className="labeling-section__title">Analyst decision</h4>
        <label htmlFor={`note-${hotspot.id}`} className="labeling-note-label">
          Analyst note
        </label>
        <textarea
          id={`note-${hotspot.id}`}
          value={note}
          onChange={(event) => onVerify && onVerify.noteChange(event.target.value)}
          placeholder="Optional — update the note for this label."
          rows={3}
          className="labeling-note"
        />

        <div className="labeling-decisions">
          {DECISIONS.map((decision) => (
            <button
              key={decision.value}
              className="btn-chip"
              disabled={busy}
              onClick={() => onVerify && onVerify.click(decision.value)}
            >
              {busy ? 'Saving…' : decision.label}
            </button>
          ))}
        </div>
      </div>
    </article>
  )
}

function EvidenceList({ hotspot }) {
  const reasons = []
  if (Array.isArray(hotspot.candidate_reasons)) reasons.push(...hotspot.candidate_reasons)
  if (hotspot.reason) reasons.push(hotspot.reason)

  const codes = String(hotspot.reason_codes || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)

  if (!reasons.length && !codes.length) {
    return <p className="empty">No explicit evidence reasons returned.</p>
  }

  return (
    <div className="detail__codes">
      {reasons.map((reason, index) => (
        <span className="code-chip" key={`reason-${index}`}>{reason}</span>
      ))}
      {codes.map((code) => (
        <span className="code-chip" key={code}>{code}</span>
      ))}
    </div>
  )
}

export default function LabelingPage() {
  const [stats, setStats] = useState(null)
  const [eligibility, setEligibility] = useState(null)
  const [candidates, setCandidates] = useState([])
  const [totalMatched, setTotalMatched] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [thermalFilter, setThermalFilter] = useState('ALL')

  // Source filter: LIVE (nasa_firms), DEMO (demo), ALL (all sources)
  // Default is LIVE to keep normal analyst workflows unchanged.
  const [sourceFilter, setSourceFilter] = useState('LIVE')

  // Active filters: drive the fetch. Only mutated by applyFilters/clearFilters.
  const [filters, setFilters] = useState({
    verify: 'ALL',
    facility: 'ALL',
    baseline: 'ALL',
    anomaly: 'ALL',
    risk: 'ALL',
    classification: 'ALL',
    history: 'ALL',
  })

  // Pending filters: updated immediately by dropdowns. NEVER triggers a fetch.
  const [pendingFilters, setPendingFilters] = useState({
    verify: 'ALL',
    facility: 'ALL',
    baseline: 'ALL',
    anomaly: 'ALL',
    risk: 'ALL',
    classification: 'ALL',
    history: 'ALL',
  })

  const [note, setNote] = useState('')
  const [savingId, setSavingId] = useState(null)
  const [msg, setMsg] = useState(null)
  const [searchValue, setSearchValue] = useState('')
  const [searched, setSearched] = useState(null)
  const [searchError, setSearchError] = useState(null)
  const [searching, setSearching] = useState(false)
  const [verifiedList, setVerifiedList] = useState([])
  const [openDeepId, setOpenDeepId] = useState(null)
  const [verifiedLoading, setVerifiedLoading] = useState(false)
  const [demoLoading, setDemoLoading] = useState(false)

  // Monotonic sequence counter used to discard stale search results when the
  // user submits a new search before the previous one resolves (A -> B -> C).
  // useRef keeps a single stable object across renders so in-flight promises
  // can reliably detect that a newer request has superseded them.
  const searchSeqRef = useRef(0)

  const createDemo = async (days = 30) => {
    setDemoLoading(true)
    setError(null)
    setMsg(null)
    try {
      await createDemoScenario(days)
      setMsg(`Demo scenario created (${days} days). Switch to DEMO mode to review.`)
      if (sourceFilter === 'DEMO') load()
    } catch (e) {
      setError(e.message || 'Failed to create demo scenario')
    } finally {
      setDemoLoading(false)
    }
  }

  const resetDemo = async () => {
    if (!window.confirm('Delete ALL demo data? This cannot be undone.')) return
    setDemoLoading(true)
    setError(null)
    setMsg(null)
    try {
      await resetDemoData()
      setMsg('Demo data reset. Switching to LIVE mode.')
      setSourceFilter('LIVE')
      load()
    } catch (e) {
      setError(e.message || 'Failed to reset demo data')
    } finally {
      setDemoLoading(false)
    }
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statsResult, eligibilityResult, candidateResult] = await Promise.all([
        fetchLabelingStats(sourceFilter === 'LIVE' ? 'nasa_firms' : sourceFilter === 'DEMO' ? 'demo' : 'all'),
        fetchTrainingEligibility(),
        fetchLabelingCandidates({
          source: sourceFilter === 'LIVE' ? 'nasa_firms' : sourceFilter === 'DEMO' ? 'demo' : 'all',
          limit: 50,
          diversity: true,
          verified:
            filters.verify === 'VERIFIED'
              ? true
              : filters.verify === 'UNVERIFIED'
                ? false
                : undefined,
          facility_associated:
            filters.facility === 'ASSOCIATED'
              ? true
              : filters.facility === 'NOT ASSOCIATED'
                ? false
                : undefined,
          facility_id:
            filters.facility === 'ASSOCIATED'
              ? true
              : filters.facility === 'NOT ASSOCIATED'
                ? false
                : undefined,
          baseline_status:
            filters.baseline === 'ALL' ? undefined : filters.baseline,
          anomaly:
            filters.anomaly === 'ANOMALY'
              ? true
              : filters.anomaly === 'NO ANOMALY'
                ? false
                : undefined,
          risk_level:
            filters.risk === 'ALL' ? undefined : filters.risk,
          classification:
            filters.classification === 'ALL'
              ? undefined
              : filters.classification === 'UNKNOWN'
                ? 'unknown'
                : filters.classification === 'NORMAL_INDUSTRIAL_HEAT'
                  ? 'industrial_normal'
                  : filters.classification === 'INDUSTRIAL_FIRE'
                    ? 'industrial_alert'
                    : filters.classification === 'WILDFIRE'
                      ? 'wildfire'
                      : filters.classification === 'AGRICULTURAL'
                        ? 'agricultural_burning'
                        : undefined,
          history_status:
            filters.history === 'ALL' ? undefined : filters.history,
        }),
      ])

      setStats(statsResult || null)
      setEligibility(eligibilityResult || null)
      setCandidates(candidateResult?.candidates || [])
      setTotalMatched(candidateResult?.total_matched ?? candidateResult?.candidates?.length ?? 0)
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Could not load the analyst queue.')
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => {
    load()
  }, [load])

  function applyFilters() {
    setFilters({ ...pendingFilters })
  }

  function clearFilters() {
    const cleared = {
      verify: 'ALL',
      facility: 'ALL',
      baseline: 'ALL',
      anomaly: 'ALL',
      risk: 'ALL',
      classification: 'ALL',
      history: 'ALL',
    }
    setPendingFilters({ ...cleared })
    setFilters({ ...cleared })
  }

  function clearSearch() {
    setSearched(null)
    setSearchError(null)
    setSearchValue('')
  }

  const filtered = useMemo(() => {
    const result = candidates.filter((hotspot) => {
      // Thermal is the only client-side filter (backend has no thermal param).
      const severity = getThermalSeverity(hotspot.brightness, hotspot.frp)
      if (thermalFilter !== 'ALL' && severity.key.toUpperCase() !== thermalFilter) return false
      return true
    })

    return sortCandidates(result)
  }, [candidates, thermalFilter])

  async function handleVerify(hotspotId, decision) {
    setSavingId(hotspotId)
    setMsg(null)

    try {
      await verifyHotspot(hotspotId, decision, note)
      setMsg(`Saved verification for hotspot ${hotspotId}: ${decision.replace(/_/g, ' ')}`)
      setNote('')
      await load()
      await loadVerified()
      if (searched && searched.id === hotspotId) {
        try {
          const v = await fetchVerification(hotspotId)
          setSearched({
            ...searched,
            verified: true,
            verification_decision: v?.decision || decision,
            verification_note: v?.note ?? note,
            verification_created_at: v?.created_at || null,
          })
        } catch {
          setSearched({
            ...searched,
            verified: true,
            verification_decision: decision,
            verification_note: note,
            verification_created_at: null,
          })
        }
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Verification could not be saved.'
      setMsg(`Verification failed: ${detail}`)
    } finally {
      setSavingId(null)
    }
  }

  async function handleSearch(event, explicitId) {
    if (event && event.preventDefault) event.preventDefault()
    const raw = String(explicitId || searchValue || '').trim()
    if (!raw) {
      setSearched(null)
      setSearchError(null)
      return
    }

    const numeric = raw.replace(/[^0-9]/g, '')
    if (!numeric) {
      setSearched(null)
      setSearchError('Enter a numeric hotspot ID, e.g. 18275.')
      return
    }

    const requestSeq = ++searchSeqRef.current
    setSearching(true)
    setSearchError(null)
    try {
      const hotspot = await fetchHotspotById(numeric)
      if (requestSeq !== searchSeqRef.current) return // stale request — a newer search is in flight
      if (!hotspot || !hotspot.id) {
        setSearched(null)
        setSearchError(`Hotspot #${numeric} not found.`)
        return
      }
      let enriched = hotspot
      try {
        const v = await fetchVerification(numeric)
        enriched = {
          ...hotspot,
          verified: true,
          verification_decision: v?.decision || hotspot.verification_decision || null,
          verification_note: v?.note ?? hotspot.verification_note ?? null,
          verification_created_at: v?.created_at || null,
        }
      } catch {
        enriched = {
          ...hotspot,
          verified: false,
          verification_decision: null,
          verification_note: null,
          verification_created_at: null,
        }
      }
      setSearched(enriched)
      setSearchError(null)
    } catch (err) {
      if (requestSeq !== searchSeqRef.current) return // stale request — discard
      setSearched(null)
      // Distinguish a genuine 404 / not-found from a backend outage or
      // network failure. A backend outage must NOT be presented as "not
      // found" — the analyst must be able to retry.
      const isHttpError = err?.response?.status
      const isNetwork = !isHttpError && (err?.code === 'ECONNABORTED' || err?.code === 'ERR_NETWORK' || err?.code === 'ERR_CANCELED')
      const detail = err?.response?.data?.detail || err?.message || 'Could not load hotspot.'
      if (isHttpError === 404) {
        setSearchError(`Hotspot #${numeric} not found.`)
      } else if (isNetwork) {
        setSearchError(`Network error while loading hotspot #${numeric}. Check your connection and try again.`)
      } else {
        setSearchError(`Could not load hotspot #${numeric}: ${detail}`)
      }
    } finally {
      setSearching(false)
    }
  }

  const loadVerified = useCallback(async () => {
    setVerifiedLoading(true)
    try {
      const result = await fetchLabelingCandidates({
        source: sourceFilter === 'LIVE' ? 'nasa_firms' : sourceFilter === 'DEMO' ? 'demo' : 'all',
        verified: true,
        limit: 100,
        diversity: false,
      })
      const verified = result?.candidates || []
      const enriched = await Promise.all(
        verified.map(async (h) => {
          try {
            const v = await fetchVerification(h.id)
            return {
              ...h,
              verification_created_at: v?.created_at || h.verification_created_at || null,
              verification_note: v?.note ?? h.verification_note ?? null,
            }
          } catch {
            return {
              ...h,
              verification_created_at: h.verification_created_at || null,
              verification_note: h.verification_note ?? null,
            }
          }
        })
      )
      setVerifiedList(enriched)
    } catch {
      setVerifiedList([])
    } finally {
      setVerifiedLoading(false)
    }
  }, [])

  useEffect(() => {
    loadVerified()
  }, [loadVerified])

  if (loading) {
    return (
      <main className="layout layout--single">
        <div className="detail">
          <h2>NASA Analyst Labeling Queue</h2>
          <p className="empty">Loading real NASA FIRMS candidates…</p>
        </div>
      </main>
    )
  }

  return (
    <main className="layout layout--single labeling-page">
      <div className="labeling-page__sidebar">
        <form className="labeling-search" onSubmit={handleSearch}>
          <div className="labeling-search__head">
            <span className="labeling-search__title">FIND HOTSPOT</span>
          </div>
          <input
            className="labeling-search__input"
            type="text"
            value={searchValue}
            onChange={(event) => {
              setSearchValue(event.target.value)
              if (searchError) setSearchError(null)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                handleSearch()
              }
            }}
            placeholder="Hotspot ID, e.g. 18275"
            disabled={searching}
          />
          <button
            type="submit"
            className="btn-secondary labeling-search__btn"
            disabled={searching}
          >
            {searching ? 'Searching…' : 'SEARCH'}
          </button>
          {searchError && <p className="labeling-search__error">{searchError}</p>}
        </form>

        <div className="labeling-filters">
          <h4>Data Source</h4>
          <div className="verify-buttons">
            {['LIVE', 'DEMO', 'ALL'].map((filter) => (
              <button
                key={filter}
                className={`btn-chip ${sourceFilter === filter ? 'btn-chip--active' : ''}`}
                onClick={() => setSourceFilter(filter)}
              >
                {filter === 'LIVE' ? '🛰 Live NASA FIRMS' : filter === 'DEMO' ? '◆ Demo Data' : 'All Sources'}
              </button>
            ))}
          </div>
          <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            <button
              className="btn-chip"
              onClick={() => createDemo(30)}
              disabled={demoLoading}
            >
              {demoLoading ? 'Generating…' : '◆ Generate 30-Day Demo'}
            </button>
            <button
              className="btn-chip"
              onClick={() => createDemo(90)}
              disabled={demoLoading}
            >
              {demoLoading ? 'Generating…' : '◆ Generate 90-Day Demo'}
            </button>
            <button
              className="btn-chip"
              onClick={resetDemo}
              disabled={demoLoading}
            >
              ⨉ Reset Demo Data
            </button>
          </div>

          <h4>Thermal</h4>
          <div className="verify-buttons">
            {THERMAL_FILTERS.map((filter) => (
              <button
                key={filter}
                className={`btn-chip ${thermalFilter === filter ? 'btn-chip--active' : ''}`}
                onClick={() => setThermalFilter(filter)}
              >
                {filter}
              </button>
            ))}
          </div>

          <h4>Advanced Filters</h4>
          <div className="labeling-selects">
            <label className="labeling-select">
              <span>Verification</span>
              <select value={pendingFilters.verify} onChange={(e) => setPendingFilters((p) => ({ ...p, verify: e.target.value }))}>
                {VERIFY_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>

            <label className="labeling-select">
              <span>Facility</span>
              <select value={pendingFilters.facility} onChange={(e) => setPendingFilters((p) => ({ ...p, facility: e.target.value }))}>
                {FACILITY_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>

            <label className="labeling-select">
              <span>Baseline</span>
              <select value={pendingFilters.baseline} onChange={(e) => setPendingFilters((p) => ({ ...p, baseline: e.target.value }))}>
                {BASELINE_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>

            <label className="labeling-select">
              <span>Anomaly</span>
              <select value={pendingFilters.anomaly} onChange={(e) => setPendingFilters((p) => ({ ...p, anomaly: e.target.value }))}>
                {ANOMALY_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>

            <label className="labeling-select">
              <span>Risk</span>
              <select value={pendingFilters.risk} onChange={(e) => setPendingFilters((p) => ({ ...p, risk: e.target.value }))}>
                {RISK_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>

            <label className="labeling-select">
              <span>Classification</span>
              <select value={pendingFilters.classification} onChange={(e) => setPendingFilters((p) => ({ ...p, classification: e.target.value }))}>
                {CLASSIFICATION_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>

            <label className="labeling-select">
              <span>History</span>
              <select value={pendingFilters.history} onChange={(e) => setPendingFilters((p) => ({ ...p, history: e.target.value }))}>
                {HISTORY_FILTERS.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </label>
          </div>

          <div className="labeling-filter-actions">
            <button className="btn-chip btn-chip--primary" onClick={applyFilters}>
              Apply Filters
            </button>
            <button className="btn-chip" onClick={clearFilters}>
              Clear Filters
            </button>
          </div>

          <div className="labeling-active-filters">
            <span className="labeling-active-filters__label">Active:</span>
            {sourceFilter !== 'LIVE' && (
              <span className="badge badge--source">
                source: {sourceFilter}
              </span>
            )}
            {[
              ['verify', filters.verify],
              ['facility', filters.facility],
              ['baseline', filters.baseline],
              ['anomaly', filters.anomaly],
              ['risk', filters.risk],
              ['classification', filters.classification],
              ['history', filters.history],
            ].filter(([, v]) => v !== 'ALL').map(([k, v]) => (
              <span key={k} className="badge badge--source">
                {k}: {v}
              </span>
            ))}
          </div>

          <div className="labeling-verified-panel">
            <h4>Verified labels</h4>
            {verifiedLoading ? (
              <p className="empty">Loading verified labels…</p>
            ) : verifiedList.length === 0 ? (
              <p className="empty">No verified labels yet.</p>
            ) : (
              <div className="labeling-verified-list">
                {verifiedList.map((h) => (
                  <button
                    key={h.id}
                    className="labeling-verified-item"
                    onClick={() => {
                      setSearched(h)
                      setSearchError(null)
                      setSearchValue(String(h.id))
                    }}
                  >
                    <span className="labeling-verified-item__id">#{h.id}</span>
                    <span className="labeling-verified-item__name">{facilityText(h)}</span>
                    <span className="labeling-verified-item__decision">
                      {(h.verification_decision || '').replace(/_/g, ' ')}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <p className="labeling-filters__count">
            Showing <strong>{filtered.length}</strong> of <strong>{totalMatched}</strong> matching observations.
          </p>
        </div>
      </div>

      <div className="labeling-page__main">
        <div className="labeling-page__topbar">
          <div>
            <h2>NASA Analyst Labeling Queue</h2>
             <p className="detail__reason">
               Human verification creates the trusted labels required for future ML training.
               {sourceFilter === 'LIVE' && ' This queue shows real NASA FIRMS observations only — no synthetic demo data.'}
               {sourceFilter === 'DEMO' && ' ◆ DEMO DATA MODE — showing synthetic observations for demonstration only.'}
               {sourceFilter === 'ALL' && ' Showing all sources — live NASA FIRMS and demo data are labeled separately.'}
             </p>
          </div>
          {searched && (
            <button className="btn-chip" onClick={clearSearch}>
              ✕ Clear search result
            </button>
          )}
        </div>

        {error && (
          <div className="sync-message sync-message--error">{error}</div>
        )}
        {msg && (
          <div className="sync-message">{msg}</div>
        )}

        {sourceFilter === 'DEMO' && (
          <div className="demo-banner">
            ◆ DEMO DATA MODE — Synthetic observations for demonstration only.
            These do NOT represent real NASA FIRMS detections.
          </div>
        )}
        {sourceFilter === 'ALL' && (
          <div className="demo-banner demo-banner--all">
            Showing all sources — live NASA FIRMS and demo data are labeled separately in each card.
          </div>
        )}

        <section className="metrics metrics--impact">
          <Stat label={sourceFilter === 'LIVE' ? 'LIVE OBSERVATIONS' : sourceFilter === 'DEMO' ? 'DEMO OBSERVATIONS' : 'TOTAL OBSERVATIONS'} value={stats?.total_observations ?? candidates.length} />
          <Stat label="VERIFIED" value={stats?.verified_observations ?? '—'} tone="amber" />
          <Stat label="UNVERIFIED" value={stats?.unverified_observations ?? '—'} />
          <Stat
            label="TRAINING ELIGIBLE"
            value={eligibility?.eligible_for_training ? 'YES' : 'NO'}
            tone={eligibility?.eligible_for_training ? 'green' : 'red'}
          />
        </section>

        <section className="detail">
          <h3>Training readiness</h3>
          <p>
            Status: <strong>{eligibility?.training_readiness ?? stats?.training_readiness ?? 'Not available'}</strong>
          </p>
          {eligibility?.excluded_false_positive !== undefined && (
            <p>False positives excluded from training: <strong>{eligibility.excluded_false_positive}</strong></p>
          )}

          {eligibility?.class_counts && (
            <div className="baseline-row">
              {Object.entries(eligibility.class_counts).map(([name, count]) => (
                <div key={name}>
                  <strong>{count}</strong>
                  <span>{name.replace(/_/g, ' ')}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <IndustrialFireBatchReview />

        {!searched && filters.verify !== 'UNVERIFIED' && (
          <section className="detail labeling-review-section">
            <h3>Review verification</h3>
            <p className="detail__reason">
              Assistant evidence review of already-verified labels. Based on existing fields only —
              it does not change the analyst's decision, retrain any model, or overwrite verification records.
            </p>
            {verifiedLoading ? (
              <p className="empty">Loading verified labels…</p>
            ) : verifiedList.length === 0 ? (
              <p className="empty">No verified labels available to review.</p>
            ) : (
              <div className="labeling-cards">
                {verifiedList.map((h) => (
                  <VerificationReviewCard
                    key={h.id}
                    hotspot={h}
                    note={note}
                    busy={savingId === h.id}
                    onVerify={{
                      noteChange: setNote,
                      click: (decision) => handleVerify(h.id, decision),
                    }}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        <div className="labeling-cards">
          {searched ? (
            <InvestigationCard
              hotspot={searched}
              note={note}
              busy={savingId === searched.id}
              isSearchResult
              onVerify={{
                noteChange: setNote,
                click: (decision) => handleVerify(searched.id, decision),
              }}
              onDeepAnalysis={() => setOpenDeepId(searched.id)}
            />
          ) : loading ? (
            <p className="empty">Loading filtered observations…</p>
          ) : searchError ? (
            <div className="labeling-search__error-panel">
              <p className="empty">{searchError}</p>
              <button className="btn-chip" onClick={clearSearch}>
                Back to queue
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <p className="empty">
              No observations match the current filters.
            </p>
          ) : (
            filtered.map((hotspot) => {
              const busy = savingId === hotspot.id
              return (
                <InvestigationCard
                  key={hotspot.id}
                  hotspot={hotspot}
                  note={note}
                  busy={busy}
                  isSearchResult={false}
                  onVerify={{
                    noteChange: setNote,
                    click: (decision) => handleVerify(hotspot.id, decision),
                  }}
                  onDeepAnalysis={() => setOpenDeepId(hotspot.id)}
                />
              )
            })
          )}
        </div>
      </div>

      {openDeepId !== null && (
        <DeepAnalysis
          hotspotId={openDeepId}
          onClose={() => setOpenDeepId(null)}
          onVerified={(id) => {
            setOpenDeepId(null)
            if (searched && searched.id === id) {
              // refresh the search result so the card shows the new verification
              handleSearch({ preventDefault: () => {} }, String(id))
            }
          }}
        />
      )}
    </main>
  )
}

/**
 * Compact INDUSTRIAL_FIRE batch-review panel.
 *
 * READ-ONLY candidate list sorted by industrial_fire_candidate_score
 * descending. Every decision is an explicit analyst action via the existing
 * POST /hotspots/{id}/verify workflow. A candidate is NEVER auto-labeled,
 * and existing verified decisions are NEVER overwritten.
 */
function IndustrialFireBatchReview() {
  const [candidates, setCandidates] = useState([])
  const [progress, setProgress] = useState(null)
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [note, setNote] = useState('')
  const [msg, setMsg] = useState(null)
  const [error, setError] = useState(null)

  const load = async () => {
    try {
      const [list, prog] = await Promise.all([
        fetchIndustrialFireCandidates({ limit: 37 }),
        fetchIndustrialFireReviewProgress(),
      ])
      setCandidates(list.candidates || [])
      setProgress(prog)
    } catch (err) {
      setError(err.message || 'Could not load industrial-fire review queue.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function handleVerify(hotspotId, decision) {
    setSavingId(hotspotId)
    setMsg(null)
    setError(null)
    try {
      if (decision === 'confirmed_industrial_fire' && !note.trim()) {
        setError('An analyst note is required to confirm an industrial fire.')
        setSavingId(null)
        return
      }
      await verifyHotspot(hotspotId, decision, note)
      setMsg(`Saved ${decision.replace(/_/g, ' ')} for hotspot ${hotspotId}.`)
      setNote('')
      await load() // refresh candidate list + progress after every verification
    } catch (err) {
      setError(err.message || 'Verification failed.')
    } finally {
      setSavingId(null)
    }
  }

  const DECISIONS = [
    { value: 'confirmed_industrial_fire', label: 'Confirm industrial fire', requiresNote: true },
    { value: 'confirmed_normal_industrial_heat', label: 'Confirm normal industrial heat' },
    { value: 'wildfire', label: 'Mark wildfire' },
    { value: 'agricultural', label: 'Mark agricultural' },
    { value: 'false_positive', label: 'Mark false positive' },
    { value: 'unknown', label: 'Mark unknown' },
  ]

  return (
    <section className="detail industrial-fire-review">
      <h3>INDUSTRIAL_FIRE batch review</h3>
      <p className="detail__reason">
        Top 37 candidates sorted by industrial_fire_candidate_score descending.
        A candidate is NOT automatically an industrial fire — every decision
        is an explicit analyst action. Facility proximity is CONTEXT, not
        proof of causation. UNKNOWN remains UNKNOWN until you decide.
      </p>

      {progress && (
        <div className="industrial-fire-review__progress">
          <span className="industrial-fire-review__stat">
            <strong>{progress.verified.confirmed_industrial_fire}</strong> industrial fire
          </span>
          <span className="industrial-fire-review__stat">
            <strong>{progress.verified.confirmed_normal_industrial_heat}</strong> normal industrial heat
          </span>
          <span className="industrial-fire-review__stat">
            <strong>{progress.verified.wildfire}</strong> wildfire
          </span>
          <span className="industrial-fire-review__stat">
            <strong>{progress.verified.agricultural}</strong> agricultural
          </span>
          <span className="industrial-fire-review__stat">
            <strong>{progress.verified.false_positive}</strong> false positive
          </span>
          <span className="industrial-fire-review__stat">
            <strong>{progress.verified.unknown}</strong> unknown
          </span>
          <span className="industrial-fire-review__stat industrial-fire-review__stat--remaining">
            <strong>{progress.remaining_candidates}</strong> remaining candidates
          </span>
        </div>
      )}

      {error && <p className="empty">{error}</p>}
      {msg && <p className="empty">{msg}</p>}

      {loading ? (
        <p className="empty">Loading industrial-fire candidates…</p>
      ) : candidates.length === 0 ? (
        <p className="empty">No industrial-fire candidates awaiting review.</p>
      ) : (
        <div className="labeling-cards">
          {candidates.map((c) => (
            <article key={c.hotspot_id} className="industrial-fire-review__card">
              <div className="industrial-fire-review__head">
                <span className="industrial-fire-review__id">#{c.hotspot_id}</span>
                <span className="industrial-fire-review__score">
                  score {c.industrial_fire_candidate_score}
                </span>
                <span className="industrial-fire-review__tier">{c.baseline_status}</span>
              </div>

              <div className="industrial-fire-review__grid">
                <div><span>Facility</span><strong>{c.facility_name || '—'}</strong></div>
                <div><span>Distance</span><strong>{c.facility_distance != null ? c.facility_distance + ' km' : '—'}</strong></div>
                <div><span>Brightness</span><strong>{c.brightness}</strong></div>
                <div><span>FRP</span><strong>{c.frp != null ? c.frp : '—'}</strong></div>
                <div><span>Confidence</span><strong>{c.source_confidence != null ? c.source_confidence + '%' : '—'}</strong></div>
                <div><span>Baseline</span><strong>{c.baseline_status}</strong></div>
                <div><span>z-score</span><strong>{c.z_score}</strong></div>
                <div><span>Deviation</span><strong>{c.deviation_percentage != null ? c.deviation_percentage + '%' : '—'}</strong></div>
                <div><span>Persistence</span><strong>{c.persistence_score}</strong></div>
                <div><span>Anomaly</span><strong>{c.anomaly ? 'YES' : 'NO'}</strong></div>
                <div><span>Risk</span><strong>{c.risk_level}</strong></div>
                <div><span>Acquired</span><strong>{fmtDate(c.acq_date)}</strong></div>
              </div>

              {c.reason_codes ? (
                <div className="detail__codes">
                  {c.reason_codes.split(',').map((code) => (
                    <span className="code-chip" key={code}>{code}</span>
                  ))}
                </div>
              ) : null}

              <div className="industrial-fire-review__actions">
                <textarea
                  className="industrial-fire-review__note"
                  placeholder="Analyst note (required for confirmed_industrial_fire)…"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                />
                <div className="industrial-fire-review__btns">
                  {DECISIONS.map((d) => (
                    <button
                      key={d.value}
                      className="btn-chip"
                      disabled={savingId === c.hotspot_id}
                      onClick={() => handleVerify(c.hotspot_id, d.value)}
                      title={d.requiresNote ? 'Note required' : ''}
                    >
                      {savingId === c.hotspot_id ? 'Saving…' : d.label}
                    </button>
                  ))}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

/**
 * Per-candidate evidence panel for the INDUSTRIAL_FIRE batch review.
 *
 * REMOVED FOR THIS ITERATION. The Analyst Queue is a compact candidate-review
 * interface: each card shows only the normal fields (Event ID, facility,
 * distance, confidence, baseline, persistence, anomaly, risk, candidate
 * score, acquisition, reason) plus the existing verification controls.
 * No satellite imagery, no thermal history, no Deep Analysis, no
 * investigation narrative.
 */
