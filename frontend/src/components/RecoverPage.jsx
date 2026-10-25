import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api.js'
import { formatINR, humanize } from '../hooks/useShowcaseCase.js'
import { loadCheckoutScript, TEST_CARD_SUCCESS, TEST_UPI_SUCCESS } from '../checkout.js'
import CopyButton from './CopyButton.jsx'

// Plain-language reasons for the customer (they never see internal codes).
const CUSTOMER_REASON = {
  bank_timeout: 'Your bank took too long to respond.',
  network_error: 'The connection dropped during payment.',
  issuer_unavailable: "Your bank's systems were unavailable.",
  card_declined: 'Your card was declined.',
  expired_card: 'The card has expired.',
  limit_exceeded: 'The payment went over a limit on your account.',
  insufficient_funds: "There weren't enough funds at the time.",
  invalid_cvv: 'The CVV was incorrect.',
  invalid_card_details: 'Some card details were incorrect.',
  authentication_failed: 'The OTP or 3-D Secure step failed.',
  payment_cancelled: 'The payment was cancelled before it finished.',
}

const ENDED = {
  failed: ["This payment didn't go through", "The merchant has been told and will follow up with another way to pay."],
  expired: ['This link has expired', 'The merchant has been told and will follow up.'],
  superseded: ['This link is no longer active', 'A newer payment link has been sent for this payment.'],
  escalated: ['Support will contact you', "There's nothing to pay here. The merchant's support team will be in touch about this payment."],
}

/**
 * The customer's side of a recovery: what the agent sent them. Access is
 * the token in the URL alone (no operator session).
 */
export default function RecoverPage({ token }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null })
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [now, setNow] = useState(() => Date.now())
  const loadedAt = useRef(Date.now())

  const load = useCallback(async () => {
    try {
      const data = await apiFetch(`/api/recover/${token}`)
      loadedAt.current = Date.now()
      setNow(loadedAt.current)
      setState({ status: 'ready', data, error: null })
    } catch (e) {
      setState({ status: 'error', data: null, error: e })
    }
  }, [token])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadCheckoutScript().catch(() => {}) }, [])

  // Countdown for a scheduled retry; reload once it opens.
  const data = state.data
  const remaining = data?.status === 'scheduled'
    ? Math.max(0, data.seconds_until_available - Math.max(0, Math.floor((now - loadedAt.current) / 1000)))
    : 0
  useEffect(() => {
    if (data?.status !== 'scheduled') return
    if (remaining <= 0) { load(); return }
    const t = setTimeout(() => setNow(Date.now()), 1000)
    return () => clearTimeout(t)
  }, [data?.status, remaining, load])

  async function report(paymentId, signature) {
    setBusy(true)
    try {
      const params = { payment_id: paymentId }
      if (signature) params.razorpay_signature = signature
      const updated = await apiFetch(`/api/recover/${token}/report`, { method: 'POST', params })
      setState({ status: 'ready', data: updated, error: null })
    } catch (e) {
      setNotice(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function pay() {
    setNotice(null)
    setBusy(true)
    try {
      const { order, checkout_config: config } = await apiFetch(`/api/recover/${token}/order`, { method: 'POST' })
      await loadCheckoutScript()
      let settled = false
      const rzp = new window.Razorpay({
        key: data.key_id,
        amount: order.amount,
        currency: order.currency,
        order_id: order.id,
        name: data.merchant,
        description: 'Payment recovery',
        ...(config ? { config } : {}),
        handler: (response) => { settled = true; report(response.razorpay_payment_id, response.razorpay_signature) },
        modal: { ondismiss: () => { if (!settled) setBusy(false) } },
      })
      rzp.on('payment.failed', (response) => {
        settled = true
        rzp.close()
        report(response.error.metadata.payment_id)
      })
      rzp.open()
    } catch (e) {
      setNotice(e.message)
      setBusy(false)
    }
  }

  return (
    <div className="site recover-site">
      <p className="demo-banner">Demo · the customer's view of the recovery link · Razorpay Test Mode, no real money</p>
      <main id="main" className="recover wrap">
        <RecoverBody state={state} remaining={remaining} busy={busy} notice={notice} onPay={pay} />
      </main>
    </div>
  )
}

function RecoverBody({ state, remaining, busy, notice, onPay }) {
  if (state.status === 'loading') return <p className="empty">Loading your payment…</p>
  if (state.status === 'error') {
    return (
      <div className="pay-slip">
        <h1 className="pay-title">Link not found</h1>
        <p>{state.error.status === 404 ? "This payment link doesn't exist or has expired." : state.error.message}</p>
      </div>
    )
  }

  const d = state.data
  if (d.status === 'paid') {
    return (
      <div className="pay-slip">
        <p className="pay-merchant">{d.merchant}</p>
        <h1 className="pay-title">Payment received</h1>
        <div className="pay-amount">{formatINR(d.amount_recovered || d.amount)}</div>
        <div className="stamp stamp-real" aria-hidden="true">Captured · verified</div>
        <p className="pay-foot">Confirmed by Razorpay. You can close this page.</p>
      </div>
    )
  }
  if (ENDED[d.status]) {
    const [title, body] = ENDED[d.status]
    return (
      <div className="pay-slip">
        <p className="pay-merchant">{d.merchant}</p>
        <h1 className="pay-title">{title}</h1>
        <p>{body}</p>
      </div>
    )
  }

  const scheduled = d.status === 'scheduled'
  const card = d.excluded_method !== 'card'
  return (
    <div className="pay-slip">
      <p className="pay-merchant">{d.merchant}</p>
      <h1 className="pay-title">Complete your payment</h1>
      <div className="pay-amount">{formatINR(d.amount)}</div>
      <p className="pay-reason">
        {CUSTOMER_REASON[d.failure_reason] || 'Your earlier payment didn’t go through.'}{' '}
        {d.excluded_method
          ? `Please use a different method this time: ${humanize(d.excluded_method)} isn't offered.`
          : scheduled ? 'You can try again in a moment.' : 'You can try again now.'}
      </p>
      {notice && <div className="alert" role="alert">{notice}</div>}
      <button className="btn btn-ink pay-btn" onClick={onPay} disabled={busy || scheduled}>
        {scheduled ? `Available in ${remaining} s` : busy ? 'Opening Checkout…' : `Pay ${formatINR(d.amount)}`}
      </button>
      {scheduled && (
        <p className="pay-foot" role="status">
          The agent scheduled this retry to give your bank time to recover
          (30 seconds here; real systems wait longer).
        </p>
      )}
      <div className="test-hint">
        <strong>Test mode:</strong>{' '}
        {card
          ? <>pay with card <code>{TEST_CARD_SUCCESS.number}</code> <CopyButton value={TEST_CARD_SUCCESS.number} className="on-paper" />, any future expiry and CVV, then {TEST_CARD_SUCCESS.bankPage}.</>
          : <>card is hidden on this link. Choose UPI and enter <code>{TEST_UPI_SUCCESS}</code> <CopyButton value={TEST_UPI_SUCCESS} className="on-paper" />, or netbanking with any bank and choose Success.</>}
      </div>
      <p className="pay-foot">Attempt {d.attempt} of {d.max_attempts} · Secured by Razorpay Checkout (test mode)</p>
    </div>
  )
}
