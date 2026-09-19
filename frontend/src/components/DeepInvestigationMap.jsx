import { useState, useEffect } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, useMapEvents, Polygon, useMap } from "react-leaflet";

// KAVACH Deep Investigation map.
//
// Basemap: Hybrid — Esri World Imagery (satellite) overlaid with
// Esri World Boundaries and Places (road/place labels). Two stacked
// tile layers: satellite base + transparent labels on top.
// No API key required. Free tier, no watermarks.

const CONTEXT_RADIUS_KM = 5.0;

const BASEMAPS = {
  hybrid: {
    label: "Hybrid",
    layers: [
      {
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attribution:
          "&copy; Esri, Vantor, Earthstar Geographics, and the GIS User Community",
      },
      {
        url: "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attribution:
          "&copy; Esri, HERE, Garmin, (c) OpenStreetMap contributors, and the GIS user community",
      },
    ],
  },
};

// Small-circle approximation for the 5 km context radius at the hotspot
// latitude. Good enough for visual context (<= 5 km, low latitudes).
function latDeltaForKm(km) {
  return km / 110.574;
}
function lonDeltaForKm(km, lat) {
  return km / (111.320 * Math.cos(lat * Math.PI / 180));
}

function ContextRadius({ hotspot }) {
  if (!hotspot) return null;
  const lat = hotspot.lat;
  const lon = hotspot.lon;
  const dLat = latDeltaForKm(CONTEXT_RADIUS_KM);
  const dLon = lonDeltaForKm(CONTEXT_RADIUS_KM, lat);
  const bounds = [
    [lat - dLat, lon - dLon],
    [lat - dLat, lon + dLon],
    [lat + dLat, lon + dLon],
    [lat + dLat, lon - dLon],
  ];
  return (
    <Polygon
      positions={bounds}
      pathOptions={{
        color: "#2E6BFF",
        weight: 1.5,
        fillOpacity: 0.06,
        dashArray: "4 6",
      }}
    >
      <Tooltip direction="center" permanent opacity={0.85} className="context-radius-tooltip">
<div className="map-tooltip">
                  <div className="map-tooltip__source">KAVACH CONTEXT</div>
                  <div className="map-tooltip__row">
                    {CONTEXT_RADIUS_KM} km facility context — NOT a fire boundary
                  </div>
                </div>
      </Tooltip>
    </Polygon>
  );
}

function FacilityMarker({ facility }) {
  if (!facility) return null;
  return (
    <CircleMarker
      center={[facility.lat, facility.lon]}
      radius={7}
      pathOptions={{
        color: "#1E3A8A",
        fillColor: "#1E3A8A",
        fillOpacity: 0.95,
        weight: 2,
      }}
    >
      <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
        <div className="map-tooltip">
          <div className="map-tooltip__source">FACILITY</div>
          <div className="map-tooltip__row">{facility.name}</div>
        </div>
      </Tooltip>
      <Popup>
        <div className="popup">
          <strong>{facility.name}</strong>
          <div className="popup__row popup__mono">
            {facility.lat.toFixed(4)}, {facility.lon.toFixed(4)}
          </div>
        </div>
      </Popup>
    </CircleMarker>
  );
}

function BasemapSwitch({ basemap, onChange }) {
  return (
    <div className="deep-investigation__basemap-switch">
      {(["hybrid"]).map((key) => (
        <button
          key={key}
          className={`btn-chip ${basemap === key ? "btn-chip--active" : ""}`}
          onClick={() => onChange(key)}
        >
          {BASEMAPS[key].label}
        </button>
      ))}
    </div>
  );
}

function ZoomTracker({ onZoom }) {
  useMapEvents({
    zoomend(e) { onZoom(e.target.getZoom()); },
  });
  return null;
}

function FocusButton({ map, focusTarget, focusZoom }) {
  return (
    <button
      className="deep-investigation__focus"
      onClick={() => {
        if (!map) return;
        map.flyTo([focusTarget[0], focusTarget[1]], focusZoom, { duration: 0.8 });
      }}
    >
      Focus on event
    </button>
  );
}

 /**
 * Dedicated Leaflet map controller.
 *
 * react-leaflet v4 only honours MapContainer's `center`/`zoom` props for the
 * INITIAL placement. Once the map is mounted, changing those props does NOT
 * move it — the live map instance must be driven directly via flyTo. This
 * controller owns that logic in one place so that:
 *   - switching hotspot A -> B re-runs it (hotspot id is a dependency)
 *   - "Focus on event" re-uses the exact same path
 */
function MapController({ target, hotspotId }) {
  const map = useMap();

  useEffect(() => {
    if (!target) return;
    map.flyTo([target.lat, target.lng], target.zoom, { duration: 0.8 });
  }, [map, target.lat, target.lng, target.zoom, hotspotId]);

  return null;
}

export default function DeepInvestigationMap({ hotspot, hotspots = [] }) {
  const [basemap, setBasemap] = useState("hybrid");
  const [zoom, setZoom] = useState(14);
  const [map, setMap] = useState(null);

  const selected = BASEMAPS[basemap];
  const active = selected || BASEMAPS.hybrid;

  // Exact event / facility focus (spec §1):
  //   facility coords (if valid) -> hotspot lat/lon -> regional default.
  // The regional default is ONLY used before a valid hotspot is supplied;
  // it must never override a newly selected event.
  const facility = hotspot && hotspot.facility ? hotspot.facility : null;
  const hasValidHotspot =
    hotspot && Number.isFinite(hotspot.lat) && Number.isFinite(hotspot.lon);
  const focusTarget = hasValidHotspot
    ? {
        lat: hotspot.lat,
        lng: hotspot.lon,
        zoom: 17,
      }
    : { lat: 22.5, lng: 80, zoom: 8 };
  const center = hasValidHotspot
    ? [hotspot.lat, hotspot.lon]
    : [22.5, 80];

  return (
    <div className="deep-investigation">
      <div className="deep-investigation__head">
        <h3>Deep Investigation map</h3>
        {hotspot && (
          <span className="deep-investigation__coords">
            {hotspot.lat.toFixed(4)}, {hotspot.lon.toFixed(4)}
          </span>
        )}
        <BasemapSwitch basemap={basemap} onChange={setBasemap} />
      </div>

      <MapContainer
        center={center}
        zoom={zoom}
        zoomControl={true}
        scrollWheelZoom={true}
        className="map deep-investigation__map"
        whenCreated={(m) => { setMap(m); }}
      >
        {active.layers.map((layer, idx) => (
          <TileLayer
            key={`${active.label}-${idx}`}
            attribution={layer.attribution}
            url={layer.url}
            errorTileUrl=""
          />
        ))}
        <ZoomTracker onZoom={setZoom} />

        {/* Dedicated controller — moves the live map when the selected
            hotspot changes. Basemap switches do NOT trigger it. */}
        <MapController
          target={focusTarget}
          hotspotId={hotspot ? hotspot.id : null}
        />

        {/* 5 km facility association context radius — visual context only.
            It is NOT a fire boundary and does NOT prove causation.
            Keyed on the current hotspot id so it is torn down when the
            selection changes. */}
        {hotspot && (
          <ContextRadius key={`context-${hotspot.id}`} hotspot={hotspot} />
        )}

        {/* Facility marker — always visible when facility coordinates exist.
            Keyed on facility id so it is replaced, not reused, on switch. */}
        {facility && (
          <FacilityMarker
            key={`facility-${facility.id}`}
            facility={facility}
          />
        )}

        {hotspots.map((h) => {
          const isSel = hotspot && h.id === hotspot.id;
          return (
            <CircleMarker
              key={`thermal-${h.id}`}
              center={[h.lat, h.lon]}
              radius={isSel ? 12 : 7}
              pathOptions={{
                color: isSel ? "#E23D3D" : "#F2A93B",
                fillColor: isSel ? "#E23D3D" : "#F2A93B",
                fillOpacity: 0.9,
                weight: isSel ? 4 : 1,
              }}
            >
              <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
                <div className="map-tooltip">
                  {isSel ? (
                    <div className="map-tooltip__source">SELECTED thermal observation</div>
                  ) : (
                    <div className="map-tooltip__source">NASA FIRMS</div>
                  )}
                  <div className="map-tooltip__row">
                    Brightness {h.brightness != null ? h.brightness.toFixed(1) : "-"} K
                  </div>
                  <div className="map-tooltip__row">
                    FRP {h.frp != null ? h.frp.toFixed(1) : "-"} MW
                  </div>
                </div>
              </Tooltip>
              <Popup>
                <div className="popup">
                  <strong>{h.facility ? h.facility.name : "Unregistered location"}</strong>
                  <div className="popup__row popup__mono">
                    {h.lat.toFixed(4)}, {h.lon.toFixed(4)}
                  </div>
                  {h.is_anomaly && <div className="popup__flag">flagged as anomaly</div>}
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>

      <div className="deep-investigation__footer">
        <FocusButton map={map} focusTarget={focusTarget} focusZoom={focusTarget.zoom} />
        <span className="deep-investigation__zoom">Zoom: {zoom}</span>
        <span className="deep-investigation__note">
          Detailed map (OSM Standard) — satellite-detected thermal observation, NOT a fire boundary
        </span>
        {facility && (
          <span className="deep-investigation__note">
            Facility: {facility.name} · {CONTEXT_RADIUS_KM} km association radius
          </span>
        )}
      </div>
    </div>
  );
}

