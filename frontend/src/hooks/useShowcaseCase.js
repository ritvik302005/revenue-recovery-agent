import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api.js'

/**
 * The one real recorded case shown on the landing page (latest completed
 * live demo, else a labelled batch record, else kind "none"). Re-fetched
 * when the tab becomes visible again, so a case recorded in another tab
 * appears without a reload.
 *
 * Returns { status: 'loading' | 'ready' | 'error', data, error }.
 */
export function useShowcaseCase() {
  const [state, setState] = useState({ status: 'loading', data: null, error: null })

  const load = useCallback(async () => {
    try {
      const data = await apiFetch('/api/showcase/case')
      setState({ status: 'ready', data, error: null })
    } catch (e) {
      setState((prev) => (prev.status === 'ready' ? prev : { status: 'error', data: null, error: e.message }))
    }
  }, [])

  useEffect(() => {
    load()
    const onVisible = () => { if (document.visibilityState === 'visible') load() }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [load])

  return state
}

export const humanize = (value) => (value ? String(value).replace(/_/g, ' ') : '—')

export const formatINR = (paise) =>
  `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

// Backend timestamps are UTC with a "Z"; records saved before P5-8 have no suffix.
export const parseTimestamp = (value) =>
  new Date(/(Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`)
