import { useEffect, useState } from 'react'

const STAGES = ['failed', 'diagnosing', 'selected', 'scheduled']

const CONTENT = {
  failed: {
    statusLabel: 'FAILED',
    statusTone: 'danger',
    diagnosis: 'Awaiting gateway evidence',
    gate: null,
    action: '—',
  },
  diagnosing: {
    statusLabel: 'DIAGNOSING',
    statusTone: 'simulated',
    diagnosis: 'Card declined by issuer',
    gate: null,
    action: '—',
  },
  selected: {
    statusLabel: 'RECOVERY SELECTED',
    statusTone: 'gold',
    diagnosis: 'Card declined by issuer',
    gate: 'passed',
    action: 'Offer alternate payment method',
  },
  scheduled: {
    statusLabel: 'FOLLOW-UP SCHEDULED',
    statusTone: 'real',
    diagnosis: 'Card declined by issuer',
    gate: 'passed',
    action: 'Offer alternate payment method',
  },
}

const STAGE_DURATION_MS = 1900

export default function RecoveryEventCard() {
  const [stageIndex, setStageIndex] = useState(0)

  useEffect(() => {
    const isLast = stageIndex === STAGES.length - 1
    const timeout = setTimeout(
      () => setStageIndex((i) => (isLast ? 0 : i + 1)),
      isLast ? STAGE_DURATION_MS * 1.8 : STAGE_DURATION_MS
    )
    return () => clearTimeout(timeout)
  }, [stageIndex])

  const stage = STAGES[stageIndex]
  const c = CONTENT[stage]

  return (
    <div className="recovery-card">
      <div className="recovery-card-header">
        <span>RECOVERY EVENT</span>
        <span className={`recovery-card-status status-${c.statusTone}`}>
          <span className="recovery-card-status-dot" />
          {c.statusLabel}
        </span>
      </div>

      <div className="recovery-card-amount">₹4,999</div>
      <div className="recovery-card-reason">Card declined</div>

      <div className="recovery-card-divider" />

      <div className="recovery-card-row">
        <div className="recovery-card-row-label">AI diagnosis</div>
        <div className={`recovery-card-row-value ${stage === 'failed' ? 'is-pending' : ''}`}>
          {c.diagnosis}
        </div>
      </div>

      <div className="recovery-card-row">
        <div className="recovery-card-row-label">Safety gate</div>
        <div className={`recovery-card-row-value ${c.gate ? 'gate-passed' : 'is-pending'}`}>
          {c.gate ? '✓ Retry allowed · 1 of 3' : 'Pending evidence'}
        </div>
      </div>

      <div className="recovery-card-row">
        <div className="recovery-card-row-label">Recovery action</div>
        <div className={`recovery-card-row-value ${c.action === '—' ? 'is-pending' : ''}`}>
          {c.action}
        </div>
      </div>

      <div className="recovery-card-footer">
        <span className="recovery-card-footer-dot" />
        Razorpay Test Mode
      </div>
    </div>
  )
}
