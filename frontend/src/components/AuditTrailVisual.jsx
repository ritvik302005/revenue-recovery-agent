import { useEffect, useState } from 'react'
import { humanize, parseTimestamp } from '../hooks/useShowcaseCase.js'

const TONES = { classify: 'danger', select_action: 'gold', replan: 'gold', safety_check: 'real', execute: 'default' }

// The recorded case's real audit trail, with times relative to its first
// entry. Rows reveal once; nothing loops or pretends to be live.
export default function AuditTrailVisual({ showcase }) {
  const { status, data } = showcase
  const entries = status === 'ready' && data.kind !== 'none' ? data.audit_trail : []
  const [visibleCount, setVisibleCount] = useState(0)

  useEffect(() => {
    if (visibleCount >= entries.length) return
    const timer = setTimeout(() => setVisibleCount((count) => count + 1), 450)
    return () => clearTimeout(timer)
  }, [visibleCount, entries.length])

  if (!entries.length) {
    return (
      <div className="audit-trail-visual audit-trail-ledger">
        <div className="audit-trail-header"><span><i className="audit-trail-header-dot" />CASE LEDGER</span></div>
        <p className="recovery-case-note">
          {status === 'loading'
            ? 'Loading the recorded audit trail…'
            : 'No recorded case yet. Once a live demo (or batch run) completes, its full audit trail appears here.'}
        </p>
      </div>
    )
  }

  const start = parseTimestamp(entries[0].timestamp).getTime()
  const offset = (entry) => `+${Math.round((parseTimestamp(entry.timestamp).getTime() - start) / 1000)}s`

  return (
    <div className="audit-trail-visual audit-trail-ledger">
      <div className="audit-trail-header">
        <span><i className="audit-trail-header-dot" />CASE LEDGER</span>
        <small>CASE {data.payment_id}</small>
      </div>
      <div className="audit-trail-decision">
        <span>Final outcome</span>
        <strong>{humanize(data.outcome)}</strong>
        <em>{data.outcome_is_simulated ? 'Simulated outcome' : 'Verified by Razorpay'}</em>
      </div>
      <div className="audit-trail-list">
        {entries.map((entry, index) => {
          const shown = index < visibleCount
          return (
            <div key={index} className={`audit-trail-row tone-${TONES[entry.step] || 'default'} ${shown ? 'audit-trail-row-shown' : ''} ${index === visibleCount - 1 ? 'audit-trail-row-current' : ''}`}>
              <div className="audit-trail-time">{shown ? offset(entry) : '+—s'}</div>
              <div className="audit-trail-connector"><span className="audit-trail-dot" />{index < entries.length - 1 && <span className="audit-trail-line" />}</div>
              <div className="audit-trail-label"><strong>{humanize(entry.step)}</strong><small>{entry.detail}</small></div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
