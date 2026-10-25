import SiteNav from './SiteNav.jsx'
import SiteFooter from './SiteFooter.jsx'

const UPDATED = '25 October 2026'

// Every retention period below matches the backend's settings
// (rate-limit windows, ACCESS_SESSION_TTL_SECONDS, LIVE_DEMO_TTL_SECONDS).
export default function LegalPage({ navigate }) {
  return (
    <div className="site">
      <SiteNav current="legal" navigate={navigate} />
      <main id="main" className="page wrap legal">
        <header className="page-head">
          <p className="eyebrow">Last updated {UPDATED}</p>
          <h1 className="display page-title">Privacy and terms</h1>
          <p className="page-lede">
            This site is a portfolio demo of a payment-recovery agent. It runs only in Razorpay
            Test Mode: no real payments are taken. Here is exactly what it handles.
          </p>
        </header>

        <section aria-labelledby="collect">
          <h2 id="collect">What this site keeps, and for how long</h2>
          <ul>
            <li><strong>No accounts, no cookies, no analytics.</strong> The site sets no cookies and runs no tracking or advertising scripts.</li>
            <li><strong>Your IP address</strong>, only to rate-limit requests: counters are kept for at most two minutes.</li>
            <li><strong>A session token</strong> that lets your browser start the demo. The server stores only a one-way hash of it, for up to 30 minutes. Your browser keeps it in memory only.</li>
            <li><strong>Live-demo records</strong>: Razorpay test order and payment ids, the amount, the error Razorpay returned, the payment method type, and the agent’s audit trail. Kept for up to one hour.</li>
            <li><strong>The latest completed demo case</strong> is shown on the home page until a newer one replaces it. It contains test-mode ids, the amount and the audit trail; no names, emails or phone numbers.</li>
            <li>Batch evaluations use synthetic data only.</li>
          </ul>
        </section>

        <section aria-labelledby="third">
          <h2 id="third">Services involved</h2>
          <ul>
            <li><strong>Razorpay Checkout</strong> (test mode) opens on Razorpay’s own pages. Anything you type there goes to Razorpay, not to this site, under <a href="https://razorpay.com/privacy/" target="_blank" rel="noreferrer">Razorpay’s privacy policy</a>. Use only Razorpay’s test cards and test UPI IDs; the demo pre-fills placeholder contact details.</li>
            <li><strong>Cloudflare Turnstile</strong> checks that a visitor is human before the demo starts; Cloudflare processes signals from your browser for this under <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noreferrer">its privacy policy</a>.</li>
            <li><strong>Hosting</strong> (Vercel for the site, Render for the API, Upstash for short-lived storage) handles requests and may keep standard server logs.</li>
          </ul>
        </section>

        <section aria-labelledby="dpdp">
          <h2 id="dpdp">Your rights (India’s DPDP Act, 2023)</h2>
          <p>
            Personal data here is limited to IP addresses used for security, processed only for that
            purpose and deleted within the periods above. To ask about, correct or erase data, or to raise
            a grievance, email <a href="mailto:talwarritvik2840@gmail.com">talwarritvik2840@gmail.com</a>.
          </p>
        </section>

        <section aria-labelledby="terms">
          <h2 id="terms">Terms of use</h2>
          <ul>
            <li>This is a demonstration, provided as is, without any warranty. It is not a payment service and must not be used for real transactions.</li>
            <li>Only Razorpay test instruments work; real cards are refused by Razorpay Test Mode.</li>
            <li>Don’t try to disrupt the service or get around its limits.</li>
            <li>Recovery rates shown for the batch evaluation are simulated, as labelled; they are not results from real payments.</li>
            <li>Not affiliated with or endorsed by Razorpay. “Razorpay” is used only to describe the integration.</li>
          </ul>
        </section>
      </main>
      <SiteFooter navigate={navigate} />
    </div>
  )
}
