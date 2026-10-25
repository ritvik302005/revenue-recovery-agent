import { useReveal } from '../hooks/useReveal.js'
import { useShowcaseCase } from '../hooks/useShowcaseCase.js'
import { useHealth, describeHealth } from '../hooks/useHealth.js'
import ReceiptPrinter from './ReceiptPrinter.jsx'
import AgentJourney from './AgentJourney.jsx'
import HeadlineMetrics from './HeadlineMetrics.jsx'
import AuditTrailVisual from './AuditTrailVisual.jsx'
import SiteNav from './SiteNav.jsx'

function Reveal({ children, className = '', as: Tag = 'div', ...rest }) {
  const [ref, visible] = useReveal()
  return (
    <Tag ref={ref} className={`reveal ${visible ? 'is-visible' : ''} ${className}`} {...rest}>
      {children}
    </Tag>
  )
}

function SectionHead({ id, title, children }) {
  return (
    <div className="section-head">
      <h2 className="display section-title" id={id}>{title}</h2>
      {children && <p className="section-intro">{children}</p>}
    </div>
  )
}

const REAL_LINES = [
  ['Order', 'Created on Razorpay Test Mode by the server'],
  ['Failure', 'A real Checkout decline with its real error_reason'],
  ['Recovery', 'Counts only if Razorpay reports the payment captured and the Checkout signature verifies'],
]
const SIMULATED_LINES = [
  ['Order', 'A local id (real test orders are optional, first 5 only)'],
  ['Failure', 'A documented Razorpay code, assigned by a generator'],
  ['Outcome', 'Drawn from an illustrative probability table'],
]

function EvidenceSlip({ tone, title, lines, foot }) {
  return (
    <div className={`slip slip-${tone}`}>
      <div className="slip-head"><span className="slip-dot" aria-hidden="true" />{title}</div>
      <dl className="slip-lines">
        {lines.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
        ))}
      </dl>
      <p className="slip-foot">{foot}</p>
    </div>
  )
}

export default function Landing({ onEnterDemo, onEnterDashboard, navigate }) {
  const showcase = useShowcaseCase()
  const health = useHealth()
  const keyChip = describeHealth(health)

  return (
    <div className="site">
      <SiteNav current="landing" navigate={navigate} />

      <main id="main">
        <section className="hero wrap" id="overview" aria-labelledby="hero-title">
          <div className="hero-text">
            <p className="eyebrow">Rule-based payment recovery · Razorpay Test Mode</p>
            <h1 className="display hero-title" id="hero-title">Failed payments, recovered on the record.</h1>
            <p className="lede">
              When a Razorpay payment fails, the agent reads the real error, picks a
              recovery action from a fixed policy, runs it past hard safety rules
              (fraud holds and a three-attempt retry budget) and writes every
              decision down. The rules are lookup tables, not a model; LangGraph runs the steps.
            </p>
            <div className="cta-row">
              <button className="btn btn-paper" onClick={onEnterDemo}>Run the live demo</button>
              <button className="btn btn-ghost" onClick={onEnterDashboard}>See the batch evaluation</button>
            </div>
            <p className={`status ${keyChip.cls}`} role="status">
              <span className="status-dot" aria-hidden="true" />{keyChip.text}
            </p>
          </div>
          <ReceiptPrinter showcase={showcase} onEnterDemo={onEnterDemo} />
        </section>

        <Reveal as="section" className="wrap block" id="evidence" aria-labelledby="evidence-title">
          <SectionHead id="evidence-title" title="Two kinds of evidence">
            Everything on this site is one of these two. They never share a number.
          </SectionHead>
          <div className="slips">
            <EvidenceSlip tone="real" title="Real · Razorpay Test Mode" lines={REAL_LINES}
              foot="One payment, end to end. This is what the live demo produces." />
            <EvidenceSlip tone="sim" title="Simulated · batch evaluation" lines={SIMULATED_LINES}
              foot="Measures the agent's decisions at scale. Never shown as money recovered." />
          </div>
        </Reveal>

        <Reveal as="section" className="wrap block" id="evaluation" aria-labelledby="evaluation-title">
          <SectionHead id="evaluation-title" title="The batch evaluation">
            The same agent, run on 500 seeded batches. The rate below is simulated; the
            safety-gate counts are what the policy did.
          </SectionHead>
          <HeadlineMetrics />
          <button className="btn btn-ghost block-cta" onClick={onEnterDashboard}>Run a batch yourself</button>
        </Reveal>

        <Reveal as="section" className="wrap block" id="how-it-works" aria-labelledby="how-title">
          <SectionHead id="how-title" title="How a failure is handled">
            Six controls, in order. Each one acts only on data it was given, and each
            has a condition that stops the case.
          </SectionHead>
          <AgentJourney />
        </Reveal>

        <Reveal as="section" className="wrap block" id="audit-tape" aria-labelledby="tape-title">
          <SectionHead id="tape-title" title="The audit tape">
            Every step of the recorded case above, as the agent logged it.
          </SectionHead>
          <AuditTrailVisual showcase={showcase} />
        </Reveal>
      </main>

      <footer className="site-footer wrap">
        <p>Built for the Razorpay Buildathon (Track 3). Test mode only; no real money moves.</p>
        <div className="site-footer-links">
          <a href="mailto:talwarritvik2840@gmail.com">talwarritvik2840@gmail.com</a>
          <a href="https://www.linkedin.com/in/ritvik-talwar-3b78372a1" target="_blank" rel="noreferrer">LinkedIn</a>
          <a href="https://github.com/ritvik302005" target="_blank" rel="noreferrer">GitHub</a>
        </div>
      </footer>
    </div>
  )
}
