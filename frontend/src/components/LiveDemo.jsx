import { useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const CHECKOUT_SCRIPT_SRC = 'https://checkout.razorpay.com/v1/checkout.js'

// Razorpay's documented test cards (checked 2026-10-25):
// https://razorpay.com/docs/payments/payments/test-card-details/
// Any future expiry and any CVV work. The error card only fails if
// "Failure" is chosen on the mock bank page (it then returns
// error_reason payment_timed_out); the domestic card succeeds with
// "Success" or any 4–10 digit OTP.
const TEST_CARD_FAIL = { number: '4100 2800 0009 0000', expiry: '12/30', cvv: '123', bankPage: 'choose Failure' }
const TEST_CARD_SUCCESS = { number: '4100 2800 0000 1007', expiry: '12/30', cvv: '123', bankPage: 'choose Success (or enter any 4–10 digit OTP)' }

function loadCheckoutScript() {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) return resolve()
    const script = document.createElement('script')
    script.src = CHECKOUT_SCRIPT_SRC
    script.onload = resolve
    script.onerror = () => reject(new Error('Failed to load Razorpay Checkout script'))
    document.body.appendChild(script)
  })
}

const STAGES = {
  IDLE: 'idle',
  ORDER_CREATED: 'order_created',
  FAILURE_RECORDED: 'failure_recorded',
  RECOVERY_ORDER_CREATED: 'recovery_order_created',
  DONE: 'done',
}

export default function LiveDemo({ onBack }) {
  const [config, setConfig] = useState(null)
  const [stage, setStage] = useState(STAGES.IDLE)
  const [order, setOrder] = useState(null)
  const [failureInfo, setFailureInfo] = useState(null)
  const [recoveryOrder, setRecoveryOrder] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE}/api/live-demo/config`)
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => setConfig({ configured: false }))
    loadCheckoutScript().catch((e) => setError(e.message))
  }, [])

  async function startDemo() {
    setError(null)
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/api/live-demo/create-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: 1000, label: 'live_demo_failure' }),
      })
      const orderData = await res.json()
      if (!res.ok) throw new Error(orderData.error || 'Order creation failed')
      setOrder(orderData)
      setStage(STAGES.ORDER_CREATED)
      openCheckout(orderData, 'fail')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function openCheckout(orderData, mode) {
    const card = mode === 'fail' ? TEST_CARD_FAIL : TEST_CARD_SUCCESS
    const options = {
      key: config.key_id,
      amount: orderData.amount,
      currency: orderData.currency,
      order_id: orderData.id,
      name: 'Revenue Recovery Demo',
      description:
        mode === 'fail'
          ? 'Live demo — intentionally failing test card'
          : 'Live demo — recovery attempt with success test card',
      prefill: { name: 'Demo Customer', email: 'demo@example.com', contact: '9999999999' },
      // Note: Razorpay Checkout requires manual card entry from the
      // user for security — we can't script the card fields directly.
      // We show the exact test card to type in the on-screen banner.
      handler: async function (response) {
        if (mode === 'fail') {
          // Shouldn't normally reach here on a genuinely failing card —
          // Checkout's own failure handler below covers that path.
        } else {
          // Checkout's signed success response: the backend verifies the
          // signature before it records a recovery.
          await handleRecoverySuccess(order.id, orderData.id, response.razorpay_payment_id, response.razorpay_signature)
        }
      },
      modal: {
        ondismiss: function () {
          setBusy(false)
        },
      },
    }

    const rzp = new window.Razorpay(options)
    rzp.on('payment.failed', async function (response) {
      const paymentId = response.error.metadata.payment_id
      if (mode === 'fail') {
        await handleFailure(orderData.id, paymentId)
      } else {
        // A failed recovery attempt is a real outcome too: record it.
        await handleRecoverySuccess(order.id, orderData.id, paymentId)
      }
    })
    rzp.open()
  }

  async function handleFailure(orderId, paymentId) {
    setBusy(true)
    try {
      const res = await fetch(
        `${API_BASE}/api/live-demo/report-failure?order_id=${orderId}&payment_id=${paymentId}`,
        { method: 'POST' }
      )
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to report failure')
      setFailureInfo(data)
      setStage(STAGES.FAILURE_RECORDED)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function attemptRecovery() {
    setError(null)
    setBusy(true)
    try {
      // The server creates the recovery order and binds it to this
      // session; report-recovery only accepts a payment on this order.
      const res = await fetch(
        `${API_BASE}/api/live-demo/create-recovery-order?order_id=${order.id}`,
        { method: 'POST' }
      )
      const orderData = await res.json()
      if (!res.ok) throw new Error(orderData.detail || 'Could not create the recovery order')
      setRecoveryOrder(orderData)
      setStage(STAGES.RECOVERY_ORDER_CREATED)
      openCheckout(orderData, 'success')
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  async function handleRecoverySuccess(originalOrderId, recoveryOrderId, recoveryPaymentId, signature) {
    setBusy(true)
    try {
      const params = new URLSearchParams({
        order_id: originalOrderId,
        recovery_order_id: recoveryOrderId,
        recovery_payment_id: recoveryPaymentId,
      })
      if (signature) params.set('razorpay_signature', signature)
      const res = await fetch(`${API_BASE}/api/live-demo/report-recovery?${params}`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to report recovery')
      setResult(data)
      setStage(STAGES.DONE)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function reset() {
    setStage(STAGES.IDLE)
    setOrder(null)
    setFailureInfo(null)
    setRecoveryOrder(null)
    setResult(null)
    setError(null)
  }

  if (config && !config.configured) {
    return (
      <div className="app">
        <div className="header">
          <div>
            {onBack && (
              <button className="back-link" onClick={onBack}>
                ← Back to Overview
              </button>
            )}
            <h1 className="title">AI Revenue Recovery Agent — Real Razorpay Demo</h1>
          </div>
        </div>
        <div className="section">
          <div className="section-label label-real">Live Demo (Real Checkout)</div>
          <p className="section-note">
            Razorpay keys aren't configured on the backend yet. Fill in
            backend/.env with your test-mode RAZORPAY_KEY_ID and
            RAZORPAY_KEY_SECRET, then restart the backend.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <div className="header">
        <div>
          {onBack && (
            <button className="back-link" onClick={onBack}>
              ← Back to Dashboard
            </button>
          )}
          <h1 className="title">AI Revenue Recovery Agent — Real Razorpay Demo</h1>
        </div>
      </div>

      <div className="section">
      <div className="section-label label-real">REAL RAZORPAY TEST MODE DEMO</div>
      <p className="section-note">
        Unlike the batch evaluation, this flow is fully real end-to-end: a real
        Razorpay order, a real Checkout failure using their documented
        test card, and a real recovery attempt. Nothing here is simulated.
      </p>

      {error && (
        <div style={{ color: '#c05b4d', marginBottom: 12 }}>{error}</div>
      )}

      {stage === STAGES.IDLE && (
        <button className="run-btn" onClick={startDemo} disabled={busy}>
          {busy ? 'Creating real order…' : 'Start Live Demo (Trigger Real Failure)'}
        </button>
      )}

      {stage === STAGES.ORDER_CREATED && (
        <div className="audit-panel">
          <p>
            Real order created: <code>{order.id}</code>. In the Checkout
            popup, enter the documented Razorpay <strong>failing</strong>{' '}
            test card:
          </p>
          <p>
            Card: <code>{TEST_CARD_FAIL.number}</code> · Expiry:{' '}
            <code>{TEST_CARD_FAIL.expiry}</code> · CVV:{' '}
            <code>{TEST_CARD_FAIL.cvv}</code>
          </p>
          <p>On Razorpay's mock bank page, <strong>{TEST_CARD_FAIL.bankPage}</strong>.</p>
          <p style={{ color: '#a89a86' }}>Waiting for the Checkout attempt to complete…</p>
        </div>
      )}

      {stage === STAGES.FAILURE_RECORDED && failureInfo && (
        <div className="audit-panel">
          <div style={{ color: '#4a9d7f', fontWeight: 600, marginBottom: 8 }}>
            ✓ Real failure recorded from Razorpay
          </div>
          <p>Failure reason: <strong>{failureInfo.failure_reason.replace(/_/g, ' ')}</strong></p>
          <p>Razorpay error code: <code>{failureInfo.raw_error_code}</code></p>
          <p>Agent's recommended action: <strong>{failureInfo.recommended_action.replace(/_/g, ' ')}</strong></p>
          <p>Safety check: {failureInfo.safety_check_passed ? '✓ passed' : '✗ blocked'}</p>
          {failureInfo.safety_check_passed ? (
            <button className="run-btn" onClick={attemptRecovery} disabled={busy} style={{ marginTop: 10 }}>
              {busy ? 'Creating recovery order…' : 'Attempt Real Recovery'}
            </button>
          ) : (
            <p style={{ color: '#c47f3a' }}>Safety gate blocked recovery — no further action taken.</p>
          )}
        </div>
      )}

      {stage === STAGES.RECOVERY_ORDER_CREATED && (
        <div className="audit-panel">
          <p>
            Real recovery order created: <code>{recoveryOrder.id}</code>. In
            the Checkout popup, enter the documented Razorpay{' '}
            <strong>success</strong> test card:
          </p>
          <p>
            Card: <code>{TEST_CARD_SUCCESS.number}</code> · Expiry:{' '}
            <code>{TEST_CARD_SUCCESS.expiry}</code> · CVV:{' '}
            <code>{TEST_CARD_SUCCESS.cvv}</code>
          </p>
          <p>On Razorpay's mock bank page, <strong>{TEST_CARD_SUCCESS.bankPage}</strong>.</p>
          <p style={{ color: '#a89a86' }}>Waiting for the recovery Checkout attempt to complete…</p>
        </div>
      )}

      {stage === STAGES.DONE && result && (
        <div className="audit-panel">
          <div style={{ color: result.recovery_outcome === 'recovered' ? '#4a9d7f' : '#c47f3a', fontWeight: 600, marginBottom: 8 }}>
            {result.recovery_outcome === 'recovered'
              ? '✓ Recovered — verified by Razorpay Test Mode'
              : `Real recovery outcome: ${result.recovery_outcome.replace(/_/g, ' ')}`}
          </div>
          <p>Amount recovered: ₹{(result.amount_recovered / 100).toFixed(2)}</p>
          <p>Recovery attempts: {result.recovery_attempts} of {result.max_attempts}</p>
          <p style={{ fontSize: 12, color: '#4a9d7f', marginTop: 10 }}>
            outcome_is_simulated: false — this result came from a real
            Razorpay Checkout payment status, not a probability model.
          </p>
          {result.stage === 'recovery_failed' && result.recovery_attempts < result.max_attempts && (
            <button className="run-btn" onClick={attemptRecovery} disabled={busy} style={{ marginTop: 10, marginRight: 10 }}>
              {busy ? 'Creating recovery order…' : 'Try Another Recovery Attempt'}
            </button>
          )}
          {result.stage === 'recovery_failed' && result.recovery_attempts >= result.max_attempts && (
            <p style={{ color: '#c47f3a' }}>
              Retry budget used — the safety gate allows no further attempts on this payment.
            </p>
          )}
          <button className="run-btn" onClick={reset} style={{ marginTop: 10 }}>
            Start Over
          </button>
        </div>
      )}
      </div>
    </div>
  )
}
