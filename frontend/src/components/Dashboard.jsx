import { useState } from 'react'
import MetricsSection from './MetricsSection.jsx'
import ResultsTable from './ResultsTable.jsx'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function Dashboard({ onBack }) {
  const [metrics, setMetrics] = useState(null)
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [batchSize, setBatchSize] = useState(60)

  async function runBatch() {
    setLoading(true)
    setError(null)
    try {
      const runRes = await fetch(
        `${API_BASE}/api/batch/run?n=${batchSize}&try_live_orders=true`,
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
          <p className="subtitle">
            A controlled 60-case batch evaluation with real Razorpay Test Mode
            order provenance and simulated recovery outcomes.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
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
