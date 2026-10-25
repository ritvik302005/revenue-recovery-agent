import { useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../api.js'
import { humanize } from '../hooks/useShowcaseCase.js'

const METHOD_LABEL = { card: 'Card', upi: 'UPI', netbanking: 'Netbanking', wallet: 'Wallet' }

function stampFor(preview) {
  if (!preview.safety_check_passed) return { tone: 'danger', text: 'Held' }
  if (preview.plan.kind === 'support_case') return { tone: 'ink', text: 'Would open a case' }
  return { tone: 'ink', text: 'Would send a link' }
}

/**
 * Pick any documented Razorpay error and see what the agent decides and
 * does, printed as a slip. The backend runs the same rules the live demo
 * uses (GET /api/policy/preview); no payment is made and nothing is sent.
 */
export default function PolicyPlayground() {
  const [reasons, setReasons] = useState(null)
  const [reason, setReason] = useState('payment_timed_out')
  const [method, setMethod] = useState('card')
  const [preview, setPreview] = useState(null)
  const [printCount, setPrintCount] = useState(0)
  const [error, setError] = useState(null)

  useEffect(() => {
    apiFetch('/api/policy').then((d) => setReasons(d.reasons)).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    let cancelled = false
    apiFetch('/api/policy/preview', { params: { error_reason: reason, method } })
      .then((d) => { if (!cancelled) { setPreview(d); setPrintCount((n) => n + 1); setError(null) } })
      .catch((e) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [reason, method])

  // Group the codes by the category they map to.
  const groups = useMemo(() => {
    const byCategory = {}
    for (const r of reasons || []) (byCategory[r.category] ||= []).push(r.error_reason)
    return Object.entries(byCategory).sort(([a], [b]) => a.localeCompare(b))
  }, [reasons])

  return (
    <div className="policy">
      <form className="policy-controls" onSubmit={(e) => e.preventDefault()}>
        <label className="field field-wide">
          <span>Razorpay error_reason</span>
          <select className="input select" value={reason} onChange={(e) => setReason(e.target.value)} disabled={!reasons}>
            {!reasons && <option value={reason}>{reason}</option>}
            {groups.map(([category, codes]) => (
              <optgroup key={category} label={humanize(category)}>
                {codes.map((c) => <option key={c} value={c}>{c}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <fieldset className="segmented">
          <legend>The failed payment was made with</legend>
          {Object.entries(METHOD_LABEL).map(([value, label]) => (
            <label key={value} className={method === value ? 'is-on' : ''}>
              <input type="radio" name="method" value={value} checked={method === value}
                     onChange={() => setMethod(value)} />
              {label}
            </label>
          ))}
        </fieldset>
        <p className="policy-note">
          These are the agent’s real rules, the same code the live demo runs. Nothing is paid or sent:
          it shows what would happen on a first failure.
        </p>
        {error && <div className="alert" role="alert">{error}</div>}
      </form>

      <div className="policy-slip-wrap" aria-live="polite">
        {preview && (
          <article key={printCount} className="policy-slip" aria-label="The agent's decision">
            <header className="receipt-head">
              <span className="receipt-title">Decision slip</span>
              <span className="receipt-meta">Preview · {METHOD_LABEL[method]} payment</span>
            </header>
            <dl className="receipt-lines">
              <div className="receipt-line"><dt>Error</dt><dd className="is-id">{preview.error_reason}{!preview.documented && <small>not a documented code</small>}</dd></div>
              <div className="receipt-line"><dt>Reason</dt><dd>{humanize(preview.category)}</dd></div>
              <div className="receipt-line"><dt>Action</dt><dd className="is-strong">{humanize(preview.action)}</dd></div>
              <div className="receipt-line"><dt>Safety gate</dt><dd>{preview.safety_check_passed ? 'passed' : 'blocked: fraud signal, no contact'}</dd></div>
              {preview.plan && <div className="receipt-line"><dt>Executes</dt><dd>{preview.plan.summary}</dd></div>}
            </dl>
            {preview.customer_message && (
              <div className="policy-message">
                <span>Customer receives</span>
                <p>{preview.customer_message}</p>
              </div>
            )}
            {preview.plan?.kind === 'support_case' && <p className="receipt-foot">The customer is asked for nothing; support takes over.</p>}
            <div className={`stamp stamp-${stampFor(preview).tone}`} aria-hidden="true">{stampFor(preview).text}</div>
          </article>
        )}
      </div>
    </div>
  )
}
