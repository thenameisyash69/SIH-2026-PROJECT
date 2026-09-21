export default function MetricCard({ label, value, tone = 'neutral', subtitle = null }) {
  return (
    <div className={`metric metric--${tone}`}>
      <span className="metric__value">{value}</span>
      <span className="metric__label">{label}</span>
      {subtitle && <span className="metric__subtitle">{subtitle}</span>}
    </div>
  )
}
