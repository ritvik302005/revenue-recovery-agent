import { useEvaluation } from '../hooks/useEvaluation.js'

const fmtPct = (n) => `${n.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`
const fmtInt = (n) => n.toLocaleString('en-IN')

// The published evaluation as a statement: ledger rows with dotted
// leaders. Every number comes from GET /api/evaluation; nothing is hardcoded.
function rowsFrom(evaluation) {
  const rate = evaluation.recovery_rate_pct
  return [
    { label: 'Failed payments simulated', value: fmtInt(evaluation.payments_simulated),
      sub: `${evaluation.seeds.count} seeded batches of ${evaluation.batch_size}` },
    { label: 'Simulated recovery rate', value: fmtPct(rate.mean), tone: 'sim',
      sub: `Mean; 95% CI ${fmtPct(rate.mean_ci95[0])}–${fmtPct(rate.mean_ci95[1])}` },
    { label: 'Fraud holds', value: fmtInt(evaluation.safety_gate.fraud_holds), tone: 'danger',
      sub: 'Risk-check declines, never retried' },
    { label: 'Retries stopped', value: fmtInt(evaluation.safety_gate.max_attempt_stops), tone: 'danger',
      sub: `Safety gate at ${evaluation.max_attempts} attempts` },
  ]
}

export default function HeadlineMetrics() {
  const { status, data } = useEvaluation()

  if (status === 'loading') {
    return <p className="statement-note">Loading the batch evaluation…</p>
  }
  if (status === 'error') {
    return (
      <p className="statement-note">
        The batch evaluation isn't available right now (backend unreachable,
        or <code>evaluate_batch.py</code> hasn't been run).
      </p>
    )
  }

  return (
    <div className="statement">
      <div className="statement-head">
        <span>Batch evaluation · simulated</span>
        <span>Seeds {data.seeds.first}–{data.seeds.last}</span>
      </div>
      <dl className="statement-rows">
        {rowsFrom(data).map((row) => (
          <div className="statement-row" key={row.label}>
            <dt>
              {row.label}
              <small>{row.sub}</small>
            </dt>
            <span className="statement-leader" aria-hidden="true" />
            <dd className={row.tone ? `tone-${row.tone}` : ''}>{row.value}</dd>
          </div>
        ))}
      </dl>
      <p className="statement-note">
        From {data.seeds.count} seeded batch runs (seeds {data.seeds.first}–{data.seeds.last});
        a single batch lands between {fmtPct(data.recovery_rate_pct.single_run_range95[0])} and{' '}
        {fmtPct(data.recovery_rate_pct.single_run_range95[1])} in 95% of runs.
        This is a simulation: failure reasons are documented Razorpay codes
        assigned by a generator, and outcomes come from an illustrative
        probability table. It describes the agent's policy, not money
        actually recovered.
      </p>
    </div>
  )
}
