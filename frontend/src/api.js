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

/**
 * The one way the frontend calls the backend. Resolves with the parsed
 * JSON body; rejects with an ApiError whose message is safe to show.
 *
 *   apiFetch('/api/batch/run', { method: 'POST', params: { n: 60 } })
 *   apiFetch('/api/live-demo/create-order', { method: 'POST', body: { amount: 1000 } })
 */
export async function apiFetch(path, { method = 'GET', params, body } = {}) {
  const query = params ? `?${new URLSearchParams(params)}` : ''
  const init = { method }
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
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
