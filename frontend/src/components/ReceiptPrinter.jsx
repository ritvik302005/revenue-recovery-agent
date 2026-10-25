import { useEffect, useState } from 'react'
import { humanize, formatINR, parseTimestamp } from '../hooks/useShowcaseCase.js'
import { usePointerTilt } from '../hooks/usePointerTilt.js'

// The recorded case, printed as a receipt. Every value comes from
// /api/showcase/case; with no case it prints that there is none.
// The stamp's ink is the provenance (see DESIGN.md §2).
export function stampFor(data) {
  if (data.kind !== 'live_demo') return { tone: 'sim', text: 'Simulated' }
  if (data.outcome === 'recovered') return { tone: 'real', text: 'Captured · verified' }
  if (data.outcome === 'held_no_action') return { tone: 'danger', text: 'Held' }
  if (data.stage === 'escalated') return { tone: 'ink', text: 'Escalated to support' }
  return { tone: 'danger', text: 'Not recovered' }
}

function recordedAt(iso) {
  if (!iso) return '—'
  return parseTimestamp(iso)
    .toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
    .toUpperCase() + ' IST'
}

const PRINT_MS = 1500   // feed + stamp, matches the CSS timings

export default function ReceiptPrinter({ showcase, onEnterDemo }) {
  const tiltRef = usePointerTilt()
  const { status, data, error } = showcase
  const [reprints, setReprints] = useState(0)
  const [printing, setPrinting] = useState(false)
  // Re-printing happens when a different case arrives, or on Reprint.
  const caseKey = status === 'ready' && data.kind !== 'none'
    ? `${data.kind}:${data.payment_id}:${data.recorded_at}`
    : `${status}:${data?.kind ?? ''}`
  const printKey = `${caseKey}:${reprints}`

  useEffect(() => {
    if (status === 'loading') return
    setPrinting(true)
    const t = setTimeout(() => setPrinting(false), PRINT_MS)
    return () => clearTimeout(t)
  }, [printKey, status])

  return (
    <div className="printer-stage" ref={tiltRef}>
      <div className="printer-rig">
        <div className="printer" aria-hidden="true">
          <div className="printer-top" />
          <div className="printer-front">
            <span className="printer-slot" />
            <span className="printer-brand">recover · thermal</span>
            <span className={`printer-led ${status === 'error' ? 'is-off' : printing || status === 'loading' ? 'is-busy' : ''}`} />
          </div>
        </div>
        <div className="receipt-feed">
          {status !== 'loading' && (
            <div className="receipt-sway" key={printKey}>
              <article className="receipt" aria-label="Recorded recovery case">
                <ReceiptBody status={status} data={data} error={error} onEnterDemo={onEnterDemo} />
                <div className="receipt-tear" aria-hidden="true" />
              </article>
            </div>
          )}
        </div>
        <div className="printer-floor" aria-hidden="true" />
      </div>
      {status === 'loading' && <p className="printer-status">Loading the recorded case…</p>}
      {status === 'ready' && data.kind !== 'none' && (
        <button type="button" className="reprint" onClick={() => setReprints((n) => n + 1)} disabled={printing}>
          Reprint
        </button>
      )}
    </div>
  )
}

function ReceiptBody({ status, data, error, onEnterDemo }) {
  if (status === 'error') {
    return (
      <>
        <ReceiptHead title="No connection" />
        <p className="receipt-text">Couldn't reach the backend to load a recorded case ({error}).</p>
      </>
    )
  }
  if (data.kind === 'none') {
    return (
      <>
        <ReceiptHead title="No completed case yet" />
        <p className="receipt-text">
          Run the live demo with Razorpay Test Mode and its case prints here,
          whether or not the recovery succeeds.
        </p>
        {onEnterDemo && <button className="btn btn-ink" onClick={onEnterDemo}>Run the live demo</button>}
        <div className="stamp stamp-empty" aria-hidden="true">No case yet</div>
      </>
    )
  }

  const live = data.kind === 'live_demo'
  const stamp = stampFor(data)
  return (
    <>
      <ReceiptHead title="Recorded case" meta={recordedAt(data.recorded_at)} />
      <dl className="receipt-lines">
        <Line label="Amount" value={formatINR(data.amount)} leader strong />
        <Line label="Order" value={data.order_id} id />
        <Line label="Payment" value={data.payment_id} id />
      </dl>
      <hr className="receipt-rule" />
      <dl className="receipt-lines">
        <Line label="Failure" value={humanize(data.failure_reason)} sub={data.raw_error_code} />
        <Line label="Action" value={humanize(data.action)} sub="from the fixed policy" />
        <Line label="Safety gate" value={data.safety_check_passed ? 'passed' : 'blocked'} />
        <Line label="Attempts" value={`${data.attempts} of 3`} />
        <Line label="Outcome" value={humanize(data.outcome)} strong />
      </dl>
      <div className={`stamp stamp-${stamp.tone}`} role="img" aria-label={`Stamp: ${stamp.text}`}>{stamp.text}</div>
      <p className="receipt-foot">
        {live
          ? 'Razorpay Test Mode: real order, real failure, real recovery attempt.'
          : 'Batch record: the failure is a documented Razorpay code assigned by a generator; the outcome is simulated.'}
      </p>
    </>
  )
}

function ReceiptHead({ title, meta }) {
  return (
    <header className="receipt-head">
      <span className="receipt-title">{title}</span>
      {meta && <span className="receipt-meta">{meta}</span>}
    </header>
  )
}

function Line({ label, value, sub, leader, strong, id }) {
  return (
    <div className={`receipt-line ${leader ? 'has-leader' : ''}`}>
      <dt>{label}</dt>
      {leader && <span className="receipt-leader" aria-hidden="true" />}
      <dd className={`${strong ? 'is-strong' : ''} ${id ? 'is-id' : ''}`}>
        {value}
        {sub && <small>{sub}</small>}
      </dd>
    </div>
  )
}
