import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mockFetch } from './test/mockFetch.js'

// api.js keeps the session token in module state: load a fresh copy per test.
let apiFetch, ApiError
beforeEach(async () => {
  vi.resetModules()
  ;({ apiFetch, ApiError } = await import('./api.js'))
})

describe('apiFetch errors', () => {
  it('returns parsed JSON on success', async () => {
    mockFetch({ '/api/health': { body: { status: 'ok' } } })
    await expect(apiFetch('/api/health')).resolves.toEqual({ status: 'ok' })
  })

  it("shows FastAPI's detail string", async () => {
    mockFetch({ '/api/x': { status: 502, body: { detail: 'Razorpay said: no' } } })
    await expect(apiFetch('/api/x')).rejects.toMatchObject({ message: 'Razorpay said: no', status: 502 })
  })

  it('formats a 422 validation list', async () => {
    mockFetch({ '/api/x': { status: 422, body: { detail: [{ loc: ['query', 'n'], msg: 'Input should be less than or equal to 500' }] } } })
    await expect(apiFetch('/api/x')).rejects.toThrow('n: Input should be less than or equal to 500')
  })

  it('survives a non-JSON error body', async () => {
    mockFetch({ '/api/x': { status: 504 } })
    await expect(apiFetch('/api/x')).rejects.toThrow('The server returned an error (HTTP 504).')
  })

  it('reports an unreachable backend with status 0', async () => {
    mockFetch({ '/api/x': 'network-error' })
    const err = await apiFetch('/api/x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
    expect(err.message).toMatch(/Could not reach the backend/)
  })

  it('encodes params and sends JSON bodies', async () => {
    const fetch = mockFetch({ '/api/x': { body: {} } })
    await apiFetch('/api/x', { method: 'POST', params: { a: 'b c', n: 5 }, body: { amount: 1000 } })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toMatch(/\/api\/x\?a=b\+c&n=5$/)
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ amount: 1000 })
  })
})

describe('apiFetch sessions', () => {
  it('gets one token and sends it on every session call', async () => {
    let issued = 0
    const fetch = mockFetch({
      '/api/session': () => ({ body: { token: `tok${++issued}` } }),
      '/api/batch/run': { body: { ok: true } },
    })
    await apiFetch('/api/batch/run', { method: 'POST', session: true })
    await apiFetch('/api/batch/run', { method: 'POST', session: true })
    expect(issued).toBe(1)
    const runs = fetch.mock.calls.filter(([url]) => url.includes('/api/batch/run'))
    expect(runs.map(([, init]) => init.headers['X-Session-Token'])).toEqual(['tok1', 'tok1'])
  })

  it('renews an expired token once and retries', async () => {
    let issued = 0
    mockFetch({
      '/api/session': () => ({ body: { token: `tok${++issued}` } }),
      '/api/batch/run': (url, init) => init.headers['X-Session-Token'] === 'tok1'
        ? { status: 401, body: { detail: 'Your session has expired.' } }
        : { body: { ok: true } },
    })
    await expect(apiFetch('/api/batch/run', { method: 'POST', session: true })).resolves.toEqual({ ok: true })
    expect(issued).toBe(2)
  })

  it('does not loop when the retry is also refused', async () => {
    mockFetch({
      '/api/session': { body: { token: 't' } },
      '/api/batch/run': { status: 401, body: { detail: 'Your session has expired.' } },
    })
    await expect(apiFetch('/api/batch/run', { method: 'POST', session: true })).rejects.toMatchObject({ status: 401 })
  })

  it('does not send the token on plain calls', async () => {
    const fetch = mockFetch({ '/api/health': { body: {} } })
    await apiFetch('/api/health')
    expect(fetch.mock.calls[0][1].headers['X-Session-Token']).toBeUndefined()
  })
})
