import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'https://sih-2026-project-wlfy.onrender.com'

const client = axios.create({ baseURL: API_URL })

const firmsSyncClient = axios.create({ baseURL: API_URL, timeout: 60000 })

/**
 * Fetches ALL hotspots by internally paginating until fewer than `limit`
 * records are returned per page. Returns { hotspots, total, source }.
 *
 * Pass `singlePage: true` to get only one page (default uses large limit
 * for convenience but still returns the full envelope).
 */
export async function fetchHotspots(params = {}) {
  const { singlePage, ...rest } = params
  const useParams = { ...rest }

  if (singlePage) {
    const { data } = await client.get('/hotspots', { params: useParams })
    return data
  }

  const PAGE_SIZE = 2000
  let allHotspots = []
  let total = 0
  let offset = 0

  while (true) {
    const { data } = await client.get('/hotspots', {
      params: { ...useParams, limit: PAGE_SIZE, offset },
    })
    allHotspots = allHotspots.concat(data.hotspots || [])
    total = data.total
    if (data.hotspots.length < PAGE_SIZE) break
    offset += PAGE_SIZE
    if (offset >= total) break
  }

  return { hotspots: allHotspots, total }
}

export async function fetchHotspotById(id) {
  const { data } = await client.get(`/hotspots/${id}`)
  return data
}

export async function fetchVerification(id) {
  const { data } = await client.get(`/hotspots/${id}/verification`)
  return data
}

export async function fetchLabelingCandidates(params = {}) {
  const { data } = await client.get('/hotspots/labeling/candidates', { params })
  return data
}

export async function fetchAlerts(params = {}) {
  const { data } = await client.get('/alerts', { params })
  return data
}

export async function fetchHotspotHistory(id) {
  const { data } = await client.get(`/hotspots/${id}/history`)
  return data
}

export async function askChatbot(question) {
  const { data } = await client.post('/chatbot/query', { question })
  return data
}

export async function fetchSatelliteImage(hotspotId) {
  const { data } = await client.get(`/hotspots/${hotspotId}/satellite-image`)
  return data
}

export async function fetchStats() {
  const { data } = await client.get('/stats')
  return data
}

export async function fetchAssessment(hotspotId) {
  const { data } = await client.get(`/hotspots/${hotspotId}/assessment`)
  return data
}

export async function verifyHotspot(hotspotId, decision, note) {
  const { data } = await client.post(`/hotspots/${hotspotId}/verify`, { decision, note })
  return data
}

export async function fetchFacilityFingerprint(facilityId) {
  const { data } = await client.get(`/facilities/${facilityId}/fingerprint`)
  return data
}

export async function fetchFacilityThermalHistory(facilityId, windowDays = 90, source = 'nasa_firms', detailed = true) {
  const { data } = await client.get(`/facilities/${facilityId}/thermal-history`, {
    params: { window_days: windowDays, source, detailed },
  })
  return data
}

/**
 * READ-ONLY nearby mapped geographic features for an observation.
 * Uses the same Overpass / OpenStreetMap source as the backend's
 * landcover_fetcher — no API key, no signup. Returns only features that
 * actually exist; never invents a place or facility. A "nearby feature" is
 * NOT a confirmed source of fire.
 */
export async function fetchGeographicContext(hotspotId) {
  const { data } = await client.get(`/hotspots/${hotspotId}/geographic-context`)
  return data
}

export async function fetchFacilities() {
  const { data } = await client.get('/facilities')
  return data
}

export async function fetchModelPerformance() {
  const { data } = await client.get('/model-performance')
  return data
}

export async function fetchDataSourceStatus() {
  const { data } = await client.get('/data-sources/status')
  return data
}

export async function triggerFirmsSync() {
  try {
    const { data } = await firmsSyncClient.post('/data-sources/firms/sync')
    return data
  } catch (err) {
    if (err.code === 'ECONNABORTED' || (err.message && err.message.toLowerCase().includes('timeout'))) {
      throw new Error('FIRMS sync timed out. Existing data is unchanged.')
    }
    const detail = err.response?.data?.detail || err.message
    throw new Error(detail || 'Sync request failed.')
  }
}

export async function fetchLabelingStats(source = 'nasa_firms') {
  const { data } = await client.get('/ml/labeling/stats', { params: { source } })
  return data
}

export async function fetchTrainingEligibility() {
  const { data } = await client.get('/ml/labeling/training-eligibility')
  return data
}

/**
 * READ-ONLY export of REAL NASA FIRMS hotspot records.
 * Returns a flat list of hotspots (id + full metadata) for analyst
 * selection (e.g. picking 280 IDs for human verification).
 * No database records are created, modified, or deleted.
 */
export async function exportNasaFirmsHotspots(format = 'csv') {
  const { data } = await client.get('/hotspots/export', {
    params: { format },
    responseType: format === 'json' ? 'json' : 'text',
  })
  return data
}

/**
 * READ-ONLY INDUSTRIAL_FIRE batch-review queue.
 * Returns the top candidates sorted by industrial_fire_candidate_score
 * descending. Never auto-labels; review_required is True for every row.
 */
export async function fetchIndustrialFireCandidates(params = {}) {
  const { data } = await client.get('/hotspots/industrial-fire/candidates', { params })
  return data
}

/**
 * READ-ONLY progress summary for the INDUSTRIAL_FIRE batch review.
 */
export async function fetchIndustrialFireReviewProgress(params = {}) {
  const { data } = await client.get('/hotspots/industrial-fire/review/progress', { params })
  return data
}

// --- Demo scenario management ---
// These endpoints create/reset DEMO-only data (source='demo'). They NEVER
// touch nasa_firms records and NEVER modify verification decisions.

export async function createDemoScenario(days = 30) {
  const { data } = await client.post('/demo/scenario', null, { params: { days } })
  return data
}

export async function resetDemoData() {
  const { data } = await client.delete('/demo/data', { params: { confirm: 'DELETE_DEMO_DATA' } })
  return data
}

export async function fetchDemoStatus() {
  const { data } = await client.get('/demo/status')
  return data
}
