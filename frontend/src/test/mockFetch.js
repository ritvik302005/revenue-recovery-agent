import { vi } from 'vitest'

/**
 * Replace global fetch with a router: { '/api/path': response | (url, init) => response }.
 * A response is { status = 200, body } (body undefined → non-JSON), or 'network-error'.
 * Returns the vi.fn so tests can inspect calls.
 */
export function mockFetch(routes) {
  const fn = vi.fn(async (url, init = {}) => {
    const path = new URL(url).pathname
    let route = routes[path]
    if (typeof route === 'function') route = await route(url, init)
    if (route === undefined) throw new Error(`mockFetch: no route for ${path}`)
    if (route === 'network-error') throw new TypeError('Failed to fetch')
    const { status = 200, body } = route
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => {
        if (body === undefined) throw new SyntaxError('Unexpected token <')
        return body
      },
    }
  })
  vi.stubGlobal('fetch', fn)
  return fn
}
