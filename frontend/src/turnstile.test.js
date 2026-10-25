import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mockFetch } from './test/mockFetch.js'

// A stand-in for Cloudflare's widget API: render() keeps the callbacks so
// the test can "solve" the challenge.
let widget
function fakeTurnstile() {
  widget = { resets: 0, options: null }
  window.turnstile = {
    render: (_el, options) => { widget.options = options; return 'w1' },
    reset: () => { widget.resets++ },
    remove: () => {},
  }
}

async function load(siteKey) {
  vi.resetModules()
  vi.stubEnv('VITE_TURNSTILE_SITE_KEY', siteKey)
  const turnstile = await import('./turnstile.js')
  const api = await import('./api.js')
  return { turnstile, api }
}

beforeEach(fakeTurnstile)
afterEach(() => { vi.unstubAllEnvs(); delete window.turnstile })

describe('Turnstile', () => {
  it('is off without a site key: sessions are requested without a token', async () => {
    const { turnstile, api } = await load('')
    expect(turnstile.turnstileEnabled).toBe(false)
    await expect(turnstile.takeToken()).resolves.toBeNull()
    const fetch = mockFetch({ '/api/session': { body: { token: 's' } }, '/api/batch/run': { body: {} } })
    await api.apiFetch('/api/batch/run', { method: 'POST', session: true })
    expect(fetch.mock.calls[0][1].body).toBeUndefined()
  })

  it('sends the solved token with the session request, then resets the widget', async () => {
    const { turnstile, api } = await load('1x00000000000000000000AA')   // Cloudflare's always-pass test key
    await turnstile.mountTurnstile(document.createElement('div'))
    expect(widget.options.sitekey).toBe('1x00000000000000000000AA')
    expect(widget.options.appearance).toBe('interaction-only')

    const fetch = mockFetch({ '/api/session': { body: { token: 's' } }, '/api/batch/run': { body: {} } })
    const run = api.apiFetch('/api/batch/run', { method: 'POST', session: true })
    widget.options.callback('cf-token-1')                // the visitor passes the check
    await run
    const [url, init] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/session$/)
    expect(JSON.parse(init.body)).toEqual({ turnstile_token: 'cf-token-1' })
    expect(widget.resets).toBe(1)                        // single use: get the next one ready
  })

  it('uses a token solved before it was needed', async () => {
    const { turnstile } = await load('1x00000000000000000000AA')
    await turnstile.mountTurnstile(document.createElement('div'))
    widget.options.callback('early')
    await expect(turnstile.takeToken()).resolves.toBe('early')
  })

  it('reports a widget error instead of waiting forever', async () => {
    const { turnstile } = await load('1x00000000000000000000AA')
    await turnstile.mountTurnstile(document.createElement('div'))
    const pending = turnstile.takeToken()
    widget.options['error-callback']()
    await expect(pending).rejects.toThrow("bot check couldn't run")
  })
})
