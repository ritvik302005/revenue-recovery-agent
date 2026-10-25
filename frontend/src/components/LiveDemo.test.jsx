import { beforeEach, describe, expect, it } from 'vitest'
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

const FAILURE = {
  failure_reason: 'bank_timeout', raw_error_code: 'BAD_REQUEST_ERROR / payment_timed_out',
  recommended_action: 'retry_with_delay', safety_check_passed: true, stage: 'failure_recorded', audit_trail: [],
}

function routes(overrides = {}) {
  return mockFetch({
    '/api/live-demo/config': { body: { configured: true, key_id: 'rzp_test_stub' } },
    '/api/session': { body: { token: 'tok' } },
    '/api/live-demo/create-order': { body: { id: 'order_D1', amount: 1000, currency: 'INR' } },
    '/api/live-demo/report-failure': { body: FAILURE },
    '/api/live-demo/create-recovery-order': { body: { id: 'order_R1', amount: 1000, currency: 'INR' } },
    '/api/live-demo/report-recovery': { body: {
      recovery_outcome: 'recovered', amount_recovered: 1000, recovery_attempts: 1, max_attempts: 3, stage: 'recovered' } },
    ...overrides,
  })
}

async function startDemo(user) {
  await user.click(await screen.findByRole('button', { name: /Start Live Demo/ }))
  await screen.findByText(/Real order created/)
}

beforeEach(() => {
  checkout = null
  window.Razorpay = FakeRazorpay
})

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
    expect(checkout.opened).toBe(1)
    expect(checkout.options.order_id).toBe('order_D1')
  })

  it('offers to reopen Checkout after it is dismissed', async () => {
    routes()
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    act(() => checkout.options.modal.ondismiss())
    await user.click(screen.getByRole('button', { name: 'Reopen Checkout' }))
    expect(checkout.opened).toBe(1)              // a new Checkout instance…
    expect(checkout.options.order_id).toBe('order_D1')   // …for the same order
    expect(screen.queryByText(/Checkout was closed/)).not.toBeInTheDocument()
  })

  it('explains a successful payment in fail mode', async () => {
    routes()
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await act(() => checkout.options.handler({ razorpay_payment_id: 'pay_Ok1' }))
    expect(screen.getByRole('alert')).toHaveTextContent('That payment succeeded')
    expect(screen.queryByText(/Checkout was closed/)).not.toBeInTheDocument()
  })

  it('records the real failure, then a verified recovery', async () => {
    const fetch = routes()
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await act(() => checkout.handlers['payment.failed']({ error: { metadata: { payment_id: 'pay_F1' } } }))
    expect(await screen.findByText(/Real failure recorded from Razorpay/)).toBeInTheDocument()
    expect(screen.getByText('bank timeout')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Attempt Real Recovery' }))
    expect(await screen.findByText('order_R1')).toBeInTheDocument()
    await act(() => checkout.options.handler({ razorpay_payment_id: 'pay_S1', razorpay_signature: 'sig' }))
    expect(await screen.findByText(/Recovered — verified by Razorpay Test Mode/)).toBeInTheDocument()

    const [url] = fetch.mock.calls.find(([u]) => u.includes('report-recovery'))
    expect(url).toMatch(/order_id=order_D1&recovery_order_id=order_R1&recovery_payment_id=pay_S1&razorpay_signature=sig/)
  })

  it('lets a failed report be retried with the same ids', async () => {
    let calls = 0
    routes({
      '/api/live-demo/report-failure': () => (++calls === 1
        ? { status: 502, body: { detail: 'Razorpay is unreachable or returned an error. Try again shortly.' } }
        : { body: FAILURE }),
    })
    const user = userEvent.setup()
    render(<LiveDemo />)
    await startDemo(user)
    await act(() => checkout.handlers['payment.failed']({ error: { metadata: { payment_id: 'pay_F1' } } }))
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
    expect(screen.getByRole('button', { name: /Start Live Demo/ })).toBeInTheDocument()
  })
})
