/**
 * Deep Analysis — the complete investigation workspace.
 *
 * The selected candidate is the single source of truth for everything
 * rendered here; switching A -> B -> C updates the map, markers, context
 * radius, geographic context, timeline and every displayed field.
 *
 * DetailPanel already renders the full investigation narrative (WHERE / WHAT
 * / WHY / HOW SERIOUS / LIKELY CAUSE / baseline + histogram / map / action /
 * evidence / verification) AND the Timeline component when `deep` is true.
 * DeepAnalysis is therefore a thin wrapper that:
 *   - owns the hotspot fetch + loading / error / not-found states
 *   - resets all per-hotspot state the instant the hotspot id changes
 *   - renders DetailPanel(deep=true) which contains the map + timeline
 *
 * No backend / API / risk / anomaly / classifier / verification logic is
 * touched — this is a pure UI composition over existing components.
 */
import { useEffect, useState } from 'react'
import { fetchHotspotById } from '../api'
import DetailPanel from './DetailPanel'

export default function DeepAnalysis({ hotspotId, hotspots = [], onClose, onVerified }) {
  const [hotspot, setHotspot] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  // Incrementing this re-runs the fetch effect without changing hotspotId.
  const [retrySeq, setRetrySeq] = useState(0)

  // Reset every per-hotspot state the instant the hotspot id changes so the
  // UI can never display stale data from a previous candidate (A -> B -> C).
  useEffect(() => {
    let cancelled = false
    setHotspot(null)
    setError(null)
    setLoading(true)

    async function load() {
      try {
        const data = await fetchHotspotById(hotspotId)
        if (cancelled) return
        if (!data || !data.id) {
          setError(`Hotspot #${hotspotId} not found.`)
          setHotspot(null)
        } else {
          setHotspot(data)
        }
      } catch (err) {
        if (cancelled) return
        const isHttpError = err?.response?.status
        const isNetwork = !isHttpError && (err?.code === 'ECONNABORTED' || err?.code === 'ERR_NETWORK' || err?.code === 'ERR_CANCELED')
        const detail = err?.response?.data?.detail || err?.message || 'Could not load hotspot.'
        if (isHttpError === 404) {
          setError(`Hotspot #${hotspotId} not found.`)
        } else if (isNetwork) {
          setError(`Network error while loading hotspot #${hotspotId}. Check your connection and try again.`)
        } else {
          setError(`Could not load hotspot #${hotspotId}: ${detail}`)
        }
        setHotspot(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [hotspotId, retrySeq])

  function retry() {
    setRetrySeq((s) => s + 1)
  }

  if (loading) {
    return (
      <div className="deep-analysis deep-analysis--loading">
        <p>Loading hotspot #{hotspotId}…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="deep-analysis deep-analysis--error">
        <p className="empty">{error}</p>
        <button className="btn-chip" onClick={retry}>
          Retry
        </button>
        {onClose && (
          <button className="btn-chip" onClick={onClose}>
            Back to queue
          </button>
        )}
      </div>
    )
  }

  if (!hotspot) {
    return (
      <div className="deep-analysis deep-analysis--empty">
        <p>Select a candidate from the queue, then open Deep Analysis.</p>
      </div>
    )
  }

  return (
    <div className="deep-analysis">
      <div className="deep-analysis__bar">
        <div>
          <h2>Deep Analysis</h2>
          <span className="deep-analysis__sub">
            Event #{hotspot.id} · {hotspot.facility ? hotspot.facility.name : 'Unregistered location'}
          </span>
        </div>
        {hotspot.source === 'demo' && (
          <div className="demo-banner demo-banner--persistent">
            DEMO DATA — SYNTHETIC SCENARIO
          </div>
        )}
        {onClose && (
          <button className="btn-secondary" onClick={onClose}>
            ← Back to queue
          </button>
        )}
       </div>

      {hotspot.source === 'demo' && (
        <p className="detail__disclaimer detail__disclaimer--demo">
          This analysis uses synthetic demonstration data and does not represent real NASA FIRMS observations.
        </p>
      )}

      <div className="deep-analysis__body">
        <DetailPanel hotspot={hotspot} hotspots={hotspots} deep />
      </div>
    </div>
  )
}