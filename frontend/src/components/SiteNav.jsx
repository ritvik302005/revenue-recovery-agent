import { useEffect, useState } from 'react'

const LINKS = [
  { href: '/#story', label: 'How it works' },
  { href: '/#policy', label: 'Try the policy' },
  { href: '/dashboard', label: 'Evaluation', page: 'dashboard' },
  { href: '/#faq', label: 'FAQ' },
]

// One nav for every page. Links are real hrefs (they work without JS and
// with middle-click); a plain click is routed in-app by `navigate`. On
// narrow screens the links fold into a menu button.
export default function SiteNav({ current = 'landing', navigate }) {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  function go(e, href) {
    setOpen(false)
    if (!navigate || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
    e.preventDefault()
    navigate(href)
  }

  return (
    <header className="nav">
      <div className="nav-inner wrap">
        <a className="brand" href="/" onClick={(e) => go(e, '/')} aria-label="Recover, home">
          <span className="brand-mark" aria-hidden="true" />
          Recover
        </a>
        <button
          type="button"
          className="nav-toggle"
          aria-expanded={open}
          aria-controls="nav-links"
          onClick={() => setOpen((o) => !o)}
        >
          <span className="nav-toggle-bars" aria-hidden="true" />
          <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
        </button>
        <nav id="nav-links" className={`nav-links ${open ? 'is-open' : ''}`} aria-label="Main">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} onClick={(e) => go(e, l.href)}
               aria-current={l.page === current ? 'page' : undefined}>
              {l.label}
            </a>
          ))}
          <a className="btn btn-paper btn-sm nav-cta" href="/demo" onClick={(e) => go(e, '/demo')}
             aria-current={current === 'demo' ? 'page' : undefined}>
            Run the live demo
          </a>
        </nav>
      </div>
    </header>
  )
}
