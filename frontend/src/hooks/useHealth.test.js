import { describe, expect, it } from 'vitest'
import { describeHealth } from './useHealth.js'

const NOW = Date.parse('2026-10-25T12:00:00Z')
const ready = (data) => ({ status: 'ready', data: { razorpay_keys_configured: true, razorpay_key_mode: 'test', ...data } })

describe('describeHealth (landing status chip)', () => {
  it('loading and unreachable', () => {
    expect(describeHealth({ status: 'loading' }).text).toBe('Checking backend…')
    expect(describeHealth({ status: 'error' })).toEqual({ cls: 'chip-danger', text: 'Backend unreachable' })
  })

  it('warns about live keys before anything else', () => {
    const chip = describeHealth(ready({ razorpay_key_mode: 'live', razorpay_keys_configured: false }), NOW)
    expect(chip.cls).toBe('chip-danger')
    expect(chip.text).toMatch(/Live Razorpay keys/)
  })

  it('missing keys', () => {
    expect(describeHealth(ready({ razorpay_keys_configured: false, razorpay_key_mode: null }), NOW).text)
      .toBe('Razorpay keys not configured: live demo unavailable')
  })

  it('keys but no call yet: claims nothing about connectivity', () => {
    expect(describeHealth(ready({}), NOW).text).toBe('Razorpay Test Mode keys configured')
  })

  it('newest outcome wins', () => {
    const ok = describeHealth(ready({ razorpay_last_success_at: '2026-10-25T11:58:00+00:00',
                                      razorpay_last_failure_at: '2026-10-25T10:00:00+00:00' }), NOW)
    expect(ok).toEqual({ cls: 'chip-real', text: 'Razorpay Test Mode: last call succeeded 2 min ago' })

    const failed = describeHealth(ready({ razorpay_last_success_at: '2026-10-25T09:00:00+00:00',
                                          razorpay_last_failure_at: '2026-10-25T11:00:00+00:00' }), NOW)
    expect(failed).toEqual({ cls: 'chip-simulated', text: 'Razorpay Test Mode: last call failed 1 h ago' })
  })
})
