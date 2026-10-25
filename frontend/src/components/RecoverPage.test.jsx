import { beforeEach, describe, expect, it } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch } from '../test/mockFetch.js'
import RecoverPage from './RecoverPage.jsx'

// Lets the report request the callback started finish inside act().
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const TOKEN = 'rr_tokenBBBBBBBBBBBBBBBBBBBBBB'
let checkout
class FakeRazorpay {
  constructor(options) { this.options = options; this.handlers = {}; checkout = this }
  on(event, fn) { this.handlers[event] = fn }
  open() {}
  close() { this.options.modal.ondismiss() }
}

const request = (overrides = {}) => ({
  status: 'open', action: 'retry_same_method', attempt: 1, max_attempts: 3, seconds_until_available: 0,
  excluded_method: null, has_order: false, merchant: 'Revenue Recovery Demo', amount: 1000, currency: 'INR',
  failure_reason: 'bank_timeout', key_id: 'rzp_test_stub', order: null, checkout_config: null, amount_recovered: 0,
  ...overrides,
})

beforeEach(() => {
  checkout = null
  window.Razorpay = FakeRazorpay
})

describe('RecoverPage (the customer view)', () => {
  it('shows the amount, a plain-language reason and the test card', async () => {
    mockFetch({ [`/api/recover/${TOKEN}`]: { body: request() } })
    render(<RecoverPage token={TOKEN} />)
    expect(await screen.findByText('Complete your payment')).toBeInTheDocument()
    expect(screen.getByText(/Your bank took too long to respond/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pay ₹10.00' })).toBeEnabled()
    expect(screen.getByText('4100 2800 0000 1007')).toBeInTheDocument()
  })

  it('pays through Checkout and shows the verified result', async () => {
    const fetch = mockFetch({
      [`/api/recover/${TOKEN}`]: { body: request() },
      [`/api/recover/${TOKEN}/order`]: { body: { order: { id: 'order_R1', amount: 1000, currency: 'INR' }, checkout_config: null } },
      [`/api/recover/${TOKEN}/report`]: { body: request({ status: 'paid', amount_recovered: 1000 }) },
    })
    const user = userEvent.setup()
    render(<RecoverPage token={TOKEN} />)
    await user.click(await screen.findByRole('button', { name: 'Pay ₹10.00' }))
    expect(checkout.options.order_id).toBe('order_R1')
    await act(async () => { checkout.options.handler({ razorpay_payment_id: 'pay_S1', razorpay_signature: 'sig' }); await flush() })
    expect(await screen.findByText('Payment received')).toBeInTheDocument()
    const [url] = fetch.mock.calls.find(([u]) => u.includes('/report'))
    expect(url).toMatch(/payment_id=pay_S1&razorpay_signature=sig/)
  })

  it('hides the failed method in Checkout and explains it', async () => {
    const config = { display: { hide: [{ method: 'card' }], preferences: { show_default_blocks: true } } }
    mockFetch({
      [`/api/recover/${TOKEN}`]: { body: request({ action: 'suggest_alternate_method', excluded_method: 'card', checkout_config: config }) },
      [`/api/recover/${TOKEN}/order`]: { body: { order: { id: 'order_R2', amount: 1000, currency: 'INR' }, checkout_config: config } },
    })
    const user = userEvent.setup()
    render(<RecoverPage token={TOKEN} />)
    expect(await screen.findByText(/card isn't offered/)).toBeInTheDocument()
    expect(screen.getByText('success@razorpay')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Pay ₹10.00' }))
    expect(checkout.options.config).toEqual(config)
  })

  it('keeps a scheduled retry closed with a countdown', async () => {
    mockFetch({ [`/api/recover/${TOKEN}`]: { body: request({ status: 'scheduled', action: 'retry_with_delay', seconds_until_available: 30 }) } })
    render(<RecoverPage token={TOKEN} />)
    const button = await screen.findByRole('button', { name: /Available in 30 s/ })
    expect(button).toBeDisabled()
  })

  it('reports a failed payment without a signature', async () => {
    const fetch = mockFetch({
      [`/api/recover/${TOKEN}`]: { body: request() },
      [`/api/recover/${TOKEN}/order`]: { body: { order: { id: 'order_R1', amount: 1000, currency: 'INR' }, checkout_config: null } },
      [`/api/recover/${TOKEN}/report`]: { body: request({ status: 'failed' }) },
    })
    const user = userEvent.setup()
    render(<RecoverPage token={TOKEN} />)
    await user.click(await screen.findByRole('button', { name: 'Pay ₹10.00' }))
    await act(async () => { checkout.handlers['payment.failed']({ error: { metadata: { payment_id: 'pay_X' } } }); await flush() })
    expect(await screen.findByText("This payment didn't go through")).toBeInTheDocument()
    const [url] = fetch.mock.calls.find(([u]) => u.includes('/report'))
    expect(url).not.toMatch(/razorpay_signature/)
  })

  it.each([
    ['expired', 'This link has expired'],
    ['superseded', 'This link is no longer active'],
    ['escalated', 'Support will contact you'],
  ])('explains a %s link', async (status, title) => {
    mockFetch({ [`/api/recover/${TOKEN}`]: { body: request({ status }) } })
    render(<RecoverPage token={TOKEN} />)
    expect(await screen.findByText(title)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Pay/ })).not.toBeInTheDocument()
  })

  it('says when the link does not exist', async () => {
    mockFetch({ [`/api/recover/${TOKEN}`]: { status: 404, body: { detail: "This recovery link doesn't exist or has expired." } } })
    render(<RecoverPage token={TOKEN} />)
    expect(await screen.findByText('Link not found')).toBeInTheDocument()
  })
})
