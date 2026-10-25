import { useEffect, useState } from 'react'
import MetricsSection from './MetricsSection.jsx'
import ResultsTable from './ResultsTable.jsx'
import { apiFetch } from '../api.js'
import SiteNav from './SiteNav.jsx'

const MAX_BATCH_SIZE = 500        // backend: n ≤ 500
const MAX_SEED = 2 ** 31 - 1      // backend: 0 ≤ seed ≤ 2^31 − 1

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

export default function Dashboard({ navigate }) {
  const [metrics, setMetrics] = useState(null)
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [batchSize, setBatchSize] = useState(60)
  const [seed, setSeed] = useState(42)
  const [liveOrders, setLiveOrders] = useState(false)
  const [checkedSaved, setCheckedSaved] = useState(false)

  // Show the last saved batch on open, instead of an empty page until "Run Batch".
  useEffect(() => {
    let cancelled = false
    apiFetch('/api/batch/results')
      .then(async (saved) => {
        if (cancelled || !saved.count) return
        const savedMetrics = await apiFetch('/api/batch/metrics')
        if (cancelled) return
        setResults(saved.results)
        setMetrics(savedMetrics)
        if (saved.seed !== null) setSeed(saved.seed)
        setBatchSize(saved.count)
      })
      .catch((e) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setCheckedSaved(true) })
    return () => { cancelled = true }
  }, [])

  async function runBatch() {
    // Same limits as POST /api/batch/run, so a typo doesn't become a 422.
    if (!Number.isInteger(batchSize) || batchSize < 1 || batchSize > MAX_BATCH_SIZE) {
      setError(`Batch size must be a whole number from 1 to ${MAX_BATCH_SIZE}.`)
      return
    }
    if (!Number.isInteger(seed) || seed < 0 || seed > MAX_SEED) {
      setError(`Seed must be a whole number from 0 to ${MAX_SEED}.`)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const runData = await apiFetch('/api/batch/run', {
        method: 'POST',
        session: true,
        params: { n: batchSize, seed, try_live_orders: liveOrders },
      })
      setResults(runData.results)
      setMetrics(await apiFetch('/api/batch/metrics'))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="site">
      <SiteNav current="dashboard" navigate={navigate} />
      <main id="main" className="page wrap">
        <header className="page-head">
          <p className="eyebrow">Batch evaluation · simulated outcomes</p>
          <h1 className="display page-title">Run the agent on a batch</h1>
          <p className="page-lede">{describeRun(metrics)}</p>
        </header>

        {/* noValidate: runBatch() checks the limits and shows one clear message */}
        <form className="run-form" noValidate onSubmit={(e) => { e.preventDefault(); runBatch() }}>
          <label className="field">
            <span>Batch size</span>
            <input className="input" type="number" min={1} max={MAX_BATCH_SIZE} step={1}
                   value={batchSize} onChange={(e) => setBatchSize(Number(e.target.value))} />
          </label>
          <label className="field">
            <span>Seed</span>
            <input className="input input-wide" type="number" min={0} max={MAX_SEED} step={1}
                   value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
          </label>
          <label className="check">
            <input type="checkbox" checked={liveOrders} onChange={(e) => setLiveOrders(e.target.checked)} />
            <span>Create real Razorpay test orders (first 5 only)</span>
          </label>
          <button className="btn btn-paper" type="submit" disabled={loading}>
            {loading ? 'Running…' : 'Run batch'}
          </button>
        </form>

        {error && <div className="alert" role="alert">{error}</div>}

        {!metrics && !loading && checkedSaved && (
          <p className="empty">
            No batch has been run yet. Choose a size and a seed, then run one: the agent
            classifies, decides and acts on each synthetic failed payment.
          </p>
        )}

        {loading && !metrics && <p className="empty">Running the agent across the batch…</p>}

        {metrics && !metrics.error && (
          <>
            <MetricsSection metrics={metrics} />
            <ResultsTable results={results} />
          </>
        )}
      </main>
    </div>
  )
}
