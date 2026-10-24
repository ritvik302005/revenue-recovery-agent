import { useEffect, useRef } from 'react'

export default function RevenueNetworkBackground() {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const pointer = { x: 0, y: 0, previousX: 0 }
    let rotation = -0.45
    const idleVelocity = 0.0032
    let velocity = idleVelocity
    let frame

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = window.innerWidth * ratio
      canvas.height = window.innerHeight * ratio
      canvas.style.width = `${window.innerWidth}px`
      canvas.style.height = `${window.innerHeight}px`
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
    }
    const move = (event) => {
      pointer.x = event.clientX / window.innerWidth - 0.5
      pointer.y = event.clientY / window.innerHeight - 0.5
      velocity += (pointer.x - pointer.previousX) * 0.22
      pointer.previousX = pointer.x
    }
    const ring = (cx, cy, rx, ry, stroke, width) => {
      ctx.beginPath()
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2)
      ctx.strokeStyle = stroke
      ctx.lineWidth = width
      ctx.stroke()
    }
    const drawCoin = (w, h) => {
      const size = Math.max(280, Math.min(w, h) * 0.69)
      const cx = w * (0.76 + pointer.x * 0.035)
      const cy = h * (0.43 + pointer.y * 0.028)
      const face = Math.abs(Math.cos(rotation))
      const tilt = Math.sin(rotation)
      const rx = Math.max(20, size * 0.5 * face)
      const ry = size * 0.5
      const depth = 22 + (1 - face) * 18

      ctx.save()
      ctx.filter = 'blur(4px)'
      ctx.globalAlpha = 0.52
      for (let layer = 7; layer >= 0; layer -= 1) {
        ctx.beginPath()
        ctx.ellipse(cx + layer * 1.4, cy + layer * 1.5, rx, ry, 0, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${30 + layer * 5}, ${19 + layer * 4}, ${66 + layer * 8}, .42)`
        ctx.fill()
      }
      ctx.restore()

      ctx.save()
      ctx.filter = 'blur(2.2px)'
      const coinGradient = ctx.createRadialGradient(cx - rx * 0.26, cy - ry * 0.3, 4, cx, cy, Math.max(rx, ry))
      coinGradient.addColorStop(0, '#fff6cf')
      coinGradient.addColorStop(.18, '#d6aa48')
      coinGradient.addColorStop(.56, '#8b5b17')
      coinGradient.addColorStop(1, '#24130b')
      ctx.beginPath()
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2)
      ctx.fillStyle = coinGradient
      ctx.fill()
      ring(cx, cy, rx * .9, ry * .9, 'rgba(255,235,160,.48)', Math.max(1, size * .012))
      ring(cx, cy, rx * .75, ry * .75, 'rgba(65,36,10,.45)', Math.max(1, size * .008))

      if (face > .15) {
        ctx.save()
        ctx.beginPath()
        ctx.ellipse(cx, cy, rx * .72, ry * .72, 0, 0, Math.PI * 2)
        ctx.clip()
        ctx.globalAlpha = .45 + face * .25
        ctx.fillStyle = '#301b08'
        ctx.font = `900 ${size * .67}px Georgia, serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.scale(face, 1)
        ctx.fillText('$', cx / face, cy + size * .02)
        ctx.restore()
      }

      ctx.globalAlpha = .34
      for (let index = 0; index < 22; index += 1) {
        const angle = (index / 22) * Math.PI * 2 + rotation * .22
        const x = cx + Math.cos(angle) * rx * .81
        const y = cy + Math.sin(angle) * ry * .81
        ctx.beginPath()
        ctx.arc(x, y, Math.max(1.2, size * .009), 0, Math.PI * 2)
        ctx.fillStyle = '#ffe38a'
        ctx.fill()
      }
      ctx.restore()

      ctx.save()
      ctx.filter = 'blur(13px)'
      ctx.globalAlpha = .22
      ctx.fillStyle = '#bd8aff'
      ctx.beginPath()
      ctx.ellipse(cx - rx * .18, cy - ry * .44, rx * .62, ry * .16, -.4, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
      ring(cx + depth * .08, cy + depth * .08, rx, ry, 'rgba(241,199,90,.25)', Math.max(1, size * .012))
    }
    const draw = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      ctx.clearRect(0, 0, w, h)
      velocity += (idleVelocity - velocity) * .018
      rotation += velocity
      drawCoin(w, h)
      frame = requestAnimationFrame(draw)
    }

    resize()
    window.addEventListener('resize', resize)
    window.addEventListener('pointermove', move, { passive: true })
    frame = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(frame); window.removeEventListener('resize', resize); window.removeEventListener('pointermove', move) }
  }, [])

  return <canvas ref={canvasRef} className="revenue-network-bg revenue-coin-bg" aria-hidden="true" />
}
