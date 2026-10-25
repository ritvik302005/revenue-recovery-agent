import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch } from '../test/mockFetch.js'
import PolicyPlayground from './PolicyPlayground.jsx'
import { linesFor } from './ScrollStory.jsx'
import SiteNav from './SiteNav.jsx'
import CopyButton from './CopyButton.jsx'

const preview = (overrides = {}) => ({
  error_reason: 'payment_timed_out', documented: true, category: 'bank_timeout', action: 'retry_same_method',
  safety_check_passed: true, gate: 'Passed',
  plan: { kind: 'payment_request', summary: 'Opened a recovery request the customer can pay now, with any method.' },
  customer_message: "Sorry, your payment of ₹10.00 to Revenue Recovery Demo didn't go through. You can try again here: <link>",
  ...overrides,
})

describe('PolicyPlayground', () => {
  it('prints the decision for the chosen error and method', async () => {
    const fetch = mockFetch({
      '/api/policy': { body: { reasons: [{ error_reason: 'payment_timed_out', category: 'bank_timeout' },
                                          { error_reason: 'payment_risk_check_failed', category: 'fraud_suspected' }] } },
      '/api/policy/preview': (url) => ({ body: new URL(url).searchParams.get('error_reason') === 'payment_risk_check_failed'
        ? preview({ error_reason: 'payment_risk_check_failed', category: 'fraud_suspected', action: 'no_action_fraud_hold',
                    safety_check_passed: false, plan: null, customer_message: null })
        : preview() }),
    })
    const user = userEvent.setup()
    render(<PolicyPlayground />)
    const slip = await screen.findByRole('article', { name: "The agent's decision" })
    expect(within(slip).getByText('retry same method')).toBeInTheDocument()
    expect(within(slip).getByText(/You can try again here/)).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Razorpay error_reason'), 'payment_risk_check_failed')
    const held = await screen.findByText(/blocked: fraud signal/)
    expect(held).toBeInTheDocument()
    expect(screen.queryByText(/Customer receives/)).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('UPI'))
    const last = fetch.mock.calls.filter(([u]) => u.includes('/preview')).at(-1)[0]
    expect(last).toMatch(/method=upi/)
  })
})

describe('ScrollStory lines', () => {
  it('prints only values from the recorded case', () => {
    const lines = linesFor({
      kind: 'live_demo', payment_id: 'pay_A', amount: 1000, raw_error_code: 'BAD_REQUEST_ERROR / payment_failed @ payment_authorization',
      failure_reason: 'card_declined', action: 'suggest_alternate_method', outcome: 'recovered', attempts: 1,
      audit_trail: [
        { step: 'classify', detail: '…' },
        { step: 'select_action', detail: "Selected 'suggest_alternate_method' as the recovery strategy for 'card_declined'." },
        { step: 'safety_check', detail: 'Passed: within retry budget.' },
        { step: 'execute', detail: '…', data: { plan: { summary: "Opened a recovery request with 'card' hidden." } } },
      ],
    })
    expect(lines.map((l) => l.value)).toEqual([
      'pay_A · ₹10.00',
      'payment_failed @ payment_authorization → card declined',
      'suggest alternate method',
      'passed',
      "Opened a recovery request with 'card' hidden.",
      'recovered · 1 of 3 attempts',
    ])
  })

  it('has nothing to print without a case', () => {
    expect(linesFor({ kind: 'none' })).toBeNull()
    expect(linesFor(null)).toBeNull()
  })
})

describe('SiteNav', () => {
  it('opens and closes the menu', async () => {
    const user = userEvent.setup()
    render(<SiteNav />)
    const toggle = screen.getByRole('button', { name: 'Open menu' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await user.keyboard('{Escape}')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('routes plain clicks in-app', async () => {
    const navigate = vi.fn()
    const user = userEvent.setup()
    render(<SiteNav navigate={navigate} />)
    await user.click(screen.getByRole('link', { name: 'Evaluation' }))
    expect(navigate).toHaveBeenCalledWith('/dashboard')
  })
})

describe('CopyButton', () => {
  it('copies the value without spaces and confirms', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    render(<CopyButton value="4100 2800 0000 1007" />)
    await user.click(screen.getByRole('button', { name: /Copy/ }))
    expect(writeText).toHaveBeenCalledWith('4100280000001007')
    expect(await screen.findByText('Copied')).toBeInTheDocument()
  })
})
