import { useEffect, useState } from 'react'

const EVENTS = [
  { time: '+0s', label: 'Payment failure received', detail: 'Gateway: bank timeout', tone: 'danger' },
  { time: '+1s', label: 'Failure classified', detail: 'Temporary issuer / network issue', tone: 'gold' },
  { time: '+2s', label: 'Recovery policy selected', detail: 'Retry same method after 15 min', tone: 'gold' },
  { time: '+2s', label: 'Safety gate passed', detail: 'Attempt 1 of 3 · no fraud signal', tone: 'real' },
  { time: '+3s', label: 'Recovery scheduled', detail: 'Awaiting verified payment status', tone: 'default' },
]

export default function AuditTrailVisual() {
  const [visibleCount, setVisibleCount] = useState(0)
  useEffect(() => {
    const timer = setTimeout(() => setVisibleCount((count) => count >= EVENTS.length ? 0 : count + 1), visibleCount >= EVENTS.length ? 2600 : 700)
    return () => clearTimeout(timer)
  }, [visibleCount])

  return (
    <div className="audit-trail-visual audit-trail-ledger">
      <div className="audit-trail-header"><span><i className="audit-trail-header-dot" />CASE LEDGER</span><small>CASE PAY_2C19</small></div>
      <div className="audit-trail-decision"><span>Current decision</span><strong>Retry after 15 min</strong><em>Safety-approved</em></div>
      <div className="audit-trail-list">
        {EVENTS.map((event, index) => {
          const shown = index < visibleCount
          return <div key={event.label} className={`audit-trail-row tone-${event.tone} ${shown ? 'audit-trail-row-shown' : ''} ${index === visibleCount - 1 ? 'audit-trail-row-current' : ''}`}>
            <div className="audit-trail-time">{shown ? event.time : '+—s'}</div><div className="audit-trail-connector"><span className="audit-trail-dot" />{index < EVENTS.length - 1 && <span className="audit-trail-line" />}</div>
            <div className="audit-trail-label"><strong>{event.label}</strong><small>{event.detail}</small></div>
          </div>
        })}
      </div>
    </div>
  )
}
