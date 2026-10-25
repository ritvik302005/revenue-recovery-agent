import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { mockFetch } from '../test/mockFetch.js'
import HeadlineMetrics from './HeadlineMetrics.jsx'

// Show final values instead of animating from 0, as if already scrolled into view.
vi.mock('../hooks/useCountUp.js', () => ({ useCountUp: (value) => value }))
vi.mock('../hooks/useReveal.js', () => ({ useReveal: () => [{ current: null }, true] }))

const EVALUATION = {
  seeds: { first: 1, last: 500, count: 500 },
  batch_size: 60,
  payments_simulated: 30000,
  max_attempts: 3,
  recovery_rate_pct: { mean: 68.3, mean_ci95: [67.8, 68.8], single_run_range95: [56.7, 78.3] },
  safety_gate: { fraud_holds: 980, max_attempt_stops: 3458 },
}

describe('HeadlineMetrics', () => {
  it('shows the published evaluation, labelled as a simulation', async () => {
    mockFetch({ '/api/evaluation': { body: EVALUATION } })
    render(<HeadlineMetrics />)
    expect(await screen.findByText('68.3%')).toBeInTheDocument()
    expect(screen.getByText('30,000')).toBeInTheDocument()
    expect(screen.getByText('980')).toBeInTheDocument()
    expect(screen.getByText('3,458')).toBeInTheDocument()
    expect(screen.getByText(/95% CI 67.8%–68.8%/)).toBeInTheDocument()
    expect(screen.getByText(/This is a simulation/)).toBeInTheDocument()
    expect(screen.getByText(/between 56.7% and 78.3%/)).toBeInTheDocument()
  })

  it('shows no numbers while loading', () => {
    mockFetch({ '/api/evaluation': () => new Promise(() => {}) })
    render(<HeadlineMetrics />)
    expect(screen.getByText(/Loading the batch evaluation/)).toBeInTheDocument()
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument()
  })

  it('says when the evaluation is unavailable instead of inventing numbers', async () => {
    mockFetch({ '/api/evaluation': { status: 404, body: { detail: 'No evaluation yet.' } } })
    render(<HeadlineMetrics />)
    expect(await screen.findByText(/isn't available right now/)).toBeInTheDocument()
    expect(screen.queryByText('68.3%')).not.toBeInTheDocument()
  })
})
