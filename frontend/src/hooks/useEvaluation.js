import { useEffect, useState } from 'react'
import { apiFetch } from '../api.js'

/**
 * The published multi-seed batch evaluation (GET /api/evaluation).
 * Returns { status: 'loading' | 'ready' | 'error', data }.
 */
export function useEvaluation() {
  const [state, setState] = useState({ status: 'loading', data: null })

  useEffect(() => {
    let cancelled = false
    apiFetch('/api/evaluation')
      .then((data) => { if (!cancelled) setState({ status: 'ready', data }) })
      .catch(() => { if (!cancelled) setState({ status: 'error', data: null }) })
    return () => { cancelled = true }
  }, [])

  return state
}
