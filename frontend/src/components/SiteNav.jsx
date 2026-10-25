const LINKS = [
  { href: '/#how-it-works', label: 'How it works' },
  { href: '/dashboard', label: 'Evaluation', page: 'dashboard' },
  { href: '/#audit-tape', label: 'Audit tape' },
]

// One nav for every page. Links are real hrefs (they work without JS and
// with middle-click); a plain click is routed in-app by `navigate`.
export default function SiteNav({ current = 'landing', navigate }) {
  function go(e, href) {
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
        <nav className="nav-links" aria-label="Main">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} onClick={(e) => go(e, l.href)}
               aria-current={l.page === current ? 'page' : undefined}>
              {l.label}
            </a>
          ))}
        </nav>
        <a className="btn btn-paper btn-sm" href="/demo" onClick={(e) => go(e, '/demo')}
           aria-current={current === 'demo' ? 'page' : undefined}>
          Run the live demo
        </a>
      </div>
    </header>
  )
}
