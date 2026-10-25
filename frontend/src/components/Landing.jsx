import { useReveal } from '../hooks/useReveal.js'
import { useShowcaseCase } from '../hooks/useShowcaseCase.js'
import { useHealth, describeHealth } from '../hooks/useHealth.js'
import ReceiptPrinter from './ReceiptPrinter.jsx'
import ScrollStory from './ScrollStory.jsx'
import PolicyPlayground from './PolicyPlayground.jsx'
import HeadlineMetrics from './HeadlineMetrics.jsx'
import AuditTrailVisual from './AuditTrailVisual.jsx'
import SiteNav from './SiteNav.jsx'
import SiteFooter from './SiteFooter.jsx'

function Reveal({ children, className = '', as: Tag = 'div', ...rest }) {
  const [ref, visible] = useReveal()
  return (
    <Tag ref={ref} className={`reveal ${visible ? 'is-visible' : ''} ${className}`} {...rest}>
      {children}
    </Tag>
  )
}

function SectionHead({ id, kicker, title, children }) {
  return (
    <div className="section-head">
      {kicker && <p className="eyebrow">{kicker}</p>}
      <h2 className="display section-title" id={id}>{title}</h2>
      {children && <p className="section-intro">{children}</p>}
    </div>
  )
}

const REAL_LINES = [
  ['Order', 'Created on Razorpay Test Mode by the server'],
  ['Failure', 'A real Checkout decline with its real error_reason'],
  ['Action', 'Executed: a recovery link for the customer, or a support case'],
  ['Recovery', 'Counts only if the customer’s payment is captured, confirmed by Checkout’s signature or a signed webhook'],
]
const SIMULATED_LINES = [
  ['Order', 'A local id (real test orders are optional, first 5 only)'],
  ['Failure', 'A documented Razorpay code, assigned by a generator'],
  ['Action', 'The same execution plan, recorded; nothing is sent'],
  ['Outcome', 'Drawn from an illustrative probability table'],
]

function EvidenceSlip({ tone, title, stamp, lines, foot }) {
  return (
    <div className={`slip slip-${tone}`}>
      <div className="slip-head"><span className="slip-dot" aria-hidden="true" />{title}</div>
      <dl className="slip-lines">
        {lines.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
        ))}
      </dl>
      <p className="slip-foot">{foot}</p>
      <div className={`slip-stamp slip-stamp-${tone}`} aria-hidden="true">{stamp}</div>
    </div>
  )
}

const FAQ = [
  ['Is any real money involved?',
    'No. Everything runs in Razorpay Test Mode: orders and payments are real Razorpay test objects, but no money moves and real cards are refused. The backend rejects live keys.'],
  ['Is this an AI model?',
    'No. The decisions are fixed rules: a documented error mapping, an action table and a safety gate, run as a LangGraph graph. Every decision can be traced in the audit trail.'],
  ['What does the agent actually do after a failure?',
    'It carries the decision out. Depending on the reason it sends the customer a recovery link (right away, after a short delay, or with the failed payment method hidden), sends a reminder, or opens a support case without asking for money. If that doesn’t work, it escalates, up to three attempts.'],
  ['What is real and what is simulated?',
    'The live demo is real end to end: a real failure, the agent’s real action, a real customer payment confirmed by Razorpay. The batch evaluation is a simulation: synthetic failures and modelled outcomes, labelled as such, used to measure the policy at scale.'],
  ['Why does the demo show messages in an “outbox”?',
    'Sending real SMS or email needs a messaging provider and real contact details. The outbox shows exactly what the customer would receive, and the link in it is the real, working recovery link.'],
  ['Can I try it?',
    'Yes. Run the live demo with Razorpay’s test cards (shown on the page), try the policy above with any error code, or run a batch. The code is on GitHub.'],
]

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
            <h1 className="display hero-title" id="hero-title">
              Failed payments, recovered <span className="hero-mark">on the record.</span>
            </h1>
            <p className="lede">
              When a Razorpay payment fails, the agent reads the real error, picks a
              recovery action from a fixed policy, runs it past hard safety rules
              (fraud holds and a three-attempt retry budget), then carries it out:
              a recovery link for the customer, or a support case. Every step is
              written down. The rules are lookup tables, not a model.
            </p>
            <div className="cta-row">
              <button className="btn btn-paper" onClick={onEnterDemo}>Run the live demo</button>
              <a className="btn btn-ghost" href="#policy">Try the policy</a>
            </div>
            <p className={`status ${keyChip.cls}`} role="status">
              <span className="status-dot" aria-hidden="true" />{keyChip.text}
            </p>
          </div>
          <ReceiptPrinter showcase={showcase} onEnterDemo={onEnterDemo} />
        </section>

        <Reveal as="section" className="wrap block" id="evidence" aria-labelledby="evidence-title">
          <SectionHead id="evidence-title" kicker="Provenance" title="Two kinds of evidence">
            Everything on this site is one of these two. They never share a number.
          </SectionHead>
          <div className="slips">
            <EvidenceSlip tone="real" title="Real · Razorpay Test Mode" stamp="Real" lines={REAL_LINES}
              foot="One payment, end to end. This is what the live demo produces." />
            <EvidenceSlip tone="sim" title="Simulated · batch evaluation" stamp="Simulated" lines={SIMULATED_LINES}
              foot="Measures the agent's decisions at scale. Never shown as money recovered." />
          </div>
        </Reveal>

        <section className="wrap block" id="story" aria-labelledby="story-title">
          <SectionHead id="story-title" kicker="How it works" title="One failure, six controls">
            Scroll through the agent’s steps; the recorded case prints beside them as you go.
            Each step acts only on data it was given, and each has a condition that stops the case.
          </SectionHead>
          <ScrollStory showcase={showcase} />
        </section>

        <Reveal as="section" className="wrap block" id="policy" aria-labelledby="policy-title">
          <SectionHead id="policy-title" kicker="Interactive" title="Try the policy">
            Pick any error Razorpay documents and watch the agent decide. The slip is printed by the
            same rules the live demo runs.
          </SectionHead>
          <PolicyPlayground />
        </Reveal>

        <Reveal as="section" className="wrap block" id="evaluation" aria-labelledby="evaluation-title">
          <SectionHead id="evaluation-title" kicker="Measured" title="The batch evaluation">
            The same agent, run on 500 seeded batches. The rate below is simulated; the
            safety-gate counts are what the policy did.
          </SectionHead>
          <HeadlineMetrics />
          <button className="btn btn-ghost block-cta" onClick={onEnterDashboard}>Run a batch yourself</button>
        </Reveal>

        <Reveal as="section" className="wrap block" id="audit-tape" aria-labelledby="tape-title">
          <SectionHead id="tape-title" kicker="Accountability" title="The audit tape">
            Every step of the recorded case, as the agent logged it.
          </SectionHead>
          <AuditTrailVisual showcase={showcase} />
        </Reveal>

        <Reveal as="section" className="wrap block" id="faq" aria-labelledby="faq-title">
          <SectionHead id="faq-title" kicker="Questions" title="FAQ" />
          <div className="faq">
            {FAQ.map(([q, a]) => (
              <details key={q} className="faq-item">
                <summary>{q}</summary>
                <p>{a}</p>
              </details>
            ))}
          </div>
        </Reveal>
      </main>

      <SiteFooter navigate={navigate} />
    </div>
  )
}
