import { Fragment, useState } from 'react'

function formatINR(paise) {
  return `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
}

export default function ResultsTable({ results }) {
  const [expandedId, setExpandedId] = useState(null)

  if (!results || results.length === 0) return null

  return (
    <div className="section">
      <div className="section-label" style={{ color: '#d4a35a' }}>
        Batch Results &amp; Audit Trail
      </div>
      <p className="section-note">
        Click a row (or focus its payment id and press Enter) to see the agent's full reasoning for that payment —
        classification, action selection, safety-check, execution, and any
        replan/escalation.
      </p>
      <table>
        <thead>
          <tr>
            <th>Payment</th>
            <th>Amount</th>
            <th>Failure Reason</th>
            <th>Source</th>
            <th>Action Taken</th>
            <th>Attempts</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => {
            const expanded = expandedId === r.payment_id
            const toggle = () => setExpandedId(expanded ? null : r.payment_id)
            const detailId = `audit-${r.payment_id}`
            return (
            <Fragment key={r.payment_id}>
              <tr className="clickable" onClick={toggle}>
                <td>
                  {/* The keyboard and screen-reader control; the row click is a mouse shortcut. */}
                  <button
                    type="button"
                    className="row-toggle"
                    aria-expanded={expanded}
                    aria-controls={detailId}
                    onClick={(e) => { e.stopPropagation(); toggle() }}
                  >
                    <span aria-hidden="true">{expanded ? '▾' : '▸'}</span> {r.payment_id}
                  </button>
                </td>
                <td>{formatINR(r.amount)}</td>
                <td>{r.failure_reason.replace(/_/g, ' ')}</td>
                <td>
                  <span
                    className={
                      r.razorpay_source === 'razorpay_test_order'
                        ? 'badge badge-source-live'
                        : 'badge badge-source-tagged'
                    }
                  >
                    {r.razorpay_source === 'razorpay_test_order' ? 'RAZORPAY TEST ORDER' : 'LOCAL ORDER'}
                  </span>
                </td>
                <td>{r.action_taken.replace(/_/g, ' ')}</td>
                <td>{r.attempt_count}</td>
                <td>
                  <span className={`badge badge-${r.outcome}`}>
                    {r.outcome === 'recovered' ? 'recovered (simulated)' : r.outcome.replace(/_/g, ' ')}
                  </span>
                </td>
              </tr>
              {expanded && (
                <tr id={detailId}>
                  <td colSpan={7}>
                    <div className="audit-panel">
                      {r.raw_error_code && (
                        <div style={{ marginBottom: 10, color: '#a89a86' }}>
                          Documented Razorpay error code (assigned synthetically): <code>{r.raw_error_code}</code>
                          {r.razorpay_order_id && (
                            <> · Order: <code>{r.razorpay_order_id}</code></>
                          )}
                        </div>
                      )}
                      {r.audit_trail.map((step, i) => (
                        <div className="audit-step" key={i}>
                          <div className="audit-step-name">{step.step}</div>
                          <div>{step.detail}</div>
                        </div>
                      ))}
                      <div style={{ marginTop: 10, fontSize: 12, color: '#c47f3a' }}>
                        ⚠ Outcome above is simulated — Razorpay test mode cannot
                        headlessly simulate a customer's retry succeeding.
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
