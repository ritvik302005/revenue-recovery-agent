import { useState, useEffect, useRef } from 'react'
import { apiFetch } from '../api.js'
import SiteNav from './SiteNav.jsx'

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

const STEP_NAMES = ['Create a real order', 'Fail a payment', 'Attempt recovery', 'Result']

function CheckoutStatus({ closed, busy, onReopen }) {
  if (!closed) return <p className="waiting">Waiting for the Checkout attempt to finish…</p>
  return (
    <p className="waiting">
      Checkout was closed before a payment finished.
      <button className="btn btn-ghost btn-sm" onClick={onReopen} disabled={busy}>Reopen Checkout</button>
    </p>
  )
}

// Razorpay's documented test card, laid out like a card so it's easy to type.
function TestCard({ card }) {
  return (
    <div className="test-card">
      <div className="test-card-number">{card.number}</div>
      <div className="test-card-meta">
        <span>Expiry <b>{card.expiry}</b></span>
        <span>CVV <b>{card.cvv}</b></span>
      </div>
      <p className="test-card-bank">On Razorpay's mock bank page, <strong>{card.bankPage}</strong>.</p>
    </div>
  )
}

const STAGES = {
  IDLE: 'idle',
  ORDER_CREATED: 'order_created',
  FAILURE_RECORDED: 'failure_recorded',
  RECOVERY_ORDER_CREATED: 'recovery_order_created',
  DONE: 'done',
}

export default function LiveDemo({ navigate }) {
  const [config, setConfig] = useState(null)
  const [stage, setStage] = useState(STAGES.IDLE)
  const [order, setOrder] = useState(null)
  const [failureInfo, setFailureInfo] = useState(null)
  const [recoveryOrder, setRecoveryOrder] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [checkoutClosed, setCheckoutClosed] = useState(false)
  const [retry, setRetry] = useState(null)   // re-sends a report that failed (network, not final yet)
  const rzpRef = useRef(null)

  useEffect(() => {
    apiFetch('/api/live-demo/config')
      .then(setConfig)
      .catch(() => setConfig({ configured: false }))
    loadCheckoutScript().catch((e) => setError(e.message))
  }, [])

  async function startDemo() {
    setError(null)
    setBusy(true)
    try {
      const orderData = await apiFetch('/api/live-demo/create-order', {
        method: 'POST',
        session: true,
        body: { amount: 1000, label: 'live_demo_failure' },
      })
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
    // Set once Checkout has produced an outcome we act on, so closing the
    // popup afterwards isn't mistaken for the user dismissing it.
    let settled = false
    const settle = () => {
      settled = true
      rzpRef.current?.close()
    }
    setCheckoutClosed(false)
    setRetry(null)

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
        settle()
        if (mode === 'fail') {
          // The payment went through, so there is no failure to recover.
          setError('That payment succeeded, so there is no failure to recover. Start over and use the ' +
            `failing test card (${TEST_CARD_FAIL.number}), then ${TEST_CARD_FAIL.bankPage} on the bank page.`)
        } else {
          // Checkout's signed success response: the backend verifies the
          // signature before it records a recovery.
          await handleRecoverySuccess(order.id, orderData.id, response.razorpay_payment_id, response.razorpay_signature)
        }
      },
      modal: {
        ondismiss: function () {
          setBusy(false)
          if (!settled) setCheckoutClosed(true)
        },
      },
    }

    const rzp = new window.Razorpay(options)
    rzpRef.current = rzp
    rzp.on('payment.failed', async function (response) {
      // Close Checkout's own retry screen: the app takes it from here.
      settle()
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
      const data = await apiFetch('/api/live-demo/report-failure', {
        method: 'POST',
        session: true,
        params: { order_id: orderId, payment_id: paymentId },
      })
      setFailureInfo(data)
      setStage(STAGES.FAILURE_RECORDED)
    } catch (e) {
      setError(e.message)
      setRetry(() => () => handleFailure(orderId, paymentId))
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
      const orderData = await apiFetch('/api/live-demo/create-recovery-order', {
        method: 'POST',
        session: true,
        params: { order_id: order.id },
      })
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
      const params = {
        order_id: originalOrderId,
        recovery_order_id: recoveryOrderId,
        recovery_payment_id: recoveryPaymentId,
      }
      if (signature) params.razorpay_signature = signature
      const data = await apiFetch('/api/live-demo/report-recovery', { method: 'POST', session: true, params })
      setResult(data)
      setStage(STAGES.DONE)
    } catch (e) {
      setError(e.message)
      setRetry(() => () => handleRecoverySuccess(originalOrderId, recoveryOrderId, recoveryPaymentId, signature))
    } finally {
      setBusy(false)
    }
  }

  function retryReport() {
    const run = retry
    setError(null)
    setRetry(null)
    run()
  }

  function reopenCheckout() {
    setError(null)
    if (stage === STAGES.ORDER_CREATED) openCheckout(order, 'fail')
    else openCheckout(recoveryOrder, 'success')
  }

  function reset() {
    rzpRef.current?.close()
    rzpRef.current = null
    setCheckoutClosed(false)
    setRetry(null)
    setStage(STAGES.IDLE)
    setOrder(null)
    setFailureInfo(null)
    setRecoveryOrder(null)
    setResult(null)
    setError(null)
  }

  const shell = (children) => (
    <div className="site">
      <SiteNav current="demo" navigate={navigate} />
      <main id="main" className="page wrap">
        <header className="page-head">
          <p className="eyebrow">Live demo · Razorpay Test Mode · nothing simulated</p>
          <h1 className="display page-title">Fail a real payment, then recover it</h1>
          <p className="page-lede">
            A real Razorpay test order, a real Checkout failure with Razorpay's documented
            test card, and a real recovery attempt on an order the server creates. The
            result counts only if Razorpay reports the payment captured and Checkout's
            signature verifies.
          </p>
        </header>
        {children}
      </main>
    </div>
  )

  if (config && !config.configured) {
    return shell(
      <div className="alert" role="alert">
        Razorpay test keys aren't configured on the backend, so the live demo can't run.
        Add test-mode <code>RAZORPAY_KEY_ID</code> and <code>RAZORPAY_KEY_SECRET</code> to{' '}
        <code>backend/.env</code> and restart it (live-mode keys are refused).
      </div>
    )
  }

  const currentStep = { [STAGES.IDLE]: 0, [STAGES.ORDER_CREATED]: 1, [STAGES.FAILURE_RECORDED]: 2,
                        [STAGES.RECOVERY_ORDER_CREATED]: 2, [STAGES.DONE]: 3 }[stage]
  const inProgress = [STAGES.ORDER_CREATED, STAGES.FAILURE_RECORDED, STAGES.RECOVERY_ORDER_CREATED].includes(stage)
  const recovered = result?.recovery_outcome === 'recovered'

  return shell(
    <>
      <ol className="steps" aria-label="Demo progress">
        {STEP_NAMES.map((name, i) => (
          <li key={name} className={i < currentStep ? 'is-done' : i === currentStep ? 'is-current' : ''}
              aria-current={i === currentStep ? 'step' : undefined}>
            <span className="steps-num">{i + 1}</span>{name}
          </li>
        ))}
      </ol>

      {error && (
        <div className="alert" role="alert">
          <span>{error}</span>
          {retry && <button className="btn btn-ghost btn-sm" onClick={retryReport} disabled={busy}>Try again</button>}
        </div>
      )}

      {stage === STAGES.IDLE && (
        <section className="stage-panel">
          <p>
            You'll pay a ₹10 test order with Razorpay's failing test card. Nothing is charged:
            this is Razorpay Test Mode.
          </p>
          <button className="btn btn-paper" onClick={startDemo} disabled={busy}>
            {busy ? 'Creating a real test order…' : 'Start the live demo'}
          </button>
        </section>
      )}

      {stage === STAGES.ORDER_CREATED && (
        <section className="stage-panel">
          <p>Real order created: <code>{order.id}</code>. In the Checkout popup, pay with the <strong>failing</strong> test card:</p>
          <TestCard card={TEST_CARD_FAIL} />
          <CheckoutStatus closed={checkoutClosed} busy={busy} onReopen={reopenCheckout} />
        </section>
      )}

      {stage === STAGES.FAILURE_RECORDED && failureInfo && (
        <section className="stage-panel">
          <h2 className="stage-title tone-real">Real failure recorded from Razorpay</h2>
          <dl className="facts">
            <div><dt>Failure reason</dt><dd>{failureInfo.failure_reason.replace(/_/g, ' ')}</dd></div>
            <div><dt>Razorpay error</dt><dd><code>{failureInfo.raw_error_code}</code></dd></div>
            <div><dt>Agent's action</dt><dd>{failureInfo.recommended_action.replace(/_/g, ' ')}</dd></div>
            <div><dt>Safety gate</dt><dd className={failureInfo.safety_check_passed ? 'tone-real' : 'tone-danger'}>
              {failureInfo.safety_check_passed ? 'passed' : 'blocked'}</dd></div>
          </dl>
          {failureInfo.safety_check_passed ? (
            <button className="btn btn-paper" onClick={attemptRecovery} disabled={busy}>
              {busy ? 'Creating the recovery order…' : 'Attempt a real recovery'}
            </button>
          ) : (
            <p className="tone-danger">The safety gate blocked recovery. No further action is taken on this payment.</p>
          )}
        </section>
      )}

      {stage === STAGES.RECOVERY_ORDER_CREATED && (
        <section className="stage-panel">
          <p>Real recovery order created: <code>{recoveryOrder.id}</code>. In the Checkout popup, pay with the <strong>success</strong> test card:</p>
          <TestCard card={TEST_CARD_SUCCESS} />
          <CheckoutStatus closed={checkoutClosed} busy={busy} onReopen={reopenCheckout} />
        </section>
      )}

      {stage === STAGES.DONE && result && (
        <section className="stage-panel result">
          <div className="result-slip">
            <h2 className="result-title">
              {recovered ? 'Recovered — verified by Razorpay Test Mode' : `Real recovery outcome: ${result.recovery_outcome.replace(/_/g, ' ')}`}
            </h2>
            <dl className="receipt-lines">
              <div className="receipt-line"><dt>Amount recovered</dt><dd className="is-strong">₹{(result.amount_recovered / 100).toFixed(2)}</dd></div>
              <div className="receipt-line"><dt>Attempts</dt><dd>{result.recovery_attempts} of {result.max_attempts}</dd></div>
            </dl>
            <div className={`stamp ${recovered ? 'stamp-real' : 'stamp-danger'}`} aria-hidden="true">
              {recovered ? 'Captured · verified' : 'Not recovered'}
            </div>
            <p className="receipt-foot">From Razorpay's payment status, not a probability model (outcome_is_simulated: false).</p>
          </div>
          <div className="cta-row">
            {result.stage === 'recovery_failed' && result.recovery_attempts < result.max_attempts && (
              <button className="btn btn-paper" onClick={attemptRecovery} disabled={busy}>
                {busy ? 'Creating the recovery order…' : 'Try another recovery attempt'}
              </button>
            )}
            <button className="btn btn-ghost" onClick={reset}>Start over</button>
          </div>
          {result.stage === 'recovery_failed' && result.recovery_attempts >= result.max_attempts && (
            <p className="tone-danger">Retry budget used: the safety gate allows no further attempts on this payment.</p>
          )}
        </section>
      )}

      {inProgress && (
        <button className="link-btn" onClick={reset} disabled={busy}>Cancel and start over</button>
      )}
    </>
  )
}