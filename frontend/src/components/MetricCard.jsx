export default function MetricCard({ label, value, tone = 'neutral' }) {
  return (
    <div className={`metric metric--${tone}`}>
      <span className="metric__value">{value}</span>
      <span className="metric__label">{label}</span>
    </div>
  )
}
