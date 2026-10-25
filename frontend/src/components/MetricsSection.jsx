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

function Tile({ label, tone, children }) {
  return (
    <div className={`tile ${tone ? `tile-${tone}` : ''}`}>
      <div className="tile-value">{children}</div>
      <div className="tile-label">{label}</div>
    </div>
  )
}

export default function MetricsSection({ metrics }) {
  const { razorpay_data_provenance: prov, simulated_recovery_summary: sim, breakdown_by_failure_reason: byReason } = metrics
  const razorpayOrders = prov.razorpay_test_orders
  const localOrders = prov.local_orders

  return (
    <>
      {/* Provenance first, and never mixed with outcome numbers */}
      <div className="chips">
        <span className="chip chip-real">
          {razorpayOrders} real Razorpay test-mode order{razorpayOrders !== 1 ? 's' : ''}
        </span>
        <span className="chip chip-simulated">
          {localOrders} local order id{localOrders !== 1 ? 's' : ''} (no Razorpay call)
        </span>
      </div>

      <section className="panel" aria-labelledby="prov-title">
        <h2 className="panel-label" id="prov-title">Order provenance</h2>
        <p className="panel-note">{prov.note}</p>
        <div className="tiles">
          <Tile label="Real Razorpay test orders" tone="real"><AnimatedNumber value={razorpayOrders} /></Tile>
          <Tile label="Local order ids (no API call)"><AnimatedNumber value={localOrders} /></Tile>
        </div>
      </section>

      <section className="panel panel-sim" aria-labelledby="sim-title">
        <h2 className="panel-label" id="sim-title">Simulated recovery outcomes</h2>
        <p className="panel-note">{sim.note}</p>
        <div className="tiles">
          <Tile label="Batch size"><AnimatedNumber value={sim.batch_size} /></Tile>
          <Tile label="Simulated recoveries" tone="sim"><AnimatedNumber value={sim.recovered} /></Tile>
          <Tile label="Recovery rate" tone="sim"><AnimatedNumber value={sim.recovery_rate_pct} decimals={1} suffix="%" /></Tile>
          <Tile label="Simulated recovery value" tone="sim"><AnimatedNumber value={sim.total_amount_recovered_inr} decimals={2} prefix="₹" /></Tile>
          <Tile label="Total at risk"><AnimatedNumber value={sim.total_amount_at_risk_inr} decimals={2} prefix="₹" /></Tile>
          <Tile label="Pending customer action"><AnimatedNumber value={sim.pending_customer_action} /></Tile>
          <Tile label="Held (fraud, no action)" tone="danger">{sim.held_no_action_fraud}</Tile>
          <Tile label="Still failed" tone="danger">{sim.still_failed}</Tile>
        </div>
      </section>

      <section className="panel" aria-labelledby="reason-title">
        <h2 className="panel-label" id="reason-title">Breakdown by failure reason</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Failure reason</th>
                <th scope="col" className="num">Count</th>
                <th scope="col" className="num">Recovered (simulated)</th>
                <th scope="col" className="num">Rate</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(byReason).map(([reason, data]) => (
                <tr key={reason}>
                  <td>{reason.replace(/_/g, ' ')}</td>
                  <td className="num">{data.count}</td>
                  <td className="num">{data.recovered}</td>
                  <td className="num">{data.count ? Math.round((data.recovered / data.count) * 100) : 0}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
