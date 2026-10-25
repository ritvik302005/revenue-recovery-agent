import { Fragment, useState } from 'react'
import { formatINR, humanize } from '../hooks/useShowcaseCase.js'

const OUTCOME_TONE = { recovered: 'sim', pending_customer_action: 'plain', still_failed: 'danger', held_no_action: 'danger' }

export default function ResultsTable({ results }) {
  const [expandedId, setExpandedId] = useState(null)

  if (!results || results.length === 0) return null

  return (
    <section className="panel" aria-labelledby="results-title">
      <h2 className="panel-label" id="results-title">Batch results and audit trails</h2>
      <p className="panel-note">
        Open a row (click it, or focus its payment id and press Enter) to read the agent's
        steps for that payment: classification, action, safety check, execution and any escalation.
      </p>
      <div className="table-wrap">
        <table className="table table-results">
          <thead>
            <tr>
              <th scope="col">Payment</th>
              <th scope="col" className="num">Amount</th>
              <th scope="col">Failure reason</th>
              <th scope="col">Order</th>
              <th scope="col">Action taken</th>
              <th scope="col" className="num">Attempts</th>
              <th scope="col">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => {
              const expanded = expandedId === r.payment_id
              const toggle = () => setExpandedId(expanded ? null : r.payment_id)
              const detailId = `audit-${r.payment_id}`
              const realOrder = r.razorpay_source === 'razorpay_test_order'
              return (
                <Fragment key={r.payment_id}>
                  <tr className={`row ${expanded ? 'is-open' : ''}`} onClick={toggle}>
                    <td>
                      {/* The keyboard and screen-reader control; the row click is a mouse shortcut. */}
                      <button
                        type="button"
                        className="row-toggle"
                        aria-expanded={expanded}
                        aria-controls={detailId}
                        onClick={(e) => { e.stopPropagation(); toggle() }}
                      >
                        <span className="row-caret" aria-hidden="true" /> {r.payment_id}
                      </button>
                    </td>
                    <td className="num">{formatINR(r.amount)}</td>
                    <td>{humanize(r.failure_reason)}</td>
                    <td><span className={`badge ${realOrder ? 'badge-real' : 'badge-plain'}`}>{realOrder ? 'Razorpay test order' : 'Local id'}</span></td>
                    <td>{humanize(r.action_taken)}</td>
                    <td className="num">{r.attempt_count}</td>
                    <td>
                      <span className={`badge badge-${OUTCOME_TONE[r.outcome] || 'plain'}`}>
                        {r.outcome === 'recovered' ? 'recovered (simulated)' : humanize(r.outcome)}
                      </span>
                    </td>
                  </tr>
                  {expanded && (
                    <tr id={detailId} className="row-detail">
                      <td colSpan={7}>
                        <div className="detail">
                          {r.raw_error_code && (
                            <p className="detail-meta">
                              Documented Razorpay error code (assigned synthetically): <code>{r.raw_error_code}</code>
                              {r.razorpay_order_id && <> · Order <code>{r.razorpay_order_id}</code></>}
                            </p>
                          )}
                          <ol className="detail-steps">
                            {r.audit_trail.map((step, i) => (
                              <li key={i}>
                                <span className="tape-step">{humanize(step.step)}</span>
                                <span>{step.detail}</span>
                              </li>
                            ))}
                          </ol>
                          <p className="detail-sim">
                            Outcome above is simulated: Razorpay Test Mode can't stand in for a customer
                            successfully retrying a payment, so batch outcomes come from the probability model.
                          </p>
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
    </section>
  )
}
