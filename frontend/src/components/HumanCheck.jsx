import { useEffect, useRef } from 'react'
import { mountTurnstile, turnstileEnabled, unmountTurnstile } from '../turnstile.js'

// Hosts the Turnstile widget on pages that create sessions. Usually
// invisible; Cloudflare shows a check only when it needs the visitor to act.
export default function HumanCheck() {
  const ref = useRef(null)

  useEffect(() => {
    if (!turnstileEnabled || !ref.current) return
    mountTurnstile(ref.current).catch(() => {})
    return () => unmountTurnstile()
  }, [])

  if (!turnstileEnabled) return null
  return <div className="human-check" ref={ref} />
}
