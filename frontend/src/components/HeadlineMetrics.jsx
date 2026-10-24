import { useCountUp } from '../hooks/useCountUp.js'

const METRICS = [
  {
    value: 60,
    decimals: 0,
    suffix: '',
    label: 'Cases evaluated',
    sublabel: 'Controlled batch',
  },
  {
    value: 76.7,
    decimals: 1,
    suffix: '%',
    label: 'Simulated recovery rate',
    sublabel: 'Modelled, not real money',
  },
  {
    value: 1.81,
    decimals: 2,
    prefix: '\u20b9',
    suffix: 'L',
    label: 'Revenue at risk',
    sublabel: 'Batch total, simulated',
  },
  {
    value: 100,
    decimals: 0,
    suffix: '%',
    label: 'Audit coverage',
    sublabel: 'Every decision logged',
  },
]

function HeadlineMetric({ metric }) {
  const animated = useCountUp(metric.value, 1000)
  return (
    <div className="headline-metric">
      <div className="headline-metric-value">
        {metric.prefix || ''}
        {animated.toLocaleString('en-IN', {
          minimumFractionDigits: metric.decimals,
          maximumFractionDigits: metric.decimals,
        })}
        {metric.suffix || ''}
      </div>
      <div className="headline-metric-label">{metric.label}</div>
      <div className="headline-metric-sublabel">{metric.sublabel}</div>
    </div>
  )
}

export default function HeadlineMetrics() {
  return (
    <div className="headline-metrics">
      {METRICS.map((m) => (
        <HeadlineMetric key={m.label} metric={m} />
      ))}
    </div>
  )
}
