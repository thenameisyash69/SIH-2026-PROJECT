/**
 * thermalSeverity.js — Shared display-only triage utility.
 *
 * IMPORTANT — this is a TRIAGE / DISPLAY indicator ONLY.
 * It is NOT:
 *   - fire probability
 *   - fire classification
 *   - operational risk
 *   - damage estimate
 *   - casualty prediction
 *
 * It is derived purely from raw NASA FIRMS fields (brightness, frp) and
 * is intended to let analysts quickly eyeball the raw satellite thermal
 * signal strength. It does NOT change any database values, does NOT
 * fabricate confidence, and does NOT assign KAVACH risk or category.
 *
 * Thresholds are display-only and documented here for SIH judges.
 */

const BRIGHTNESS = {
  LOW: { max: 300, key: 'low', label: 'Weak', color: '#3FA796' },       // < 300 K
  MODERATE: { min: 300, max: 320, key: 'moderate', label: 'Moderate', color: '#F2C14E' }, // 300–319.99
  HIGH: { min: 320, max: 340, key: 'high', label: 'High', color: '#F2A93B' },             // 320–339.99
  EXTREME: { min: 340, key: 'extreme', label: 'Extreme', color: '#E23D3D' },              // >= 340
}

const FRP = {
  LOW: { max: 5, key: 'low', label: 'Weak', color: '#3FA796' },          // < 5 MW
  MODERATE: { min: 5, max: 20, key: 'moderate', label: 'Moderate', color: '#F2C14E' },   // 5–19.99
  HIGH: { min: 20, max: 50, key: 'high', label: 'High', color: '#F2A93B' },              // 20–49.99
  EXTREME: { min: 50, key: 'extreme', label: 'Extreme', color: '#E23D3D' },              // >= 50
}

const UNKNOWN = {
  key: 'unknown',
  label: 'Unknown',
  color: '#6B7280',
}

const SEVERITY_ORDER = { unknown: 0, low: 1, moderate: 2, high: 3, extreme: 4 }

function brightnessSeverity(brightness) {
  if (brightness === null || brightness === undefined || Number.isNaN(Number(brightness))) {
    return null
  }
  const b = Number(brightness)
  if (b < BRIGHTNESS.LOW.max) return BRIGHTNESS.LOW
  if (b < BRIGHTNESS.MODERATE.max) return BRIGHTNESS.MODERATE
  if (b < BRIGHTNESS.HIGH.max) return BRIGHTNESS.HIGH
  return BRIGHTNESS.EXTREME
}

function frpSeverity(frp) {
  if (frp === null || frp === undefined || Number.isNaN(Number(frp))) {
    return null
  }
  const f = Number(frp)
  if (f < FRP.LOW.max) return FRP.LOW
  if (f < FRP.MODERATE.max) return FRP.MODERATE
  if (f < FRP.HIGH.max) return FRP.HIGH
  return FRP.EXTREME
}

/**
 * Combined thermal severity = the HIGHER severity of brightness and FRP.
 * If either is missing, fall back to whichever is available.
 * If both are missing, return UNKNOWN.
 */
export function getThermalSeverity(brightness, frp) {
  const bSev = brightnessSeverity(brightness)
  const fSev = frpSeverity(frp)

  if (!bSev && !fSev) {
    return UNKNOWN
  }
  if (!bSev) return fSev
  if (!fSev) return bSev

  return SEVERITY_ORDER[bSev.key] >= SEVERITY_ORDER[fSev.key] ? bSev : fSev
}

/** Convenience: severity key from a hotspot-like object. */
export function severityForHotspot(hotspot) {
  if (!hotspot) return UNKNOWN
  return getThermalSeverity(hotspot.brightness, hotspot.frp)
}

/** Severity key -> CSS class suffix used by styles. */
export function severityClass(key) {
  return `thermal-sev--${key || 'unknown'}`
}

/** Ordered list of severity keys for sorting (highest first). */
export const SEVERITY_KEYS = ['extreme', 'high', 'moderate', 'low', 'unknown']

export default {
  getThermalSeverity,
  severityForHotspot,
  severityClass,
  SEVERITY_KEYS,
  UNKNOWN,
}