import { useCountUp } from '../hooks/useCountUp.js'

function AnimatedNumber({ value, decimals = 0, prefix = '', suffix = '' }) {
  const animated = useCountUp(value)
  return (
    <>
      {prefix}
      {animated.toLocaleString('en-IN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </>
  )
}

export default function MetricsSection({ metrics }) {
  const { razorpay_data_provenance: prov, simulated_recovery_summary: sim, breakdown_by_failure_reason: byReason } = metrics

  const liveCount = prov.live_test_mode_orders
  const taggedCount = prov.real_order_tagged_failure_orders

  return (
    <>
      {/* PROVENANCE BANNER — always visible, never mixed with outcome numbers */}
      <div className="provenance-banner">
        <div className="provenance-chip chip-real">
          ● {liveCount} order{liveCount !== 1 ? 's' : ''} from Razorpay TEST MODE • Connected Orders API
        </div>
        <div className="provenance-chip chip-simulated">
          ● {taggedCount} order{taggedCount !== 1 ? 's' : ''} using Razorpay's documented error
          taxonomy (offline fallback — no live API call)
        </div>
      </div>

      {/* REAL DATA PROVENANCE */}
      <div className="section">
        <div className="section-label label-real">Razorpay Data Provenance (Real)</div>
        <p className="section-note">{prov.note}</p>
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={liveCount} /></div>
            <div className="metric-label">Razorpay Test Mode orders</div>
          </div>
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={taggedCount} /></div>
            <div className="metric-label">Real-error-taxonomy (offline) orders</div>
          </div>
        </div>
      </div>

      {/* SIMULATED RECOVERY OUTCOMES */}
      <div className="section">
        <div className="section-label label-simulated">Simulated Recovery Outcomes</div>
        <p className="section-note">{sim.note}</p>
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={sim.batch_size} /></div>
            <div className="metric-label">Batch size</div>
          </div>
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={sim.recovered} /></div>
            <div className="metric-label">Simulated recoveries</div>
          </div>
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={sim.recovery_rate_pct} decimals={1} suffix="%" /></div>
            <div className="metric-label">Recovery rate</div>
          </div>
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={sim.total_amount_recovered_inr} decimals={2} prefix="₹" /></div>
            <div className="metric-label">Simulated recovery value</div>
          </div>
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={sim.total_amount_at_risk_inr} decimals={2} prefix="₹" /></div>
            <div className="metric-label">Total at risk</div>
          </div>
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={sim.pending_customer_action} /></div>
            <div className="metric-label">Pending customer action</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{sim.held_no_action_fraud}</div>
            <div className="metric-label">Held (fraud, no action)</div>
          </div>
          <div className="metric-card">
            <div className="metric-value">{sim.still_failed}</div>
            <div className="metric-label">Still failed</div>
          </div>
        </div>
      </div>

      {/* BREAKDOWN BY FAILURE REASON */}
      <div className="section">
        <div className="section-label" style={{ color: '#d4a35a' }}>Breakdown by Failure Reason</div>
        <table>
          <thead>
            <tr>
              <th>Failure Reason</th>
              <th>Count</th>
              <th>Recovered (simulated)</th>
              <th>Rate</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(byReason).map(([reason, data]) => (
              <tr key={reason}>
                <td>{reason.replace(/_/g, ' ')}</td>
                <td>{data.count}</td>
                <td>{data.recovered}</td>
                <td>{data.count ? Math.round((data.recovered / data.count) * 100) : 0}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
