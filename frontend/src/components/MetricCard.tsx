type MetricCardProps = {
  label: string
  value: string
  subtext: string
}

export default function MetricCard({ label, value, subtext }: MetricCardProps) {
  return (
    <article className="metric-card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      <p className="metric-subtext">{subtext}</p>
    </article>
  )
}
