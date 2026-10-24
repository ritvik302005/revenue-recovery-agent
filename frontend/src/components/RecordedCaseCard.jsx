import { humanize, formatINR, parseTimestamp } from '../hooks/useShowcaseCase.js'

// One real recorded case: every value comes from /api/showcase/case.
// No placeholder IDs, scores or times — if there is no case, it says so.
export default function RecordedCaseCard({ showcase, onEnterDemo }) {
  const { status, data, error } = showcase

  if (status === 'loading') {
    return <CaseShell><p className="recovery-case-note">Loading the recorded case…</p></CaseShell>
  }
  if (status === 'error') {
    return (
      <CaseShell>
        <p className="recovery-case-note">Couldn't reach the backend to load a recorded case ({error}).</p>
      </CaseShell>
    )
  }
  if (data.kind === 'none') {
    return (
      <CaseShell>
        <p className="recovery-case-note">
          No completed case yet. Complete the live demo with Razorpay Test Mode (or run a batch
          evaluation) and the recorded case appears here automatically.
        </p>
        {onEnterDemo && (
          <button className="run-btn" onClick={onEnterDemo} style={{ marginTop: 14 }}>
            Run the live demo →
          </button>
        )}
      </CaseShell>
    )
  }

  const live = data.kind === 'live_demo'
  const recorded = data.recorded_at
    ? parseTimestamp(data.recorded_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST'
    : '—'

  return (
    <CaseShell badge={live ? 'Razorpay Test Mode · real' : 'Batch record · simulated outcome'} live={live}>
      <div className="recovery-case-amount">
        <span>Amount</span>
        <strong>{formatINR(data.amount)}</strong>
        <small>{data.order_id}</small>
      </div>
      <div className="recovery-case-events">
        <CaseRow tone="danger" label="Failure" value={humanize(data.failure_reason)} detail={data.raw_error_code} />
        <CaseRow tone="accent" label="Agent action (rule-based)" value={humanize(data.action)} />
        <CaseRow tone="safe" label="Safety gate" value={data.safety_check_passed ? 'Passed' : 'Blocked'} />
      </div>
      <div className="recovery-case-footer">
        <div>
          <span>Outcome</span>
          <strong>{humanize(data.outcome)}{data.outcome_is_simulated ? ' (simulated)' : ''}</strong>
        </div>
        <div><span>Attempts</span><strong>{data.attempts}</strong></div>
        <div><span>Recorded</span><strong>{recorded}</strong></div>
      </div>
      <p className="recovery-case-note">
        {live
          ? 'From a completed Razorpay Test Mode demo: real order, real failure, real recovery attempt.'
          : 'From the latest batch run: the failure is a documented Razorpay code assigned synthetically, and the outcome comes from the simulation model.'}
      </p>
    </CaseShell>
  )
}

function CaseShell({ badge, live, children }) {
  return (
    <div className="recovery-case" aria-label="Recorded recovery case">
      <div className="recovery-case-glow" />
      <div className="recovery-case-topline">
        <span className="recovery-case-kicker">RECORDED CASE</span>
        {badge && <span className={`recovery-case-status ${live ? '' : 'is-simulated'}`}><i /> {badge}</span>}
      </div>
      {children}
    </div>
  )
}

function CaseRow({ tone, label, value, detail }) {
  return (
    <div className={`recovery-case-event recovery-case-event-${tone} is-static`}>
      <span><small>{label}</small><strong>{value}</strong>{detail && <small><code>{detail}</code></small>}</span>
    </div>
  )
}
