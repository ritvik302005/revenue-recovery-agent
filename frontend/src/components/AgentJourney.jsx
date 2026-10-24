import { useEffect, useState } from 'react'

const STAGES = [
  { num: '01', title: 'Detect', eyebrow: 'Signal', input: 'A Razorpay payment event — real Checkout failure in the live demo, a tagged record in the batch.', action: 'Opens a recovery case only when a payment does not succeed.', stop: 'No payment failure means no case and no downstream action.' },
  { num: '02', title: 'Diagnose', eyebrow: 'Evidence', input: 'The payment’s Razorpay error code and metadata.', action: 'Maps the raw error to a known, documented failure reason.', stop: 'Unknown errors are escalated rather than guessed.' },
  { num: '03', title: 'Decide', eyebrow: 'Policy', input: 'The diagnosed reason and a fixed strategy table.', action: 'Selects the allowed recovery option for that failure type.', stop: 'No matching policy means an escalation, never improvisation.' },
  { num: '04', title: 'Safety Gate', eyebrow: 'Control', input: 'Proposed action plus the payment’s attempt history.', action: 'Enforces hard checks before any recovery action is permitted.', stop: 'Fraud flags and exhausted retry budgets block the case outright.' },
  { num: '05', title: 'Act', eyebrow: 'Execution', input: 'Only a gate-approved action.', action: 'Runs the approved intervention or routes it to support.', stop: 'The escalation ceiling prevents endless retry loops.' },
  { num: '06', title: 'Verify', eyebrow: 'Proof', input: 'The final payment status from Razorpay’s API.', action: 'Counts recovery only when the payment status is captured.', stop: 'Any other status remains unresolved; it is never called recovered.' },
]

export default function AgentJourney() {
  const [active, setActive] = useState(0)
  const activeStage = STAGES[active]

  useEffect(() => {
    const timer = window.setInterval(() => setActive((current) => (current + 1) % STAGES.length), 2800)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <div className="journey journey-board">
      <div className="journey-board-head"><span>RECOVERY CONTROL BOARD</span><small>Choose a control to inspect its boundary</small></div>
      <div className="journey-board-grid">
        {STAGES.map((stage, index) => (
          <button key={stage.num} className={`journey-board-card ${active === index ? 'is-active' : ''}`} onMouseEnter={() => setActive(index)} onFocus={() => setActive(index)} onClick={() => setActive(index)}>
            <span className="journey-board-number">{stage.num}</span><span className="journey-board-eyebrow">{stage.eyebrow}</span><strong>{stage.title}</strong>
          </button>
        ))}
      </div>
      <div className="journey-detail journey-board-detail">
        <div className="journey-detail-title"><span>{activeStage.num}</span>{activeStage.title}</div>
        <div className="journey-detail-row"><div className="journey-detail-label">Evidence used</div><div className="journey-detail-text">{activeStage.input}</div></div>
        <div className="journey-detail-row"><div className="journey-detail-label">Control applied</div><div className="journey-detail-text">{activeStage.action}</div></div>
        <div className="journey-detail-row"><div className="journey-detail-label">Hard boundary</div><div className="journey-detail-text journey-detail-stop">{activeStage.stop}</div></div>
      </div>
    </div>
  )
}
