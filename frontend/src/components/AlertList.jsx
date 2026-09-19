const SEVERITY_ICON = { high: '⛔', medium: '⚠', low: 'ℹ' }

export default function AlertList({ alerts, onSelect }) {
  if (!alerts.length) {
    return <p className="empty">No active alerts. All monitored facilities within normal range.</p>
  }
  return (
    <ul className="alert-list">
      {alerts.map((a) => (
        <li
          key={a.id}
          className={`alert-list__item alert-list__item--${a.severity}`}
          onClick={() => onSelect && onSelect(a.hotspot_id)}
          role="button"
          tabIndex={0}
        >
          <span className="alert-list__icon">{SEVERITY_ICON[a.severity] || 'ℹ'}</span>
          <div className="alert-list__body">
            <span className="alert-list__severity">{a.severity} severity</span>
            <p className="alert-list__message">{a.message}</p>
            <time className="alert-list__time popup__mono">
              {new Date(a.created_at).toLocaleString()}
            </time>
          </div>
        </li>
      ))}
    </ul>
  )
}
