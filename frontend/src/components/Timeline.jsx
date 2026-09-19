import { useEffect, useRef, useState } from 'react'
import { fetchHotspotHistory } from '../api'

const HISTORY_CACHE_KEY = 'kavach_timeline_history_cache'
const LAST_HOTSPOT_KEY = 'kavach_timeline_last_hotspot'

function getCache() {
  try {
    const raw = localStorage.getItem(HISTORY_CACHE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function saveCache(cache) {
  try {
    localStorage.setItem(HISTORY_CACHE_KEY, JSON.stringify(cache))
  } catch {
    /* storage unavailable */
  }
}

function getLastHotspotId() {
  try {
    return localStorage.getItem(LAST_HOTSPOT_KEY)
  } catch {
    return null
  }
}

function saveLastHotspotId(id) {
  try {
    localStorage.setItem(LAST_HOTSPOT_KEY, String(id))
  } catch {
    /* storage unavailable */
  }
}

export default function Timeline({ hotspotId }) {
  const [history, setHistory] = useState([])
  const [status, setStatus] = useState('loading')
  const seqRef = useRef(0)

  useEffect(() => {
    if (!hotspotId) {
      setStatus('empty')
      setHistory([])
      return
    }
    saveLastHotspotId(hotspotId)
    const mySeq = ++seqRef.current
    setStatus('loading')
    setHistory([])

    const cache = getCache()
    const cached = cache[hotspotId]
    if (cached && Array.isArray(cached.data) && cached.data.length > 0) {
      setHistory(cached.data)
      setStatus('ready')
    }

    fetchHotspotHistory(hotspotId)
      .then((data) => {
        if (mySeq !== seqRef.current) return
        const arr = Array.isArray(data) ? data : []
        setHistory(arr)
        setStatus(arr.length ? 'ready' : 'empty')
        const newCache = { ...getCache(), [hotspotId]: { data: arr, fetchedAt: Date.now() } }
        saveCache(newCache)
      })
      .catch(() => {
        if (mySeq !== seqRef.current) return
        setHistory([])
        setStatus('error')
      })
  }, [hotspotId])

  if (status === 'loading') return <p className="empty">Loading history…</p>
  if (status === 'error') return (
    <div className="timeline timeline--error">
      <p className="empty">Could not load history.</p>
      <button className="btn-chip" onClick={() => {
        const mySeq = ++seqRef.current
        setStatus('loading')
        fetchHotspotHistory(hotspotId)
          .then((data) => {
            if (mySeq !== seqRef.current) return
            const arr = Array.isArray(data) ? data : []
            setHistory(arr)
            setStatus(arr.length ? 'ready' : 'empty')
            const newCache = { ...getCache(), [hotspotId]: { data: arr, fetchedAt: Date.now() } }
            saveCache(newCache)
          })
          .catch(() => { if (mySeq === seqRef.current) setStatus('error') })
      }}>
        Retry
      </button>
    </div>
  )
  const cacheFreshness = (() => {
    const cache = getCache()
    const cached = cache[hotspotId]
    if (cached && cached.fetchedAt) {
      const minutes = Math.round((Date.now() - cached.fetchedAt) / 60000)
      if (minutes < 1) return 'cached just now'
      if (minutes < 60) return `cached ${minutes}m ago`
      return `cached ${Math.floor(minutes / 60)}h ago`
    }
    return null
  })()

  if (status === 'empty') return (
    <div className="timeline">
      <p className="empty">
        No prior observation history stored for this hotspot.
      </p>
      <p className="empty" style={{ fontSize: '0.85rem' }}>
        This hotspot has no linked facility registration or historical observations
        in the 90-day window. Timeline requires a facility association with
        repeated NASA FIRMS detections over time. Verification by an analyst
        does not create facility registration or observation history — those
        require separate processing.
      </p>
      {cacheFreshness && (
        <p className="empty" style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>
          {cacheFreshness} — no newer data available from backend.
        </p>
      )}
    </div>
  )

  const max = Math.max(...history.map((h) => h.brightness))
  const min = Math.min(...history.map((h) => h.brightness))
  const range = max - min || 1
  const recent = history.slice(-30)

  return (
    <div className="timeline">
      {cacheFreshness && status === 'ready' && (
        <p className="timeline__cache-note">
          Showing cached data {cacheFreshness}. Refreshing from backend…
        </p>
      )}
      <div className="timeline__chart">
        {recent.map((h) => {
          const heightPct = 15 + ((h.brightness - min) / range) * 85
          return (
            <div
              key={h.id}
              className={`timeline__bar ${h.is_anomaly ? 'timeline__bar--anomaly' : ''}`}
              style={{ height: `${heightPct}%` }}
              title={`${new Date(h.acq_date).toLocaleDateString()} — brightness ${h.brightness.toFixed(1)}`}
            />
          )
        })}
      </div>
      <div className="timeline__labels">
        <span>{new Date(recent[0].acq_date).toLocaleDateString()}</span>
        <span>{new Date(recent[recent.length - 1].acq_date).toLocaleDateString()}</span>
      </div>
      <p className="timeline__note">
        {recent.filter((h) => h.is_anomaly).length} anomalous reading(s) in this window — bars in red.
      </p>
    </div>
  )
}
