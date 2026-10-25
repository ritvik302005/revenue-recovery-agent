import { useEffect, useState } from 'react'

/**
 * Animates a number counting up from 0 to `value` over `duration` ms.
 * Re-triggers whenever `value` changes (e.g. a new batch run).
 */
export function useCountUp(value, duration = 700) {
  const [display, setDisplay] = useState(0)

  useEffect(() => {
    let raf
    const start = performance.now()
    const from = 0
    const to = typeof value === 'number' ? value : 0
    // Nothing to count (e.g. not scrolled into view yet), or reduced motion:
    // show the value without running an animation frame loop.
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (to === from || reduced) {
      setDisplay(to)
      return
    }

    function tick(now) {
      const progress = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
      setDisplay(from + (to - from) * eased)
      if (progress < 1) raf = requestAnimationFrame(tick)
      else setDisplay(to)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  return display
}
