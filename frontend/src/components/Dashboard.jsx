import { useState } from 'react'
import MetricsSection from './MetricsSection.jsx'
import ResultsTable from './ResultsTable.jsx'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// Says what the run actually was, not what it might have been.
function describeRun(metrics) {
  if (!metrics || metrics.error) {
    return 'Runs a batch of synthetic failed payments through the rule-based recovery agent. ' +
      'Failure reasons are documented Razorpay codes assigned synthetically; recovery outcomes are simulated.'
  }
  const n = metrics.simulated_recovery_summary.batch_size
  const real = metrics.razorpay_data_provenance.razorpay_test_orders
  const orders = real === 0
    ? 'no real Razorpay orders (all order ids local)'
    : real === n
      ? `a real Razorpay test-mode order for each`
      : `${real} real Razorpay test-mode order${real !== 1 ? 's' : ''} and ${n - real} local order id${n - real !== 1 ? 's' : ''}`
  const seed = metrics.simulated_recovery_summary.seed
  return `Last run (seed ${seed}): ${n} synthetic failed payment${n !== 1 ? 's' : ''}, ${orders}. ` +
    'Recovery outcomes are simulated; the same seed reproduces the same run.'
}

export default function Dashboard({ onBack }) {
  const [metrics, setMetrics] = useState(null)
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [batchSize, setBatchSize] = useState(60)
  const [seed, setSeed] = useState(42)
  const [liveOrders, setLiveOrders] = useState(false)

  async function runBatch() {
    setLoading(true)
    setError(null)
    try {
      const runRes = await fetch(
        `${API_BASE}/api/batch/run?n=${batchSize}&seed=${seed}&try_live_orders=${liveOrders}`,
        { method: 'POST' }
      )
      if (!runRes.ok) throw new Error(`Batch run failed: ${runRes.status}`)
      const runData = await runRes.json()
      setResults(runData.results)

      const metricsRes = await fetch(`${API_BASE}/api/batch/metrics`)
      const metricsData = await metricsRes.json()
      setMetrics(metricsData)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <div className="header">
        <div>
          {onBack && (
            <button className="back-link" onClick={onBack}>
              ← Back to Overview
            </button>
          )}
          <h1 className="title">AI Revenue Recovery Agent — Batch Evaluation</h1>
          <p className="subtitle">{describeRun(metrics)}</p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <label style={{ display: 'grid', gap: 4, fontSize: 11, color: 'var(--text-dim)' }}>
            Batch size
            <input
              type="number"
              min={1}
              max={200}
              value={batchSize}
              onChange={(e) => setBatchSize(Number(e.target.value))}
              style={{
                width: 70, padding: '10px 8px', borderRadius: 8,
                border: '1px solid #332c22', background: '#1f1a15', color: '#f0e6d6'
              }}
            />
          </label>
          <label style={{ display: 'grid', gap: 4, fontSize: 11, color: 'var(--text-dim)' }}>
            Seed
            <input
              type="number"
              min={0}
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              style={{
                width: 80, padding: '10px 8px', borderRadius: 8,
                border: '1px solid #332c22', background: '#1f1a15', color: '#f0e6d6'
              }}
            />
          </label>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, color: 'var(--text-dim)', maxWidth: 190 }}>
            <input type="checkbox" checked={liveOrders} onChange={(e) => setLiveOrders(e.target.checked)} />
            Create real Razorpay test orders (first 5 only)
          </label>
          <button className="run-btn" onClick={runBatch} disabled={loading}>
            {loading ? 'Running…' : 'Run Batch'}
          </button>
        </div>
      </div>

      {error && (
        <div className="section" style={{ borderColor: '#c05b4d', color: '#c05b4d' }}>
          {error}
        </div>
      )}

      {!metrics && !loading && (
        <div className="empty-state">
          No batch run yet. Click "Run Batch" to generate a set of failed
          payments and let the agent classify, decide, and act on them.
        </div>
      )}

      {loading && !metrics && (
        <div className="empty-state loading">Running agent across batch…</div>
      )}

      {metrics && !metrics.error && (
        <>
          <MetricsSection metrics={metrics} />
          <ResultsTable results={results} />
        </>
      )}
    </div>
  )
}
