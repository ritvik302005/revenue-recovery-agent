import { useRef, useState } from 'react'

const STAGES = [
  { title: 'Detect', eyebrow: 'Signal', input: 'A Razorpay payment event: a real Checkout failure in the live demo, a synthetic record in the batch.', action: 'Opens a recovery case only when a payment does not succeed.', stop: 'No payment failure means no case and no downstream action.' },
  { title: 'Diagnose', eyebrow: 'Evidence', input: 'The payment’s Razorpay error code and metadata.', action: 'Maps the raw error to a known, documented failure reason.', stop: 'Unknown errors are escalated rather than guessed.' },
  { title: 'Decide', eyebrow: 'Policy', input: 'The diagnosed reason and a fixed strategy table.', action: 'Selects the allowed recovery option for that failure type.', stop: 'No matching policy means an escalation, never improvisation.' },
  { title: 'Safety gate', eyebrow: 'Control', input: 'Proposed action plus the payment’s attempt history.', action: 'Enforces hard checks before any recovery action is permitted.', stop: 'Fraud flags and exhausted retry budgets block the case outright.' },
  { title: 'Act', eyebrow: 'Execution', input: 'Only a gate-approved action.', action: 'Carries the decision out: sends the customer a recovery link (now, after a delay, or with the failed method hidden), a reminder, or opens a support case instead of asking for money.', stop: 'A failed or unpaid link escalates to the next action; after three attempts the gate holds the case.' },
  { title: 'Verify', eyebrow: 'Proof', input: 'The customer’s payment, as Razorpay reports it.', action: 'In the live demo, counts a recovery only when Razorpay reports the payment captured, confirmed by Checkout’s signature or a signed webhook. Batch outcomes are simulated.', stop: 'Any other status stays unresolved; it is never called recovered.' },
]

// The six controls in order (a real sequence, so they're numbered). A tab
// list: click, focus or arrow keys select one. No autoplay.
export default function AgentJourney() {
  const [active, setActive] = useState(0)
  const tabs = useRef([])
  const stage = STAGES[active]

  function onKeyDown(e) {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key]
    let next = step === undefined ? null : (active + step + STAGES.length) % STAGES.length
    if (e.key === 'Home') next = 0
    if (e.key === 'End') next = STAGES.length - 1
    if (next === null) return
    e.preventDefault()
    setActive(next)
    tabs.current[next]?.focus()
  }

  return (
    <div className="controls">
      <div className="controls-list" role="tablist" aria-label="Recovery controls" aria-orientation="vertical" onKeyDown={onKeyDown}>
        {STAGES.map((s, index) => (
          <button
            key={s.title}
            ref={(el) => { tabs.current[index] = el }}
            role="tab"
            id={`control-tab-${index}`}
            aria-selected={active === index}
            aria-controls="control-panel"
            tabIndex={active === index ? 0 : -1}
            className="control-tab"
            onClick={() => setActive(index)}
            onMouseEnter={() => setActive(index)}
          >
            <span className="control-num">{String(index + 1).padStart(2, '0')}</span>
            <span className="control-name">{s.title}</span>
            <span className="control-eyebrow">{s.eyebrow}</span>
          </button>
        ))}
      </div>
      <div className="control-panel" role="tabpanel" id="control-panel" aria-labelledby={`control-tab-${active}`}>
        <h3 className="control-panel-title"><span>{String(active + 1).padStart(2, '0')}</span>{stage.title}</h3>
        <dl className="control-facts">
          <div><dt>Evidence used</dt><dd>{stage.input}</dd></div>
          <div><dt>Control applied</dt><dd>{stage.action}</dd></div>
          <div className="is-stop"><dt>Hard boundary</dt><dd>{stage.stop}</dd></div>
        </dl>
      </div>
    </div>
  )
}
