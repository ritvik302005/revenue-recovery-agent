import { useEffect, useState } from 'react'
import { apiFetch } from '../api.js'
import { parseTimestamp } from './useShowcaseCase.js'

/**
 * Backend health, for status chips that must describe the real state.
 * Returns { status: 'loading' | 'ready' | 'error', data }.
 */
export function useHealth() {
  const [state, setState] = useState({ status: 'loading', data: null })

  useEffect(() => {
    let cancelled = false
    apiFetch('/api/health')
      .then((data) => { if (!cancelled) setState({ status: 'ready', data }) })
      .catch(() => { if (!cancelled) setState({ status: 'error', data: null }) })
    return () => { cancelled = true }
  }, [])

  return state
}

export function timeAgo(iso, now = Date.now()) {
  const minutes = Math.round((now - parseTimestamp(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`
}

// The chip says only what /api/health actually knows: key mode, and the
// outcome of the latest real Razorpay call (health never probes Razorpay).
export function describeHealth(health, now = Date.now()) {
  if (health.status === 'loading') return { cls: 'chip-simulated', text: 'Checking backend…' }
  if (health.status === 'error') return { cls: 'chip-danger', text: 'Backend unreachable' }
  const h = health.data
  if (h.razorpay_key_mode === 'live') return { cls: 'chip-danger', text: 'Live Razorpay keys set: demo disabled (test mode only)' }
  if (!h.razorpay_keys_configured) return { cls: 'chip-danger', text: 'Razorpay keys not configured: live demo unavailable' }
  const ok = h.razorpay_last_success_at
  const failed = h.razorpay_last_failure_at
  if (failed && (!ok || parseTimestamp(failed) > parseTimestamp(ok))) {
    return { cls: 'chip-simulated', text: `Razorpay Test Mode: last call failed ${timeAgo(failed, now)}` }
  }
  if (ok) return { cls: 'chip-real', text: `Razorpay Test Mode: last call succeeded ${timeAgo(ok, now)}` }
  return { cls: 'chip-real', text: 'Razorpay Test Mode keys configured' }
}
