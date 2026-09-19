import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, useMap } from 'react-leaflet'
import { useMemo, useEffect, useState, useCallback } from 'react'
import { getThermalSeverity } from '../utils/thermalSeverity'

// Command Center operational map — powered by OpenStreetMap Standard tiles.
//
// OSM Standard — detailed roads, labels, boundaries, cities, POIs.
// OSM tiles never show watermarks.
//
// Tile failures show a clear error state instead of silent fallback.
//
// Attribution is required by OpenStreetMap.

const CATEGORY_COLOR = {
  industrial_alert: '#E23D3D',
  industrial_new: '#E23D3D',
  industrial_normal: '#F2A93B',
  wildfire: '#8B5E3C',
  agricultural_burning: '#3FA796',
  unknown: '#6B7280',
}

const CATEGORY_LABEL = {
  industrial_alert: 'Industrial — Alert',
  industrial_new: 'Industrial — New / Unverified',
  industrial_normal: 'Industrial — Normal',
  wildfire: 'Wildfire',
  agricultural_burning: 'Agricultural Burning',
  unknown: 'Unknown — insufficient evidence',
}

const SEVERITY_LABELS = {
  low: 'Weak',
  moderate: 'Moderate',
  high: 'High',
  extreme: 'Extreme',
  unknown: 'Unknown',
}

const SEVERITY_KEYS = ['low', 'moderate', 'high', 'extreme', 'unknown']

function MapLegend() {
  return (
    <div className="map-legend">
      <div className="map-legend__title">NASA FIRMS — Raw Thermal Signal</div>
      {SEVERITY_KEYS.map((key) => (
        <div key={key} className="map-legend__item">
          <span className={`map-legend__dot map-legend__dot--${key}`} />
          <span>{SEVERITY_LABELS[key]}</span>
        </div>
      ))}
      <div className="map-legend__sep" />
      <div className="map-legend__item">
        <span className={`map-legend__dot map-legend__dot--unknown`} />
        <span>Demo — synthetic</span>
      </div>
      <p className="map-legend__note">Thermal signal ≠ KAVACH risk</p>
    </div>
  )
}

function FitToData({ hotspots }) {
  const map = useMap()
  useEffect(() => {
    if (!hotspots || hotspots.length === 0) return
    const bounds = [
      [Infinity, Infinity],
      [-Infinity, -Infinity],
    ]
    hotspots.forEach((h) => {
      if (h.lat != null && h.lon != null) {
        bounds[0][0] = Math.min(bounds[0][0], h.lat)
        bounds[0][1] = Math.min(bounds[0][1], h.lon)
        bounds[1][0] = Math.max(bounds[1][0], h.lat)
        bounds[1][1] = Math.max(bounds[1][1], h.lon)
      }
    })
    if (bounds[0][0] < bounds[1][0] && bounds[0][1] < bounds[1][1]) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 10 })
    }
  }, [map, hotspots])
  return null
}

function MapError({ code }) {
  if (code === 'TILE_ERROR') {
    return (
      <div className="map-error">
        <div className="map-error__content">
          <div className="map-error__icon">⚠</div>
          <div className="map-error__title">Map Tiles Failed to Load</div>
          <div className="map-error__message">
            OSM tiles are returning errors. Check your network connection and try again.
          </div>
          <div className="map-error__hint">
            If the problem persists, contact your administrator.
          </div>
        </div>
      </div>
    )
  }
  return null
}

function markerForHotspot(h) {
  const anomalyWeight = h.is_anomaly ? 3 : 1

  if (h.source === 'nasa_firms') {
    const sev = getThermalSeverity(h.brightness, h.frp)
    return {
      color: sev.color,
      fillColor: sev.color,
      fillOpacity: 0.9,
      weight: anomalyWeight,
      radius: h.is_anomaly ? 9 : 7,
      isNasa: true,
      sevKey: sev.key,
      sevLabel: sev.label,
      riskLevel: h.risk_level,
    }
  }

  const color = CATEGORY_COLOR[h.category] || '#6B7280'
  return {
    color,
    fillColor: color,
    fillOpacity: 0.85,
    weight: anomalyWeight,
    radius: h.is_anomaly ? 10 : 7,
    isNasa: false,
    sevKey: null,
    sevLabel: null,
    riskLevel: h.risk_level,
  }
}

export default function HeatMap({ hotspots, onSelect }) {
  const [mapError, setMapError] = useState(null)
  const [tileErrorCount, setTileErrorCount] = useState(0)

  const handleTileError = useCallback(() => {
    setTileErrorCount((prev) => {
      const count = prev + 1
      if (count >= 10 && !mapError) {
        setMapError('TILE_ERROR')
      }
      return count
    })
  }, [mapError])

  const bounds = useMemo(() => {
    if (!hotspots || hotspots.length === 0) return null
    let minLat = Infinity, minLon = Infinity, maxLat = -Infinity, maxLon = -Infinity
    hotspots.forEach((h) => {
      if (h.lat != null && h.lon != null) {
        minLat = Math.min(minLat, h.lat)
        minLon = Math.min(minLon, h.lon)
        maxLat = Math.max(maxLat, h.lat)
        maxLon = Math.max(maxLon, h.lon)
      }
    })
    if (minLat < maxLat && minLon < maxLon) {
      return [[minLat, minLon], [maxLat, maxLon]]
    }
    return null
  }, [hotspots])

  return (
    <div className="map-wrapper">
      <MapContainer
        center={[22.5, 80]}
        zoom={5}
        scrollWheelZoom={true}
        className="map"
        zoomControl={true}
        maxZoom={18}
        minZoom={3}
      >
        {mapError && <MapError code={mapError} />}
        <FitToData hotspots={hotspots} />
        <TileLayer
          attribution={OSM_ATTRIBUTION}
          url={OSM_URL}
          maxZoom={19}
          attributionControl={true}
          showTileCoordError={false}
          updateWhenIdle={true}
          onError={handleTileError}
        />
        <MapLegend />
        {hotspots.map((h) => {
          const m = markerForHotspot(h)
          const isCritical = m.riskLevel === 'CRITICAL'
          return (
            <g key={h.id}>
              {isCritical && (
                <CircleMarker
                  center={[h.lat, h.lon]}
                  radius={m.radius + 6}
                  pathOptions={{
                    color: '#FF0000',
                    fillColor: '#FF0000',
                    fillOpacity: 0.15,
                    weight: 0,
                    className: 'critical-pulse',
                  }}
                />
              )}
              <CircleMarker
                center={[h.lat, h.lon]}
                radius={m.radius}
                pathOptions={{
                  color: isCritical ? '#FF0000' : m.color,
                  fillColor: m.fillColor,
                  fillOpacity: m.fillOpacity,
                  weight: isCritical ? m.weight + 1 : m.weight,
                }}
                eventHandlers={{ click: () => onSelect && onSelect(h) }}
              >
                <Tooltip direction="top" offset={[0, -10]} opacity={0.95} permanent={false}>
                  <div className="map-tooltip">
                    {m.isNasa ? (
                      <>
                        <div className="map-tooltip__source">NASA FIRMS</div>
                        <div className="map-tooltip__sev">
                          <span className={`map-tooltip__dot map-tooltip__dot--${m.sevKey}`} />
                          {m.sevLabel} thermal signal
                        </div>
                        <div className="map-tooltip__row">Brightness {h.brightness.toFixed(1)} K</div>
                        <div className="map-tooltip__row">FRP {h.frp != null ? h.frp.toFixed(1) : '—'} MW</div>
                      </>
                    ) : (
                      <>
                        <div className="map-tooltip__source">DEMO — synthetic</div>
                        <div className="map-tooltip__row">{CATEGORY_LABEL[h.category] || h.category}</div>
                        <div className="map-tooltip__row">Brightness {h.brightness.toFixed(1)} K</div>
                      </>
                    )}
                    <div className="map-tooltip__row map-tooltip__mono">
                      {h.lat.toFixed(3)}, {h.lon.toFixed(3)}
                    </div>
                    {h.acq_date && (
                      <div className="map-tooltip__row map-tooltip__mono">
                        {new Date(h.acq_date).toISOString().replace('T', ' ').slice(0, 19)} UTC
                      </div>
                    )}
                    {isCritical && (
                      <div className="map-tooltip__row map-tooltip__alert">
                        ⚠ CRITICAL risk level
                      </div>
                    )}
                  </div>
                </Tooltip>
                <Popup>
                  <div className="popup">
                    {m.isNasa && (
                      <div className="popup__source-flag popup__source-flag--nasa">
                        <span className="popup__nasa-tag">NASA</span>
                        <span className={`popup__sev-tag popup__sev-tag--`}>{m.sevLabel.toUpperCase()} THERMAL SIGNAL</span>
                      </div>
                    )}
                    <strong>{h.facility ? h.facility.name : 'Unregistered location'}</strong>
                    {isCritical && (
                      <div className="popup__flag popup__flag--critical">
                        ⚠ CRITICAL risk level — immediate analyst review
                      </div>
                    )}
                    {m.isNasa ? (
                      <>
                        <div className="popup__row">
                          <span className={`popup__sev-dot popup__sev-dot--${m.sevKey}`} />
                          {m.sevLabel} thermal signal
                        </div>
                        <div className="popup__row popup__mono">brightness {h.brightness.toFixed(1)} K · FRP {h.frp != null ? h.frp.toFixed(1) : '—'} MW</div>
                        <div className="popup__row popup__mono">satellite {h.satellite || '—'}</div>
                      </>
                    ) : (
                      <div className="popup__row">{CATEGORY_LABEL[h.category] || h.category}</div>
                    )}
                    <div className="popup__row popup__mono">{h.lat.toFixed(3)}, {h.lon.toFixed(3)}</div>
                    {h.is_anomaly && <div className="popup__flag">⚠ flagged as anomaly</div>}
                  </div>
                </Popup>
              </CircleMarker>
            </g>
          )
        })}
      </MapContainer>
    </div>
  )
}

const OSM_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'

const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
