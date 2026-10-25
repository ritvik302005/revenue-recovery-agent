import { useEffect, useRef, useState } from 'react'
import { formatINR, humanize } from '../hooks/useShowcaseCase.js'
import { stampFor } from './ReceiptPrinter.jsx'

const STEPS = [
  { title: 'Detect', eyebrow: 'Signal',
    body: 'A Razorpay payment fails: a real Checkout failure in the live demo, or a synthetic record in the batch. No failure, no case.',
    boundary: 'Only a payment Razorpay reports as failed opens a case.' },
  { title: 'Diagnose', eyebrow: 'Evidence',
    body: 'The payment’s error_reason from Razorpay is mapped to a documented failure reason.',
    boundary: 'Unknown or vague errors are escalated, never guessed.' },
  { title: 'Decide', eyebrow: 'Policy',
    body: 'A fixed table picks the recovery action for that reason: retry, wait, suggest another method, remind, or hand to support.',
    boundary: 'No matching rule means escalation, never improvisation.' },
  { title: 'Safety gate', eyebrow: 'Control',
    body: 'Hard checks run before every action: fraud signals and the three-attempt budget.',
    boundary: 'A fraud flag or a spent budget stops the case outright.' },
  { title: 'Act', eyebrow: 'Execution',
    body: 'The decision is carried out: a recovery link for the customer (now, after a delay, or with the failed method hidden), a reminder, or a support case.',
    boundary: 'A failed or unpaid link escalates to the next action.' },
  { title: 'Verify', eyebrow: 'Proof',
    body: 'A recovery counts only when Razorpay reports the customer’s payment captured, confirmed by Checkout’s signature or a signed webhook.',
    boundary: 'Anything else stays unresolved; it is never called recovered.' },
]

// One printed line per step, all from the recorded case (never invented).
export function linesFor(data) {
  if (!data || data.kind === 'none') return null
  const trail = data.audit_trail || []
  const find = (step) => trail.find((e) => e.step === step)
  const firstAction = find('select_action')?.detail.match(/'([a-z_]+)'/)?.[1] || data.action
  const gate = find('safety_check')
  const execute = find('execute')
  const errorCode = (data.raw_error_code || '').split(' / ')[1]
  return [
    { label: 'Failed', value: `${data.payment_id} · ${formatINR(data.amount)}` },
    { label: 'Diagnosed', value: `${errorCode || 'error'} → ${humanize(data.failure_reason)}` },
    { label: 'Decided', value: humanize(firstAction) },
    { label: 'Gate', value: gate && !gate.detail.startsWith('BLOCKED') ? 'passed' : 'blocked' },
    { label: 'Executed', value: execute?.data?.plan?.summary || (execute ? humanize(firstAction) : 'nothing (held)') },
    { label: 'Outcome', value: `${humanize(data.outcome)} · ${data.attempts} of 3 attempts` },
  ]
}

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/**
 * The agent's six steps, told by scrolling: as each step comes into view,
 * the recorded case's matching line prints on the receipt beside it, and
 * the stamp lands at the end. With reduced motion everything is printed.
 */
export default function ScrollStory({ showcase }) {
  const reduced = prefersReducedMotion()
  const [printed, setPrinted] = useState(reduced ? STEPS.length - 1 : -1)
  const [current, setCurrent] = useState(0)
  const stepRefs = useRef([])

  useEffect(() => {
    if (reduced || typeof IntersectionObserver === 'undefined') { setPrinted(STEPS.length - 1); return }
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue
        const i = Number(e.target.dataset.index)
        setCurrent(i)
        setPrinted((p) => Math.max(p, i))
      }
    }, { rootMargin: '-35% 0px -50% 0px' })
    stepRefs.current.forEach((el) => el && io.observe(el))
    return () => io.disconnect()
  }, [reduced])

  const data = showcase.status === 'ready' ? showcase.data : null
  const lines = linesFor(data)
  const stamp = lines ? stampFor(data) : null

  return (
    <div className="story">
      <div className="story-tape-col">
        <div className="story-tape" aria-label="The recorded case, printed step by step">
          <div className="story-tape-head">
            <span>{lines ? 'Recorded case' : 'No recorded case yet'}</span>
            {lines && <span>{data.kind === 'live_demo' ? 'Live demo' : 'Batch record'}</span>}
          </div>
          {lines ? (
            <ol className="story-lines">
              {lines.map((l, i) => (
                <li key={l.label} className={`story-line ${i <= printed ? 'is-printed' : ''} ${i === current ? 'is-current' : ''}`}>
                  <span className="story-line-label">{l.label}</span>
                  <span className="story-line-value">{l.value}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="story-empty">Run the live demo or a batch and its case prints here, line by line, as you read the steps.</p>
          )}
          {lines && (
            <div className={`stamp stamp-${stamp.tone} story-stamp ${printed >= STEPS.length - 1 ? 'is-down' : ''}`} aria-hidden="true">
              {stamp.text}
            </div>
          )}
          <div className="receipt-tear" aria-hidden="true" />
        </div>
      </div>

      <ol className="story-steps">
        {STEPS.map((s, i) => (
          <li key={s.title} ref={(el) => { stepRefs.current[i] = el }} data-index={i}
              className={`story-step ${i === current ? 'is-current' : ''}`}>
            <span className="story-num">{String(i + 1).padStart(2, '0')} · {s.eyebrow}</span>
            <h3 className="story-title">{s.title}</h3>
            <p>{s.body}</p>
            <p className="story-boundary"><span>Hard boundary</span>{s.boundary}</p>
            {lines && <p className="story-inline-line"><span>{lines[i].label}</span> {lines[i].value}</p>}
          </li>
        ))}
      </ol>
    </div>
  )
}
