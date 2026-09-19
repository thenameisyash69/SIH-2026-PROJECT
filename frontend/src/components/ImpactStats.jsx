export default function ImpactStats({ stats }) {
  if (!stats) return null
  const real = stats.real_data
  const demo = stats.demo_data

  return (
    <div className="impact">
      <div className="impact__row">
        <div><strong>{stats.facilities_monitored}</strong><span>facilities monitored</span></div>
        <div><strong>{stats.states_covered}</strong><span>states covered</span></div>
        <div><strong>{stats.hotspots_classified_by_ml}</strong><span>classified by trained model</span></div>
      </div>
      <div className="impact__row impact__row--split">
        <div className="impact__source impact__source--real">
          <span className="impact__source-label">REAL — NASA FIRMS</span>
          <div><strong>{real.total_hotspots}</strong><span>NASA observations stored</span></div>
          <div><strong>{real.high_or_critical_risk}</strong><span>high/critical risk</span></div>
        </div>
        <div className="impact__source impact__source--demo">
          <span className="impact__source-label">DEMO — synthetic</span>
          <div><strong>{demo.total_hotspots}</strong><span>observations</span></div>
          <div><strong>{demo.high_or_critical_risk}</strong><span>high/critical risk</span></div>
        </div>
      </div>
    </div>
  )
}
