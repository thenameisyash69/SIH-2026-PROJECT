// Fallback data shown if the backend isn't running yet.
export const demoHotspots = [
  { id: 1, lat: 22.3511, lon: 69.8340, brightness: 312, category: 'industrial_normal', is_anomaly: false,
    reason: 'Persistent, low-variance heat source at known facility Jamnagar Refinery.', reason_codes: 'NEAR_FACILITY,PERSISTENT_EXPECTED',
    classification_method: 'rules', classification_confidence: 0.8, baseline_status: 'NORMAL', z_score: 0.4,
    deviation_percentage: 2.1, distance_to_facility_km: 0.3, risk_level: 'LOW', risk_score: 8.0,
    source: 'demo_synthetic', state: 'Gujarat', facility: { name: 'Jamnagar Refinery', type: 'refinery' } },
  { id: 2, lat: 23.6693, lon: 86.1511, brightness: 341, category: 'industrial_alert', is_anomaly: true,
    reason: 'Thermal reading deviates 12.4% from this facility\u2019s historical baseline (z=2.9).', reason_codes: 'NEAR_FACILITY,HIGH_DEVIATION',
    classification_method: 'rules', classification_confidence: 0.75, baseline_status: 'ABNORMAL', z_score: 2.9,
    deviation_percentage: 12.4, distance_to_facility_km: 0.2, risk_level: 'HIGH', risk_score: 62.0,
    source: 'demo_synthetic', state: 'Jharkhand', facility: { name: 'Bokaro Steel Plant', type: 'steel_plant' } },
  { id: 3, lat: 20.9500, lon: 85.2333, brightness: 305, category: 'industrial_normal', is_anomaly: false,
    reason: 'Persistent, low-variance heat source at known facility Talcher Thermal Power Station.', reason_codes: 'NEAR_FACILITY,PERSISTENT_EXPECTED',
    classification_method: 'rules', classification_confidence: 0.8, baseline_status: 'NORMAL', z_score: 0.2,
    deviation_percentage: 1.0, distance_to_facility_km: 0.4, risk_level: 'LOW', risk_score: 6.0,
    source: 'demo_synthetic', state: 'Odisha', facility: { name: 'Talcher Thermal Power Station', type: 'power_plant' } },
  { id: 4, lat: 30.7, lon: 76.7, brightness: 310, category: 'agricultural_burning', is_anomaly: false,
    reason: 'Location is farmland during the known stubble-burning season.', reason_codes: 'SEASONAL_AGRI_BURN',
    classification_method: 'rules', classification_confidence: 0.6, baseline_status: 'INSUFFICIENT_HISTORY', z_score: 0,
    deviation_percentage: 0, distance_to_facility_km: null, risk_level: 'LOW', risk_score: 5.0,
    source: 'demo_synthetic', state: 'Punjab', facility: null },
  { id: 5, lat: 11.4, lon: 76.7, brightness: 305, category: 'wildfire', is_anomaly: false,
    reason: 'Location falls within forest land-cover \u2014 consistent with wildfire context.', reason_codes: 'FOREST_LAND_COVER',
    classification_method: 'rules', classification_confidence: 0.65, baseline_status: 'INSUFFICIENT_HISTORY', z_score: 0,
    deviation_percentage: 0, distance_to_facility_km: null, risk_level: 'LOW', risk_score: 5.0,
    source: 'demo_synthetic', state: 'Kerala', facility: null },
]

export const demoAlerts = [
  { id: 1, hotspot_id: 2, severity: 'high', message: 'Bokaro Steel Plant: brightness abnormally high for routine process heat. (risk: HIGH, score 62.0)', created_at: new Date().toISOString() },
]
