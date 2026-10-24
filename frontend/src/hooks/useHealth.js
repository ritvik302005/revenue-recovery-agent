import { useEffect, useState } from 'react'
import { API_BASE } from '../api.js'

/**
 * Backend health, for status chips that must describe the real state.
 * Returns { status: 'loading' | 'ready' | 'error', data }.
 */
export function useHealth() {
  const [state, setState] = useState({ status: 'loading', data: null })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/health`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => { if (!cancelled) setState({ status: 'ready', data }) })
      .catch(() => { if (!cancelled) setState({ status: 'error', data: null }) })
    return () => { cancelled = true }
  }, [])

  return state
}
