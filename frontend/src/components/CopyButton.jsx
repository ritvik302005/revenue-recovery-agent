import { useEffect, useState } from 'react'

// Copies a value (a test card number, a UPI ID) so it can be pasted into Checkout.
export default function CopyButton({ value, label = 'Copy', className = '' }) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 1600)
    return () => clearTimeout(t)
  }, [copied])

  async function copy() {
    try {
      await navigator.clipboard.writeText(value.replace(/\s/g, ''))
      setCopied(true)
    } catch {
      setCopied(false)     // clipboard blocked: the value is still on screen to type
    }
  }

  return (
    <button type="button" className={`copy-btn ${className}`} onClick={copy} aria-label={`${label}: ${value}`}>
      <span aria-live="polite">{copied ? 'Copied' : label}</span>
    </button>
  )
}
