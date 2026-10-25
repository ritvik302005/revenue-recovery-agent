import { useState, useEffect, useCallback } from 'react'
import Landing from './components/Landing.jsx'
import Dashboard from './components/Dashboard.jsx'
import LiveDemo from './components/LiveDemo.jsx'
import RecoverPage from './components/RecoverPage.jsx'
import LegalPage from './components/LegalPage.jsx'

const RECOVER_PATH = /^\/recover\/(rr_[A-Za-z0-9_-]{20,64})$/

function pathToView(path) {
  if (path === '/demo') return 'demo'
  if (path === '/dashboard') return 'dashboard'
  if (RECOVER_PATH.test(path)) return 'recover'
  if (path === '/legal') return 'legal'
  return 'landing'
}

function scrollToHash() {
  const id = window.location.hash.slice(1)
  if (id) document.getElementById(id)?.scrollIntoView({ block: 'start' })
  else window.scrollTo(0, 0)
}

export default function App() {
  const [view, setView] = useState(() => pathToView(window.location.pathname))

  useEffect(() => {
    const onPopState = () => setView(pathToView(window.location.pathname))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  // Accepts "/", "/demo", "/dashboard" and "/#section".
  const navigate = useCallback((href) => {
    window.history.pushState({}, '', href)
    setView(pathToView(window.location.pathname))
    // After the new view renders, go to its #section (or the top).
    requestAnimationFrame(scrollToHash)
  }, [])

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      {view === 'recover' ? <RecoverPage token={window.location.pathname.match(RECOVER_PATH)[1]} />
        : view === 'legal' ? <LegalPage navigate={navigate} />
        : view === 'demo' ? <LiveDemo navigate={navigate} />
        : view === 'dashboard' ? <Dashboard navigate={navigate} />
        : <Landing navigate={navigate} onEnterDemo={() => navigate('/demo')} onEnterDashboard={() => navigate('/dashboard')} />}
    </>
  )
}
