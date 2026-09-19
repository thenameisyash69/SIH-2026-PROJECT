/**
 * Command Center candidate list.
 *
 * A CLEAN candidate-selection screen: each card shows only concise
 * operational information and is SELECTABLE. The full investigation
 * narrative (WHERE/WHAT/WHY/HOW SERIOUS/LIKELY CAUSE/WHAT TO DO/EVIDENCE
 * NEEDED/VERIFICATION) lives in the Deep Analysis workspace, NOT here.
 */
import { useState, useEffect } from 'react'
import { getThermalSeverity } from '../utils/thermalSeverity'

const RISK_TONE = { LOW: 'low', WATCH: 'watch', HIGH: 'high', CRITICAL: 'critical' }

function fmtDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString()
}

function facilityText(hotspot) {
  if (!hotspot?.facility) return 'No mapped facility'
  return hotspot.facility.name || hotspot.facility.id || 'Mapped facility'
}

export default function CandidateList({ hotspots = [], selectedId, onSelect, emptyLabel }) {
  if (!hotspots.length) {
    return <p className="empty">{emptyLabel || 'No candidates available.'}</p>
  }

  return (
    <ul className="candidate-list">
      {hotspots.map((h) => {
        const sev = getThermalSeverity(h.brightness, h.frp)
        const isSel = selectedId === h.id
        return (
          <li
            key={h.id}
            className={`candidate-card candidate-card--${sev.key} ${isSel ? 'candidate-card--selected' : ''}`}
            role="button"
            tabIndex={0}
            onClick={() => onSelect && onSelect(h)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect && onSelect(h)
              }
            }}
          >
            <div className="candidate-card__head">
              <span className="candidate-card__id">#{h.id}</span>
              <span className={`candidate-card__risk badge badge--risk-${RISK_TONE[h.risk_level] || 'low'}`}>
                {h.risk_level}
              </span>
              <span className="candidate-card__sev">{sev.label}</span>
            </div>

            <div className="candidate-card__title">
              <span className="candidate-card__facility">{facilityText(h)}</span>
            </div>

            <div className="candidate-card__grid">
              <div><span>Brightness</span><strong>{h.brightness != null ? h.brightness.toFixed(1) : '—'} K</strong></div>
              <div><span>FRP</span><strong>{h.frp != null ? h.frp.toFixed(1) : '—'} MW</strong></div>
              <div><span>Classification</span><strong>{h.category.replace(/_/g, ' ')}</strong></div>
              <div><span>Baseline</span><strong>{h.baseline_status.replace(/_/g, ' ')}</strong></div>
              <div><span>Acquired</span><strong>{fmtDate(h.acq_date)}</strong></div>
              {h.industrial_fire_candidate_score != null && (
                <div><span>Industrial-fire score</span><strong>{h.industrial_fire_candidate_score}</strong></div>
              )}
              {h.risk_score != null && (
                <div><span>Risk score</span><strong>{h.risk_score}</strong></div>
              )}
              {h.distance_to_facility_km != null && (
                <div><span>Facility distance</span><strong>{h.distance_to_facility_km.toFixed(2)} km</strong></div>
              )}
            </div>

            {h.reason && (
              <p className="candidate-card__reason">{h.reason}</p>
            )}

            <div className="candidate-card__actions">
              <button
                className="btn-primary"
                onClick={(e) => { e.stopPropagation(); onSelect && onSelect(h, 'deep') }}
              >
                Deep Analysis →
              </button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}