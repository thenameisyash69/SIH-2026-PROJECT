import { useEffect, useState } from 'react'
import HeatMap from './components/HeatMap'
import AlertList from './components/AlertList'
import MetricCard from './components/MetricCard'
import Chatbot from './components/Chatbot'
import DetailPanel from './components/DetailPanel'
import ImpactStats from './components/ImpactStats'
import FacilitiesPage from './components/FacilitiesPage'
import ModelPerformancePage from './components/ModelPerformancePage'
import LabelingPage from './components/LabelingPage'
import { fetchHotspots, fetchAlerts, fetchStats, fetchDataSourceStatus, triggerFirmsSync } from './api'
import { demoHotspots, demoAlerts } from './demoData'

const SIDEBAR_TABS = ['Alerts', 'Details', 'Ask Kavach']
const VIEWS = [
  { id: 'command_center', label: 'Command Center' },
  { id: 'labeling', label: 'Analyst Queue' },
  { id: 'facilities', label: 'Facility Intelligence' },
  { id: 'model_performance', label: 'Model Performance' },
]
const SOURCE_FILTERS = ['REAL NASA', 'DEMO', 'ALL']

export default function App() {
  const [view, setView] = useState('command_center')
  const [hotspots, setHotspots] = useState(demoHotspots)
  const [totalHotspots, setTotalHotspots] = useState(0)
  const [alerts, setAlerts] = useState(demoAlerts)
  const [stats, setStats] = useState(null)
  const [firmsStatus, setFirmsStatus] = useState(null)
  const [usingDemo, setUsingDemo] = useState(true)
  const [selectedHotspot, setSelectedHotspot] = useState(null)
  const [activeTab, setActiveTab] = useState('Alerts')
  const [sourceFilter, setSourceFilter] = useState('ALL')
  const [syncing, setSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState(null)

  async function load() {
    try {
      const [h, a, s, sources] = await Promise.all([
        fetchHotspots({ india_scope: sourceFilter === 'REAL NASA' }),
        fetchAlerts(),
        fetchStats(),
        fetchDataSourceStatus(),
      ])
      setHotspots(h.hotspots || h)
      setTotalHotspots(h.total || (h.hotspots || h).length)
      setAlerts(a)
      setStats(s)
      const firms = sources.find((src) => src.name === 'NASA FIRMS')
      setFirmsStatus(firms || null)
      setUsingDemo(false)
      if (firms && firms.total_real_observations > 0 && sourceFilter === 'ALL') {
        setSourceFilter('REAL NASA')
      }
    } catch {
      setUsingDemo(true)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(load, 60000)
    return () => clearInterval(interval)
  }, [sourceFilter])

  async function handleSync() {
    setSyncing(true)
    setSyncMessage(null)
    try {
      const result = await triggerFirmsSync()
      if (result.success) {
        setSyncMessage(`Sync succeeded — fetched ${result.fetched}, inserted ${result.inserted}, ${result.duplicates_skipped} duplicates skipped.`)
        await load()
      } else {
        setSyncMessage(`Sync failed: ${result.error}`)
      }
    } catch (err) {
      setSyncMessage(err.message || 'Could not reach the backend to trigger a sync.')
    } finally {
      setSyncing(false)
    }
  }

  function selectHotspotById(id) {
    const found = hotspots.find((h) => h.id === id)
    if (found) {
      setSelectedHotspot(found)
      setActiveTab('Details')
    }
  }

  function handleMapSelect(hotspot) {
    setSelectedHotspot(hotspot)
    setActiveTab('Details')
  }

  const filteredHotspots = hotspots.filter((h) => {
    if (sourceFilter === 'REAL NASA') return h.source === 'nasa_firms'
    if (sourceFilter === 'DEMO') return h.source === 'demo_synthetic'
    return true
  })

  const alertCount = filteredHotspots.filter((h) => h.is_anomaly).length
  const industrialCount = filteredHotspots.filter((h) => h.category.startsWith('industrial')).length

  // Honest status label — driven by the REAL backend-checked FIRMS status,
  // never inferred from "does the map currently show real dots."
  let firmsLabel = '◆ DEMO MODE — FIRMS not configured'
  let firmsTone = 'demo'
  if (firmsStatus) {
    if (firmsStatus.status && firmsStatus.status.startsWith('LIVE')) { firmsLabel = `🛰 LIVE — NASA FIRMS (${firmsStatus.total_real_observations} real obs.)`; firmsTone = 'real' }
    else if (firmsStatus.status && firmsStatus.status.startsWith('STALE')) { firmsLabel = `⚠ STALE — NASA FIRMS (last sync ${firmsStatus.minutes_since_last_success}m ago)`; firmsTone = 'stale' }
    else { firmsLabel = `◆ OFFLINE — NASA FIRMS`; firmsTone = 'demo' }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__mark">कवच</span>
          <div>
            <h1>KAVACH</h1>
            <p>Industrial Thermal Intelligence &amp; Early Warning</p>
          </div>
        </div>
        <div className="topbar__right">
          <span className={`mode-indicator mode-indicator--${firmsTone}`}>{firmsLabel}</span>
          <button className="btn-secondary" onClick={handleSync} disabled={syncing}>
            {syncing ? 'Syncing…' : 'Sync FIRMS now'}
          </button>
          {usingDemo && <span className="topbar__badge">backend offline — showing cached demo data</span>}
        </div>
      </header>
      {syncMessage && <div className="sync-message">{syncMessage}</div>}
      {firmsStatus && firmsStatus.last_error && !firmsStatus.status.startsWith('LIVE') && (
        <div className="sync-message sync-message--error">FIRMS: {firmsStatus.detail}</div>
      )}

      <nav className="view-switcher">
        {VIEWS.map((v) => (
          <button key={v.id} className={`view-switcher__btn ${view === v.id ? 'view-switcher__btn--active' : ''}`}
                  onClick={() => setView(v.id)}>
            {v.label}
          </button>
        ))}
      </nav>

      {view === 'command_center' && (
        <>
          <section className="metrics">
            <MetricCard label="Hotspots loaded" value={filteredHotspots.length} subtitle={`${totalHotspots} total match current filters`} />
            <MetricCard label="Industrial sources" value={industrialCount} tone="amber" />
            <MetricCard label="Active anomalies" value={alertCount} tone="red" />
          </section>

          {stats && (
            <section className="metrics metrics--impact">
              <ImpactStats stats={stats} />
            </section>
          )}

          <div className="source-filter">
            {SOURCE_FILTERS.map((f) => (
              <button key={f} className={`source-filter__btn ${sourceFilter === f ? 'source-filter__btn--active' : ''}`}
                      onClick={() => setSourceFilter(f)}>
                {f}
              </button>
            ))}
          </div>

          <main className="layout">
            <div className="layout__map">
              {filteredHotspots.length === 0 && sourceFilter === 'REAL NASA' ? (
                <div className="map-empty-state">
                  No live NASA FIRMS observations available for the selected region/time window.
                  Try "Sync FIRMS now" above, or switch to the DEMO / ALL filter.
                </div>
              ) : (
                <HeatMap hotspots={filteredHotspots} onSelect={handleMapSelect} />
              )}
            </div>
            <aside className="layout__side">
              <nav className="tabs">
                {SIDEBAR_TABS.map((tab) => (
                  <button
                    key={tab}
                    className={`tabs__btn ${activeTab === tab ? 'tabs__btn--active' : ''}`}
                    onClick={() => setActiveTab(tab)}
                  >
                    {tab}
                  </button>
                ))}
              </nav>

              <div className="tabs__panel">
                {activeTab === 'Alerts' && <AlertList alerts={alerts} onSelect={selectHotspotById} />}
                {activeTab === 'Details' && <DetailPanel hotspot={selectedHotspot} hotspots={filteredHotspots} deep={false} />}
                {activeTab === 'Ask Kavach' && <Chatbot />}
              </div>
            </aside>
          </main>
        </>
      )}

      {view === 'facilities' && (
        <main className="layout layout--single">
          <FacilitiesPage />
        </main>
      )}

      {view === 'model_performance' && (
        <main className="layout layout--single">
          <ModelPerformancePage />
        </main>
      )}

      {view === 'labeling' && (
        <main className="layout layout--single">
          <LabelingPage />
        </main>
      )}
    </div>
  )
}
