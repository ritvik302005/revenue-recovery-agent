import { useEffect, useState } from 'react'

const EVENTS = [
  { label: 'Payment event', value: 'Bank timeout', tone: 'danger', icon: '↯' },
  { label: 'Recovery policy', value: 'Retry in 15 min', tone: 'accent', icon: '◌' },
  { label: 'Guardrail', value: 'Within retry budget', tone: 'safe', icon: '✓' },
]

export default function HeroTransactionVisual() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => setActive((value) => (value + 1) % EVENTS.length), 2200)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="recovery-case" aria-label="Recovery case summary">
      <div className="recovery-case-glow" />
      <div className="recovery-case-topline">
        <span className="recovery-case-kicker">LIVE RECOVERY CASE</span>
        <span className="recovery-case-status"><i /> Monitoring</span>
      </div>
      <div className="recovery-case-amount">
        <span>Amount at risk</span><strong>₹2,499.00</strong><small>order_RP48…917</small>
      </div>
      <div className="recovery-case-events">
        {EVENTS.map((event, index) => (
          <button className={`recovery-case-event recovery-case-event-${event.tone} ${active === index ? 'is-active' : ''}`} key={event.label} onMouseEnter={() => setActive(index)} onFocus={() => setActive(index)} onClick={() => setActive(index)}>
            <span className="recovery-case-event-icon">{event.icon}</span>
            <span><small>{event.label}</small><strong>{event.value}</strong></span>
            <span className="recovery-case-event-state">{active === index ? 'now' : 'logged'}</span>
          </button>
        ))}
      </div>
      <div className="recovery-case-footer">
        <div><span>Confidence</span><strong>94%</strong></div>
        <div><span>Next review</span><strong>14:30 IST</strong></div>
        <div className="recovery-case-footer-safe"><span>Auto-charge</span><strong>Blocked</strong></div>
      </div>
    </div>
  )
}
