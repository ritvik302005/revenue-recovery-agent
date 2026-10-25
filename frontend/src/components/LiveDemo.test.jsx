import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch } from '../test/mockFetch.js'
import LiveDemo from './LiveDemo.jsx'

// A stand-in for Razorpay Checkout: records the options and lets the test
// fire its callbacks. No script is loaded and no order is real.
let checkout
class FakeRazorpay {
  constructor(options) { this.options = options; this.handlers = {}; this.opened = 0; checkout = this }
  on(event, fn) { this.handlers[event] = fn }
  open() { this.opened++ }
  close() { this.options.modal.ondismiss() }
}

const view = (overrides = {}) => ({
  order_id: 'order_D1', stage: 'awaiting_customer', amount: 1000,
  failure_reason: 'bank_timeout', raw_error_code: 'BAD_REQUEST_ERROR / payment_timed_out', failed_method: 'card',
  recommended_action: 'retry_same_method', safety_check_passed: true, recovery_attempts: 1, max_attempts: 3,
  current_request: { status: 'open', action: 'retry_same_method', attempt: 1, max_attempts: 3,
                     seconds_until_available: 0, excluded_method: null, has_order: false, link: '/recover/rr_tokenAAAAAAAAAAAAAAAAAAAAAA' },
  outbox: [{ at: '2026-10-25T12:00:00+00:00', attempt: 1, action: 'retry_same_method', link: '/recover/rr_tokenAAAAAAAAAAAAAAAAAAAAAA',
             text: "Sorry, your payment of ₹10.00 to Revenue Recovery Demo didn't go through. You can try again here: /recover/rr_tokenAAAAAAAAAAAAAAAAAAAAAA",
             channel: 'SMS / email in production' }],
  support_case: null, result: null, audit_trail: [],
  ...overrides,
})

function routes(overrides = {}) {
  return mockFetch({
    '/api/live-demo/config': { body: { configured: true, key_id: 'rzp_test_stub' } },
    '/api/session': { body: { token: 'tok' } },
    '/api/live-demo/create-order': { body: { id: 'order_D1', amount: 1000, currency: 'INR' } },
    '/api/live-demo/report-failure': { body: view() },
    '/api/live-demo/session': { body: view() },
    ...overrides,
  })
}

async function startDemo(user) {
  await user.click(await screen.findByRole('button', { name: /Start the live demo/ }))
  await screen.findByText(/Real order created/)
}

async function failPayment() {
  await act(() => checkout.handlers['payment.failed']({ error: { metadata: { payment_id: 'pay_F1' } } }))
}

beforeEach(() => {
  checkout = null
  window.Razorpay = FakeRazorpay
})
afterEach(() => vi.useRealTimers())

describe('LiveDemo', () => {
  it('explains when keys are not configured', async () => {
    mockFetch({ '/api/live-demo/config': { body: { configured: false, key_id: null } } })
    render(<LiveDemo />)
    expect(await screen.findByText(/keys aren't configured/)).toBeInTheDocument()
  })

  it('creates an order and shows the failing test card', async () => {
    routes()
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    expect(screen.getByText('order_D1')).toBeInTheDocument()
    expect(screen.getByText('4100 2800 0009 0000')).toBeInTheDocument()
    expect(checkout.options.order_id).toBe('order_D1')
  })

  it('offers to reopen Checkout after it is dismissed', async () => {
    routes()
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    act(() => checkout.options.modal.ondismiss())
    await user.click(screen.getByRole('button', { name: 'Reopen Checkout' }))
    expect(checkout.options.order_id).toBe('order_D1')
    expect(screen.queryByText(/Checkout was closed/)).not.toBeInTheDocument()
  })

  it('explains a successful payment in fail mode', async () => {
    routes()
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await act(() => checkout.options.handler({ razorpay_payment_id: 'pay_Ok1' }))
    expect(screen.getByRole('alert')).toHaveTextContent('That payment succeeded')
  })

  it('shows what the agent executed: the outbox message and a customer link', async () => {
    routes()
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await failPayment()
    expect(await screen.findByText(/Real failure recorded from Razorpay/)).toBeInTheDocument()
    expect(screen.getByText('bank timeout')).toBeInTheDocument()
    expect(screen.getByText(/Open: waiting for the customer/)).toBeInTheDocument()
    expect(screen.getByText(/didn't go through. You can try again here/)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Open as the customer/ })
    expect(link).toHaveAttribute('href', '/recover/rr_tokenAAAAAAAAAAAAAAAAAAAAAA')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('counts down a scheduled retry', async () => {
    routes({ '/api/live-demo/report-failure': { body: view({
      recommended_action: 'retry_with_delay',
      current_request: { ...view().current_request, status: 'scheduled', action: 'retry_with_delay', seconds_until_available: 30 },
    }) } })
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await failPayment()
    expect(await screen.findByText('Scheduled: payable in 30 s')).toBeInTheDocument()
  })

  it('follows the session until the customer has paid', async () => {
    const recovered = view({
      stage: 'recovered', current_request: null,
      result: { amount_recovered: 1000, recovery_order_id: 'order_R1', outcome_is_simulated: false },
    })
    let polls = 0
    routes({ '/api/live-demo/session': () => ({ body: ++polls >= 1 ? recovered : view() }) })
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await failPayment()
    await screen.findByText(/Open: waiting for the customer/)
    expect(await screen.findByText(/Recovered — verified by Razorpay Test Mode/, {}, { timeout: 4000 })).toBeInTheDocument()
    expect(screen.getByText('order_R1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start over' })).toBeInTheDocument()
  })

  it('shows a support case instead of a payment link', async () => {
    routes({ '/api/live-demo/report-failure': { body: view({
      stage: 'escalated', recommended_action: 'escalate_to_support', current_request: null, outbox: [],
      support_case: { id: 'case_abc', note: 'A support agent contacts the customer.' },
    }) } })
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await failPayment()
    expect(await screen.findByText('Escalated to support')).toBeInTheDocument()
    expect(screen.getByText('case_abc')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open as the customer/ })).not.toBeInTheDocument()
  })

  it('lets a failed report be retried with the same ids', async () => {
    let calls = 0
    routes({
      '/api/live-demo/report-failure': () => (++calls === 1
        ? { status: 502, body: { detail: 'Razorpay is unreachable or returned an error. Try again shortly.' } }
        : { body: view() }),
    })
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await failPayment()
    expect(await screen.findByRole('alert')).toHaveTextContent('Razorpay is unreachable')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/Real failure recorded from Razorpay/)).toBeInTheDocument()
    expect(calls).toBe(2)
  })

  it('can always cancel back to the start', async () => {
    routes()
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await user.click(screen.getByRole('button', { name: 'Cancel and start over' }))
    expect(screen.getByRole('button', { name: /Start the live demo/ })).toBeInTheDocument()
  })
})
