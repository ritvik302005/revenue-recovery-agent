import { useEffect, useRef } from 'react'

/**
 * Tilts an element a few degrees toward the pointer by setting --tilt-x /
 * --tilt-y (in degrees) on it. Only on fine pointers, never under reduced
 * motion, and only does work while the pointer moves over the element.
 */
export function usePointerTilt(maxDegrees = 4) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el || !window.matchMedia) return
    const ok = window.matchMedia('(pointer: fine) and (prefers-reduced-motion: no-preference)')
    if (!ok.matches) return

    let frame = 0
    let pending = null
    const apply = () => {
      frame = 0
      if (!pending) return
      el.style.setProperty('--tilt-x', `${pending.x.toFixed(2)}deg`)
      el.style.setProperty('--tilt-y', `${pending.y.toFixed(2)}deg`)
    }
    const onMove = (e) => {
      const r = el.getBoundingClientRect()
      const dx = (e.clientX - r.left) / r.width - 0.5
      const dy = (e.clientY - r.top) / r.height - 0.5
      pending = { x: -dy * 2 * maxDegrees, y: dx * 2 * maxDegrees }
      if (!frame) frame = requestAnimationFrame(apply)
    }
    const onLeave = () => {
      pending = { x: 0, y: 0 }
      if (!frame) frame = requestAnimationFrame(apply)
    }
    el.addEventListener('pointermove', onMove)
    el.addEventListener('pointerleave', onLeave)
    return () => {
      el.removeEventListener('pointermove', onMove)
      el.removeEventListener('pointerleave', onLeave)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [maxDegrees])

  return ref
}
