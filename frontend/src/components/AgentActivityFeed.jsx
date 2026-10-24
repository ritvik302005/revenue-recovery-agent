import { useEffect, useState } from 'react'

const CASES = [
  { id: 'PAY_8F42', reason: 'Card declined', action: 'Offer alternate payment', gate: 'Retry allowed · 1 of 3' },
  { id: 'PAY_2C19', reason: 'Bank timeout', action: 'Retry after 15 min', gate: 'Retry allowed · 1 of 3' },
  { id: 'PAY_5A77', reason: 'Insufficient funds', action: 'Send secure payment link', gate: 'Customer action required' },
]

export default function AgentActivityFeed() {
  const [caseIndex, setCaseIndex] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setCaseIndex((current) => (current + 1) % CASES.length), 4800)
    return () => window.clearInterval(timer)
  }, [])
  const current = CASES[caseIndex]

  return (
    <div className="agent-activity agent-activity-compact">
      <div className="agent-activity-header"><span className="agent-activity-dot" />LIVE CASE MONITOR <span className="agent-activity-cycle">{current.id}</span></div>
      <div className="agent-activity-summary"><strong>{current.reason}</strong><span>Gateway event received</span></div>
      <div className="agent-activity-steps">
        <div><span>01</span><p>Diagnosis <b>{current.reason}</b></p></div>
        <div><span>02</span><p>Policy <b>{current.action}</b></p></div>
        <div><span>03</span><p>Safety <b>{current.gate}</b></p></div>
      </div>
    </div>
  )
}
