import { takeToken } from './turnstile.js'

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status // 0 when the backend couldn't be reached
  }
}

// FastAPI sends { detail: "message" }, or { detail: [{ loc, msg }, ...] }
// when request validation fails (422).
function errorMessage(body, status) {
  const detail = body && body.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => {
      const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null
      return field ? `${field}: ${d.msg}` : d.msg
    }).join('; ')
  }
  return `The server returned an error (HTTP ${status}).`
}

// Endpoints that act (create orders, run batches) need a short-lived
// session token from POST /api/session. It is kept in memory only, so a
// reload starts a new session.
let sessionToken = null
let pendingSession = null

function getSessionToken(fresh = false) {
  if (fresh) sessionToken = null
  if (sessionToken) return Promise.resolve(sessionToken)
  if (!pendingSession) {
    pendingSession = takeToken()
      .then((proof) => request('/api/session', { method: 'POST', body: proof ? { turnstile_token: proof } : undefined }))
      .then((data) => { sessionToken = data.token; return sessionToken })
      .finally(() => { pendingSession = null })
  }
  return pendingSession
}

/**
 * The one way the frontend calls the backend. Resolves with the parsed
 * JSON body; rejects with an ApiError whose message is safe to show.
 * `session: true` sends the session token, and on a 401 (expired) gets a
 * new one and retries once.
 *
 *   apiFetch('/api/batch/run', { method: 'POST', params: { n: 60 }, session: true })
 *   apiFetch('/api/live-demo/create-order', { method: 'POST', body: { amount: 1000 }, session: true })
 */
export async function apiFetch(path, { session = false, ...options } = {}) {
  if (!session) return request(path, options)
  const token = await getSessionToken()
  try {
    return await request(path, options, token)
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401) throw e
    return request(path, options, await getSessionToken(true))
  }
}

async function request(path, { method = 'GET', params, body } = {}, token = null) {
  const query = params ? `?${new URLSearchParams(params)}` : ''
  const init = { method, headers: {} }
  if (token) init.headers['X-Session-Token'] = token
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch(`${API_BASE}${path}${query}`, init)
  } catch {
    throw new ApiError('Could not reach the backend. Check that it is running and try again.', 0)
  }

  let data = null
  try {
    data = await res.json()
  } catch {
    // Not JSON (e.g. a proxy's HTML error page); handled below.
  }
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status)
  if (data === null) throw new ApiError('The server sent a response that could not be read.', res.status)
  return data
}
