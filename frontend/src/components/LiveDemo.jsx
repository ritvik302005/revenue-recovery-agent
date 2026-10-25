import { useState, useEffect, useRef } from 'react'
import { apiFetch } from '../api.js'
import { formatINR, humanize } from '../hooks/useShowcaseCase.js'
import { loadCheckoutScript, TEST_CARD_FAIL } from '../checkout.js'
import SiteNav from './SiteNav.jsx'

const STEP_NAMES = ['Create a real order', 'Fail a payment', 'Agent acts', 'Customer pays', 'Result']
const POLL_MS = 2500

const STAGES = { IDLE: 'idle', ORDER_CREATED: 'order_created', AGENT: 'agent' }

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

function useCountdown(seconds, key) {
  const [left, setLeft] = useState(seconds)
  useEffect(() => { setLeft(seconds) }, [seconds, key])
  useEffect(() => {
    if (left <= 0) return
    const t = setTimeout(() => setLeft((s) => s - 1), 1000)
    return () => clearTimeout(t)
  }, [left])
  return left
}

const REQUEST_STATUS = {
  scheduled: 'Scheduled: the customer can pay once the delay passes',
  open: 'Open: waiting for the customer',
  paid: 'Paid',
}

function RequestStatus({ request }) {
  const left = useCountdown(request.seconds_until_available, request.link)
  const label = request.status === 'scheduled' && left > 0
    ? `Scheduled: payable in ${left} s`
    : REQUEST_STATUS[request.status] || humanize(request.status)
  return (
    <div className="request-status">
      <span className={`badge ${request.status === 'scheduled' && left > 0 ? 'badge-plain' : 'badge-real'}`}>{label}</span>
      {request.has_order && <span className="badge badge-plain">Customer has opened Checkout</span>}
      {request.excluded_method && <span className="badge badge-plain">{humanize(request.excluded_method)} hidden</span>}
    </div>
  )
}

function AgentPanel({ view }) {
  const recovered = view.stage === 'recovered'
  const latest = [...view.outbox].reverse()
  return (
    <>
      <section className="stage-panel">
        <h2 className="stage-title tone-real">Real failure recorded from Razorpay</h2>
        <dl className="facts">
          <div><dt>Failure reason</dt><dd>{humanize(view.failure_reason)}</dd></div>
          <div><dt>Razorpay error</dt><dd><code>{view.raw_error_code}</code></dd></div>
          <div><dt>Paid with</dt><dd>{humanize(view.failed_method) || 'unknown'}</dd></div>
          <div><dt>Agent's action</dt><dd>{humanize(view.recommended_action)}</dd></div>
          <div><dt>Attempt</dt><dd>{view.recovery_attempts} of {view.max_attempts}</dd></div>
        </dl>
      </section>

      {view.stage === 'awaiting_customer' && view.current_request && (
        <section className="stage-panel">
          <h2 className="stage-title">What the agent did</h2>
          <RequestStatus request={view.current_request} />
          <p className="waiting">This page updates when the customer pays.</p>
        </section>
      )}

      {view.stage === 'escalated' && view.support_case && (
        <section className="stage-panel">
          <h2 className="stage-title">Escalated to support</h2>
          <p>
            Case <code>{view.support_case.id}</code> opened. The agent sends no payment request:
            {' '}{view.support_case.note}
          </p>
        </section>
      )}

      {view.stage === 'held' && (
        <section className="stage-panel">
          <h2 className="stage-title tone-danger">Held by the safety gate</h2>
          <p>{view.audit_trail[view.audit_trail.length - 1]?.detail}</p>
        </section>
      )}

      {recovered && view.result && (
        <section className="stage-panel result">
          <div className="result-slip">
            <h2 className="result-title">Recovered — verified by Razorpay Test Mode</h2>
            <dl className="receipt-lines">
              <div className="receipt-line"><dt>Amount recovered</dt><dd className="is-strong">{formatINR(view.result.amount_recovered)}</dd></div>
              <div className="receipt-line"><dt>Recovery order</dt><dd className="is-id">{view.result.recovery_order_id}</dd></div>
              <div className="receipt-line"><dt>Attempts</dt><dd>{view.recovery_attempts} of {view.max_attempts}</dd></div>
            </dl>
            <div className="stamp stamp-real" aria-hidden="true">Captured · verified</div>
            <p className="receipt-foot">The customer paid through the agent's link; Razorpay reported it captured (outcome_is_simulated: false).</p>
          </div>
        </section>
      )}

      {latest.length > 0 && (
        <section className="stage-panel outbox" aria-labelledby="outbox-title">
          <h2 className="stage-title" id="outbox-title">Outbox</h2>
          <p className="panel-note">What the customer received. In production this goes by SMS or email; in the demo it is shown here.</p>
          <ol className="outbox-list">
            {latest.map((m, i) => (
              <li key={m.link} className={`outbox-msg ${i === 0 && view.stage === 'awaiting_customer' ? 'is-current' : ''}`}>
                <div className="outbox-meta">
                  <span>Attempt {m.attempt} · {humanize(m.action)}</span>
                  <span>{new Date(m.at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                </div>
                {/* The server stores a path; a real message would carry the full URL. */}
                <p className="outbox-text">{m.text.replace(m.link, window.location.origin + m.link)}</p>
                {i === 0 && view.stage === 'awaiting_customer' && (
                  <a className="btn btn-paper btn-sm" href={m.link} target="_blank" rel="noopener">
                    Open as the customer ↗
                  </a>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  )
}

export default function LiveDemo({ navigate }) {
  const [config, setConfig] = useState(null)
  const [stage, setStage] = useState(STAGES.IDLE)
  const [order, setOrder] = useState(null)
  const [view, setView] = useState(null)      // the server's session view once the failure is recorded
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

  // While the customer has the request, follow the session (they pay in another tab).
  const awaitingCustomer = view?.stage === 'awaiting_customer'
  useEffect(() => {
    if (!awaitingCustomer || !order) return
    const t = setInterval(() => {
      if (document.visibilityState !== 'visible') return
      apiFetch('/api/live-demo/session', { session: true, params: { order_id: order.id } })
        .then(setView)
        .catch(() => {})
    }, POLL_MS)
    return () => clearInterval(t)
  }, [awaitingCustomer, order])

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
      openCheckout(orderData)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function openCheckout(orderData) {
    // Set once Checkout has produced an outcome we act on, so closing the
    // popup afterwards isn't mistaken for the user dismissing it.
    let settled = false
    const settle = () => {
      settled = true
      rzpRef.current?.close()
    }
    setCheckoutClosed(false)
    setRetry(null)

    const rzp = new window.Razorpay({
      key: config.key_id,
      amount: orderData.amount,
      currency: orderData.currency,
      order_id: orderData.id,
      name: 'Revenue Recovery Demo',
      description: 'Live demo — intentionally failing test card',
      prefill: { name: 'Demo Customer', email: 'demo@example.com', contact: '9999999999' },
      handler: function () {
        settle()
        // The payment went through, so there is no failure to recover.
        setError('That payment succeeded, so there is no failure to recover. Start over and use the ' +
          `failing test card (${TEST_CARD_FAIL.number}), then ${TEST_CARD_FAIL.bankPage} on the bank page.`)
      },
      modal: {
        ondismiss: function () {
          setBusy(false)
          if (!settled) setCheckoutClosed(true)
        },
      },
    })
    rzpRef.current = rzp
    rzp.on('payment.failed', async function (response) {
      // Close Checkout's own retry screen: the app takes it from here.
      settle()
      await handleFailure(orderData.id, response.error.metadata.payment_id)
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
      setView(data)
      setStage(STAGES.AGENT)
    } catch (e) {
      setError(e.message)
      setRetry(() => () => handleFailure(orderId, paymentId))
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

  function reset() {
    rzpRef.current?.close()
    rzpRef.current = null
    setCheckoutClosed(false)
    setRetry(null)
    setStage(STAGES.IDLE)
    setOrder(null)
    setView(null)
    setError(null)
  }

  const shell = (children) => (
    <div className="site">
      <SiteNav current="demo" navigate={navigate} />
      <main id="main" className="page wrap">
        <header className="page-head">
          <p className="eyebrow">Live demo · Razorpay Test Mode · nothing simulated</p>
          <h1 className="display page-title">Fail a real payment, then watch the agent recover it</h1>
          <p className="page-lede">
            You fail a real Razorpay test payment. The agent reads the real error, decides, and
            acts: it sends the customer a recovery link (now, after a delay, or with the failed
            method hidden) or opens a support case. You then play the customer in another tab.
            A recovery counts only if Razorpay reports the payment captured.
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

  const currentStep = stage === STAGES.IDLE ? 0
    : stage === STAGES.ORDER_CREATED ? 1
    : view?.stage === 'awaiting_customer' ? (view.current_request?.has_order ? 3 : 2)
    : 4
  const finished = view && ['recovered', 'escalated', 'held'].includes(view.stage)

  return shell(
    <>
      <ol className="steps steps-5" aria-label="Demo progress">
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
          <CheckoutStatus closed={checkoutClosed} busy={busy} onReopen={() => { setError(null); openCheckout(order) }} />
        </section>
      )}

      {stage === STAGES.AGENT && view && <AgentPanel view={view} />}

      {stage !== STAGES.IDLE && (
        <button className={finished ? 'btn btn-ghost' : 'link-btn'} onClick={reset} disabled={busy}>
          {finished ? 'Start over' : 'Cancel and start over'}
        </button>
      )}
    </>
  )
}
