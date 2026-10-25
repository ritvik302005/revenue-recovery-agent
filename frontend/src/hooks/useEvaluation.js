import { useEffect, useState } from 'react'
import { API_BASE } from '../api.js'

/**
 * The published multi-seed batch evaluation (GET /api/evaluation).
 * Returns { status: 'loading' | 'ready' | 'error', data }.
 */
export function useEvaluation() {
  const [state, setState] = useState({ status: 'loading', data: null })

  useEffect(() => {
    let cancelled = false
    fetch(`${API_BASE}/api/evaluation`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data) => { if (!cancelled) setState({ status: 'ready', data }) })
      .catch(() => { if (!cancelled) setState({ status: 'error', data: null }) })
    return () => { cancelled = true }
  }, [])

  return state
}
