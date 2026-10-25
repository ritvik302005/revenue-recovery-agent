export default function SiteFooter({ navigate }) {
  function go(e, href) {
    if (!navigate || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
    e.preventDefault()
    navigate(href)
  }

  return (
    <footer className="site-footer wrap">
      <p>
        Built for the Razorpay Buildathon (Track 3). Test mode only; no real money moves.
        Not affiliated with Razorpay.
      </p>
      <div className="site-footer-links">
        <a href="/legal" onClick={(e) => go(e, '/legal')}>Privacy and terms</a>
        <a href="https://github.com/ritvik302005/revenue-recovery-agent" target="_blank" rel="noreferrer">Source on GitHub</a>
        <a href="mailto:talwarritvik2840@gmail.com">talwarritvik2840@gmail.com</a>
        <a href="https://www.linkedin.com/in/ritvik-talwar-3b78372a1" target="_blank" rel="noreferrer">LinkedIn</a>
      </div>
    </footer>
  )
}
