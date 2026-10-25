// Cloudflare Turnstile: proves a visitor is human before the backend issues
// a session (POST /api/session). Off unless VITE_TURNSTILE_SITE_KEY is set.
// The widget lives in <HumanCheck />; apiFetch asks for a token through
// takeToken() when it needs a new session. Tokens are single use and valid
// for 5 minutes, so the widget is reset after each one is taken.
const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
const WAIT_MS = 60_000

export const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''
export const turnstileEnabled = Boolean(SITE_KEY)

let widgetId = null
let ready = null          // token waiting to be taken
let waiters = []          // takeToken() calls waiting for a token
let failure = null        // set when the widget reports an error

function deliver(token) {
  failure = null
  const next = waiters.shift()
  if (next) next.resolve(token)
  else ready = token
}

function fail(message) {
  failure = message
  waiters.forEach((w) => w.reject(new Error(message)))
  waiters = []
}

function loadScript() {
  if (window.turnstile) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${SCRIPT_SRC}"]`)
    const script = existing || document.createElement('script')
    script.addEventListener('load', () => resolve())
    script.addEventListener('error', () => reject(new Error("Couldn't load the bot check.")))
    if (!existing) {
      script.src = SCRIPT_SRC
      script.async = true
      document.head.appendChild(script)
    }
  })
}

export async function mountTurnstile(container) {
  if (!turnstileEnabled || widgetId !== null) return
  await loadScript()
  widgetId = window.turnstile.render(container, {
    sitekey: SITE_KEY,
    appearance: 'interaction-only',      // shown only if Cloudflare needs the visitor to act
    callback: deliver,
    'expired-callback': () => { ready = null; window.turnstile.reset(widgetId) },
    'error-callback': () => fail("The bot check couldn't run. Refresh the page and try again."),
  })
}

export function unmountTurnstile() {
  if (widgetId !== null && window.turnstile) window.turnstile.remove(widgetId)
  widgetId = null
  ready = null
}

/** A fresh Turnstile token, or null when Turnstile is off. */
export function takeToken() {
  if (!turnstileEnabled) return Promise.resolve(null)
  if (failure) return Promise.reject(new Error(failure))
  if (ready) {
    const token = ready
    ready = null
    if (widgetId !== null) window.turnstile.reset(widgetId)   // prepare the next one
    return Promise.resolve(token)
  }
  return new Promise((resolve, reject) => {
    const waiter = { resolve: (t) => { clearTimeout(timer); if (widgetId !== null) window.turnstile.reset(widgetId); resolve(t) },
                     reject: (e) => { clearTimeout(timer); reject(e) } }
    const timer = setTimeout(() => {
      waiters = waiters.filter((w) => w !== waiter)
      reject(new Error('The bot check didn’t finish. Tick “Verify you are human” if it’s showing, then try again.'))
    }, WAIT_MS)
    waiters.push(waiter)
  })
}
