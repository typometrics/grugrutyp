// In production nginx maps /grugrutyp/api/ -> the FastAPI service; in `vite dev` the
// same prefix is proxied (see vite.config.js), so one base URL works in both.
const BASE = '/grugrutyp/api'

async function call(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = body.detail || {}
    const error = new Error(detail.message || `request failed (${response.status})`)
    error.detail = detail
    throw error
  }
  return body
}

export const api = {
  treebanks: () => call('/treebanks'),
  validate: (request) =>
    call('/validate', { method: 'POST', body: JSON.stringify({ request }) }),
  search: (payload) => call('/search', { method: 'POST', body: JSON.stringify(payload) }),
}
