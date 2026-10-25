import { useState, useEffect, useCallback } from 'react'
import Landing from './components/Landing.jsx'
import Dashboard from './components/Dashboard.jsx'
import LiveDemo from './components/LiveDemo.jsx'

function pathToView(path) {
  if (path === '/demo') return 'demo'
  if (path === '/dashboard') return 'dashboard'
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
      {view === 'demo' ? <LiveDemo navigate={navigate} />
        : view === 'dashboard' ? <Dashboard navigate={navigate} />
        : <Landing navigate={navigate} onEnterDemo={() => navigate('/demo')} onEnterDashboard={() => navigate('/dashboard')} />}
    </>
  )
}
