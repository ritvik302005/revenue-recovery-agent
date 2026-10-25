import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { mockFetch } from '../test/mockFetch.js'
import Dashboard from './Dashboard.jsx'

vi.mock('../hooks/useCountUp.js', () => ({ useCountUp: (value) => value }))

const result = (i, overrides = {}) => ({
  payment_id: `pay_T${i}`,
  amount: 49900,
  failure_reason: 'bank_timeout',
  raw_error_code: 'BAD_REQUEST_ERROR / payment_timed_out',
  razorpay_source: 'local_order',
  razorpay_order_id: null,
  action_taken: 'retry_with_delay',
  attempt_count: 1,
  outcome: 'recovered',
  audit_trail: [{ step: 'classify', detail: `classified pay_T${i}` }],
  ...overrides,
})

const metrics = (n, seed = 42) => ({
  razorpay_data_provenance: { note: 'provenance note', razorpay_test_orders: 0, local_orders: n },
  simulated_recovery_summary: {
    note: 'simulated note', batch_size: n, seed, recovered: n, still_failed: 0, pending_customer_action: 0,
    held_no_action_fraud: 0, recovery_rate_pct: 100, total_amount_at_risk_inr: 499 * n, total_amount_recovered_inr: 499 * n,
  },
  breakdown_by_failure_reason: { bank_timeout: { count: n, recovered: n } },
})

describe('Dashboard', () => {
  it('shows the saved batch on open, with its seed and size', async () => {
    mockFetch({
      '/api/batch/results': { body: { count: 2, seed: 7, results: [result(1), result(2)] } },
      '/api/batch/metrics': { body: metrics(2, 7) },
    })
    render(<Dashboard />)
    expect(await screen.findByText('pay_T1')).toBeInTheDocument()
    expect(screen.getByText(/Last run \(seed 7\): 2 synthetic failed payments/)).toBeInTheDocument()
    expect(screen.getByLabelText('Seed')).toHaveValue(7)
    expect(screen.getByLabelText('Batch size')).toHaveValue(2)
    expect(screen.queryByText(/No batch run yet/)).not.toBeInTheDocument()
  })

  it('shows the empty state when nothing is saved', async () => {
    mockFetch({ '/api/batch/results': { body: { count: 0, seed: null, results: [] } } })
    render(<Dashboard />)
    expect(await screen.findByText(/No batch run yet/)).toBeInTheDocument()
  })

  it('runs a batch with a session token and the chosen options', async () => {
    const fetch = mockFetch({
      '/api/batch/results': { body: { count: 0, seed: null, results: [] } },
      '/api/session': { body: { token: 'tok' } },
      '/api/batch/run': { body: { count: 1, seed: 9, results: [result(1)] } },
      '/api/batch/metrics': { body: metrics(1, 9) },
    })
    const user = userEvent.setup()
    render(<Dashboard />)
    await screen.findByText(/No batch run yet/)
    await user.clear(screen.getByLabelText('Seed'))
    await user.type(screen.getByLabelText('Seed'), '9')
    await user.click(screen.getByRole('button', { name: 'Run Batch' }))
    expect(await screen.findByText('pay_T1')).toBeInTheDocument()
    const [url, init] = fetch.mock.calls.find(([u]) => u.includes('/api/batch/run'))
    expect(url).toMatch(/n=60&seed=9&try_live_orders=false/)
    expect(init.headers['X-Session-Token']).toBe('tok')
  })

  it('catches out-of-range input without calling the server', async () => {
    const fetch = mockFetch({ '/api/batch/results': { body: { count: 0, seed: null, results: [] } } })
    const user = userEvent.setup()
    render(<Dashboard />)
    await screen.findByText(/No batch run yet/)
    await user.clear(screen.getByLabelText('Batch size'))
    await user.type(screen.getByLabelText('Batch size'), '600')
    await user.click(screen.getByRole('button', { name: 'Run Batch' }))
    expect(screen.getByText('Batch size must be a whole number from 1 to 500.')).toBeInTheDocument()
    expect(fetch.mock.calls.some(([u]) => u.includes('/api/batch/run'))).toBe(false)
  })

  it("shows the server's error message when a run fails", async () => {
    mockFetch({
      '/api/batch/results': { body: { count: 0, seed: null, results: [] } },
      '/api/session': { body: { token: 'tok' } },
      '/api/batch/run': { status: 429, body: { detail: 'Too many requests. Please wait a minute and try again.' } },
    })
    const user = userEvent.setup()
    render(<Dashboard />)
    await screen.findByText(/No batch run yet/)
    await user.click(screen.getByRole('button', { name: 'Run Batch' }))
    expect(await screen.findByText('Too many requests. Please wait a minute and try again.')).toBeInTheDocument()
  })

  it('opens a row with the keyboard and announces it', async () => {
    mockFetch({
      '/api/batch/results': { body: { count: 1, seed: 42, results: [result(1)] } },
      '/api/batch/metrics': { body: metrics(1) },
    })
    const user = userEvent.setup()
    render(<Dashboard />)
    const toggle = await screen.findByRole('button', { name: /pay_T1/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    toggle.focus()
    await user.keyboard('{Enter}')
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const panel = document.getElementById(toggle.getAttribute('aria-controls'))
    expect(within(panel).getByText('classified pay_T1')).toBeInTheDocument()
    expect(within(panel).getByText(/Outcome above is simulated/)).toBeInTheDocument()
  })
})
