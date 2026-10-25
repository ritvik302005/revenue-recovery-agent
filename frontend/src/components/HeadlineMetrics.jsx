import { useCountUp } from '../hooks/useCountUp.js'
import { useEvaluation } from '../hooks/useEvaluation.js'

const fmtPct = (n) => `${n.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`

// Every number comes from the published evaluation; nothing is hardcoded.
function metricsFrom(evaluation) {
  const rate = evaluation.recovery_rate_pct
  return [
    {
      value: evaluation.payments_simulated,
      decimals: 0,
      label: 'Failed payments simulated',
      sublabel: `${evaluation.seeds.count} seeded batches of ${evaluation.batch_size}`,
    },
    {
      value: rate.mean,
      decimals: 1,
      suffix: '%',
      label: 'Simulated recovery rate',
      sublabel: `Mean; 95% CI ${fmtPct(rate.mean_ci95[0])}–${fmtPct(rate.mean_ci95[1])}`,
    },
    {
      value: evaluation.safety_gate.fraud_holds,
      decimals: 0,
      label: 'Fraud holds',
      sublabel: 'Risk-check declines, never retried',
    },
    {
      value: evaluation.safety_gate.max_attempt_stops,
      decimals: 0,
      label: 'Retries stopped',
      sublabel: `Safety gate at ${evaluation.max_attempts} attempts`,
    },
  ]
}

function HeadlineMetric({ metric }) {
  const animated = useCountUp(metric.value, 1000)
  return (
    <div className="headline-metric">
      <div className="headline-metric-value">
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
  const { status, data } = useEvaluation()

  if (status === 'loading') {
    return <p className="headline-metrics-note">Loading the batch evaluation…</p>
  }
  if (status === 'error') {
    return (
      <p className="headline-metrics-note">
        The batch evaluation isn't available right now (backend unreachable,
        or <code>evaluate_batch.py</code> hasn't been run).
      </p>
    )
  }

  return (
    <>
      <div className="headline-metrics">
        {metricsFrom(data).map((m) => (
          <HeadlineMetric key={m.label} metric={m} />
        ))}
      </div>
      <p className="headline-metrics-note">
        From {data.seeds.count} seeded batch runs (seeds {data.seeds.first}–{data.seeds.last});
        a single batch lands between {fmtPct(data.recovery_rate_pct.single_run_range95[0])} and{' '}
        {fmtPct(data.recovery_rate_pct.single_run_range95[1])} in 95% of runs.
        This is a simulation: failure reasons are documented Razorpay codes
        assigned by a generator, and outcomes come from an illustrative
        probability table. It describes the agent's policy, not money
        actually recovered — see real vs simulated below.
      </p>
    </>
  )
}
