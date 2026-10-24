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

  const razorpayOrders = prov.razorpay_test_orders
  const localOrders = prov.local_orders

  return (
    <>
      {/* PROVENANCE BANNER — always visible, never mixed with outcome numbers */}
      <div className="provenance-banner">
        <div className="provenance-chip chip-real">
          ● {razorpayOrders} real Razorpay test-mode order{razorpayOrders !== 1 ? 's' : ''}
        </div>
        <div className="provenance-chip chip-simulated">
          ● {localOrders} local order id{localOrders !== 1 ? 's' : ''} (no Razorpay call)
        </div>
      </div>

      {/* ORDER PROVENANCE */}
      <div className="section">
        <div className="section-label label-real">Order Provenance</div>
        <p className="section-note">{prov.note}</p>
        <div className="metrics-grid">
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={razorpayOrders} /></div>
            <div className="metric-label">Real Razorpay test orders</div>
          </div>
          <div className="metric-card">
            <div className="metric-value"><AnimatedNumber value={localOrders} /></div>
            <div className="metric-label">Local order ids (no API call)</div>
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
