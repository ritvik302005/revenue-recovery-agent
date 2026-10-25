import { humanize, parseTimestamp } from '../hooks/useShowcaseCase.js'
import { useReveal } from '../hooks/useReveal.js'
import { stampFor } from './ReceiptPrinter.jsx'

const TONES = { classify: 'danger', safety_check: 'real' }

// The recorded case's real audit trail, printed as a tape. Times are
// relative to the first entry. Lines print once, when the tape scrolls
// into view; nothing loops or pretends to be live.
export default function AuditTrailVisual({ showcase }) {
  const [ref, inView] = useReveal(0.1)
  const { status, data } = showcase
  const entries = status === 'ready' && data.kind !== 'none' ? data.audit_trail : []

  if (!entries.length) {
    return (
      <div className="tape" ref={ref}>
        <div className="tape-head"><span>Audit tape</span></div>
        <p className="tape-empty">
          {status === 'loading'
            ? 'Loading the recorded audit trail…'
            : 'No recorded case yet. When a live demo or a batch run completes, its full audit trail prints here.'}
        </p>
      </div>
    )
  }

  const start = parseTimestamp(entries[0].timestamp).getTime()
  const offset = (entry) => `+${((parseTimestamp(entry.timestamp).getTime() - start) / 1000).toFixed(2)}s`
  const stamp = stampFor(data)

  return (
    <div className={`tape ${inView ? 'is-printed' : ''}`} ref={ref}>
      <div className="tape-head">
        <span>Audit tape</span>
        <span className="tape-case">{data.payment_id}</span>
      </div>
      <ol className="tape-lines">
        {entries.map((entry, index) => (
          <li key={index} className={`tape-line is-${TONES[entry.step] || 'plain'}`} style={{ '--i': index }}>
            <span className="tape-time">{offset(entry)}</span>
            <span className="tape-step">{humanize(entry.step)}</span>
            <span className="tape-detail">{entry.detail}</span>
          </li>
        ))}
      </ol>
      <div className="tape-foot">
        <span>End of tape · outcome: {humanize(data.outcome)}</span>
        <span className={`tape-verdict tone-${stamp.tone}`}>
          {data.outcome_is_simulated ? 'Simulated outcome' : 'Reported by Razorpay'}
        </span>
      </div>
    </div>
  )
}
