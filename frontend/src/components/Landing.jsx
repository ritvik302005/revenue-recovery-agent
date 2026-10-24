import { useState } from 'react'
import { useReveal } from '../hooks/useReveal.js'
import { useShowcaseCase } from '../hooks/useShowcaseCase.js'
import RecordedCaseCard from './RecordedCaseCard.jsx'
import AgentJourney from './AgentJourney.jsx'
import HeadlineMetrics from './HeadlineMetrics.jsx'
import AuditTrailVisual from './AuditTrailVisual.jsx'

function RevealSection({ children, className = '', delay = 0 }) {
  const [ref, visible] = useReveal()
  return (
    <div
      ref={ref}
      className={`reveal ${visible ? 'reveal-visible' : ''} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

const NAV_LINKS = [
  { id: 'overview', label: 'Overview', type: 'scroll' },
  { id: 'demo', label: 'Live Demo', type: 'route' },
  { id: 'dashboard', label: 'Evaluation', type: 'route' },
  { id: 'audit-trail', label: 'Audit Trail', type: 'scroll' },
]

export default function Landing({ onEnterDemo, onEnterDashboard }) {
  const [activeSection, setActiveSection] = useState('overview')
  const showcase = useShowcaseCase()

  function scrollTo(id) {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="landing">
      {/* Sticky nav, mirrors the buildathon site's top bar */}
      <nav className="landing-nav">
        <div className="landing-nav-inner">
          <div className="landing-nav-brand"><span className="brand-orb" /> RECOVER</div>
          <div className="landing-nav-links">
            {NAV_LINKS.map((l) => (
              <button
                key={l.id}
                className={`landing-nav-link ${activeSection === l.id ? 'active' : ''}`}
                onClick={() => (l.type === 'route' ? (l.id === 'demo' ? onEnterDemo() : onEnterDashboard()) : scrollTo(l.id))}
              >
                {l.label}
              </button>
            ))}
          </div>
          <button className="run-btn landing-nav-cta" onClick={onEnterDemo}>
            Run Demo →
          </button>
        </div>
      </nav>

      <div className="landing-hero-inner" id="overview">
        <div className="landing-hero-text">
          <RevealSection>
            <div className="landing-eyebrow">AUTONOMOUS REVENUE OPERATIONS</div>
            <h1 className="landing-title">
              Recover revenue<br />before it <span className="landing-title-accent">disappears.</span>
            </h1>
            <p className="landing-subtitle">
              Find revenue that's slipping away and win it back. Detects
              revenue at risk, determines the right intervention, and
              executes a bounded recovery workflow — from failed payments to
              overdue receivables — with a hard safety gate no LLM can
              override.
            </p>
            <div className="landing-cta-row">
              <button className="run-btn landing-cta landing-cta-primary" onClick={onEnterDemo}>
                Try Real Razorpay Demo →
              </button>
              <button className="run-btn landing-cta landing-cta-secondary" onClick={onEnterDashboard}>
                View Batch Evaluation
              </button>
            </div>
          </RevealSection>

          <RevealSection delay={80}>
            <div className="landing-provenance">
              <span className="provenance-chip chip-real" style={{ margin: 0 }}>
                ● Razorpay TEST MODE • Connected
              </span>
              <span className="provenance-chip chip-simulated" style={{ margin: 0 }}>
                ● Simulated outcomes always clearly labeled
              </span>
            </div>
          </RevealSection>

        </div>

        <RevealSection delay={40} className="landing-hero-visual-wrap">
          <RecordedCaseCard showcase={showcase} onEnterDemo={onEnterDemo} />
        </RevealSection>
      </div>

      {/* WHY NOW / THE BAR — same two-column pattern as the track cards */}
      <div className="landing-inner">
        <RevealSection>
          <div className="landing-track-card">
            <div className="landing-track-row">
              <div>
                <div className="landing-track-label">WHY NOW</div>
                <p className="landing-track-text">
                  Revenue loss rarely happens in one clean step. A payment
                  degrades, a checkout gets abandoned, a subscription fails.
                  Most systems either don't retry at all, or retry blindly
                  without understanding why it failed — this agent closes
                  the loop from detecting the problem to diagnosing it,
                  choosing the right intervention, and recovering the
                  money.
                </p>
              </div>
              <div>
                <div className="landing-track-label">THE BAR</div>
                <p className="landing-track-text">
                  Don't just identify the problem. Every money action is
                  explainable, bounded, and gated — measured recovery
                  across a batch, with compliant escalation, stopping
                  rules, and a full audit trail on every decision.
                </p>
              </div>
            </div>
          </div>
        </RevealSection>
      </div>

      {/* HEADLINE METRICS — from the batch evaluation, explicitly labeled */}
      <div className="landing-inner landing-inner-wide">
        <RevealSection>
          <HeadlineMetrics />
          <p className="headline-metrics-note">
            From the 60-case batch evaluation. The recovery rate and revenue
            figures are simulated outcomes, not money actually recovered —
            see real vs simulated below.
          </p>
        </RevealSection>
      </div>

      {/* HOW IT WORKS — horizontal agent journey */}
      <div className="landing-inner landing-inner-wide" id="how-it-works">
        <RevealSection>
          <div className="landing-section-title">How the agent thinks</div>
          <p className="landing-journey-intro">
            Every step is bounded — the agent can only act on data it was
            actually given, and every stage has a condition that stops it cold.
          </p>
        </RevealSection>
        <RevealSection delay={40}>
          <AgentJourney />
        </RevealSection>
      </div>

      {/* AUDIT TRAIL — every decision, timestamped */}
      <div className="landing-inner" id="audit-trail">
        <RevealSection>
          <div className="landing-section-title">Every decision, timestamped</div>
          <p className="landing-journey-intro">
            The safety gate and every action taken are logged as they
            happen — nothing is retroactively summarized.
          </p>
        </RevealSection>
        <RevealSection delay={40}>
          <AuditTrailVisual showcase={showcase} />
        </RevealSection>
      </div>

      {/* REAL VS SIMULATED — the two kinds of evidence, side by side */}
      <div className="landing-inner landing-inner-wide" id="provenance">
        <RevealSection>
          <div className="landing-section-title">Real vs simulated</div>
          <p className="landing-journey-intro">
            This project produces two different kinds of evidence. They are
            never presented as the same thing.
          </p>
        </RevealSection>

        <div className="compare-grid">
          <RevealSection delay={0}>
            <div className="compare-card compare-card-real">
              <div className="compare-card-badge">
                <span className="compare-card-dot" />
                REAL RAZORPAY TEST MODE
              </div>
              <div className="compare-card-flow">
                <span>1 payment</span>
                <span className="compare-arrow">→</span>
                <span>actual failure</span>
                <span className="compare-arrow">→</span>
                <span>actual error</span>
                <span className="compare-arrow">→</span>
                <span>actual recovery</span>
              </div>
              <p className="compare-card-body">
                A single real Razorpay order, a real Checkout failure using
                their documented test card, and a real recovery payment.
                Every field comes straight from Razorpay's API — verified
                only when their own status says captured.
              </p>
            </div>
          </RevealSection>

          <RevealSection delay={90}>
            <div className="compare-card compare-card-simulated">
              <div className="compare-card-badge">
                <span className="compare-card-dot" />
                60-CASE CONTROLLED EVALUATION
              </div>
              <div className="compare-card-flow">
                <span>60 cases</span>
                <span className="compare-arrow">→</span>
                <span>agent decisions</span>
                <span className="compare-arrow">→</span>
                <span>simulated recovery outcomes</span>
              </div>
              <p className="compare-card-body">
                Orders can be real, but failure reasons are synthetically
                assigned and recovery outcomes come from a probability
                model — useful for measuring the agent's decisions at
                scale, never presented as money actually recovered.
              </p>
            </div>
          </RevealSection>
        </div>

        <RevealSection delay={150}>
          <div className="compare-disclaimer">
            We never blend simulated recovery value with real Razorpay payment outcomes.
          </div>
        </RevealSection>
      </div>

      <div className="landing-inner">
        <RevealSection>
          <footer className="landing-footer">
            <div className="landing-footer-note">
              Every decision is logged with full reasoning. Real Razorpay
              data and simulated recovery outcomes are never blended into
              one number.
            </div>
            <a className="landing-footer-email" href="mailto:talwarritvik2840@gmail.com">
              <span className="footer-icon" aria-hidden="true">✉</span>
              talwarritvik2840@gmail.com
            </a>
            <div className="landing-footer-links">
              <a href="https://www.linkedin.com/in/ritvik-talwar-3b78372a1" target="_blank" rel="noreferrer">
                <svg className="footer-icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M5.4 3.7a2.1 2.1 0 1 1-4.2 0 2.1 2.1 0 0 1 4.2 0ZM1.5 8h3.8v12H1.5V8Zm6.2 0h3.7v1.6h.1c.5-1 1.8-2 3.8-2 4.1 0 4.8 2.6 4.8 6.1V20h-3.8v-5.6c0-1.3 0-3.1-2-3.1s-2.2 1.5-2.2 3V20H7.7V8Z" /></svg>
                LinkedIn
              </a>
              <a href="https://github.com/ritvik302005" target="_blank" rel="noreferrer">
                <svg className="footer-icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 1.5a10.5 10.5 0 0 0-3.3 20.47c.53.1.72-.23.72-.51v-2c-2.94.64-3.56-1.25-3.56-1.25-.48-1.22-1.17-1.54-1.17-1.54-.96-.66.07-.64.07-.64 1.06.08 1.62 1.09 1.62 1.09.94 1.62 2.47 1.15 3.07.88.1-.68.37-1.15.67-1.42-2.35-.27-4.82-1.18-4.82-5.24 0-1.16.41-2.1 1.09-2.85-.11-.27-.47-1.35.1-2.81 0 0 .89-.29 2.89 1.09a10.1 10.1 0 0 1 5.27 0c2-1.38 2.89-1.09 2.89-1.09.57 1.46.21 2.54.1 2.81.68.75 1.09 1.69 1.09 2.85 0 4.07-2.48 4.96-4.84 5.23.38.33.72.97.72 1.95v2.89c0 .28.19.62.73.51A10.5 10.5 0 0 0 12 1.5Z" /></svg>
                GitHub
              </a>
            </div>
          </footer>
          <div className="landing-cta-row" style={{ marginTop: 24 }}>
            <button className="run-btn landing-cta" onClick={onEnterDashboard}>
              Open Dashboard →
            </button>
          </div>
        </RevealSection>
      </div>
    </div>
  )
}
