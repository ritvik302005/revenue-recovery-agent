import { useState, useEffect, useCallback } from 'react'
import Landing from './components/Landing.jsx'
import Dashboard from './components/Dashboard.jsx'
import LiveDemo from './components/LiveDemo.jsx'
import RevenueNetworkBackground from './components/RevenueNetworkBackground.jsx'

function pathToView(path) {
  if (path === '/demo') return 'demo'
  if (path === '/dashboard') return 'dashboard'
  return 'landing'
}

export default function App() {
  const [view, setView] = useState(() => pathToView(window.location.pathname))

  useEffect(() => {
    const onPopState = () => setView(pathToView(window.location.pathname))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((path) => {
    window.history.pushState({}, '', path)
    setView(pathToView(path))
  }, [])

  return (
    <>
      <RevenueNetworkBackground />
      {view === 'demo' ? <LiveDemo onBack={() => navigate('/dashboard')} /> : view === 'dashboard' ? <Dashboard onBack={() => navigate('/')} /> : <Landing onEnterDemo={() => navigate('/demo')} onEnterDashboard={() => navigate('/dashboard')} />}
    </>
  )
}
