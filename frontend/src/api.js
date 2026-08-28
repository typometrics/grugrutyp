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

/**
 * POST that streams Server-Sent Events back.
 *
 * `EventSource` cannot do this: it is GET-only, and a measure request carries two Grew
 * requests plus a treebank list, which do not belong in a URL. So the SSE framing is
 * parsed by hand off the fetch body stream -- it is four lines, and it buys progressive
 * rendering, which is the whole reason the endpoint streams.
 *
 * `onEvent(name, data)` is called for each event; the promise resolves when the stream
 * ends. Calling `abort()` on the returned controller stops it.
 */
export function stream(path, payload, onEvent) {
  const controller = new AbortController()

  const done = (async () => {
    const response = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      const detail = body.detail || {}
      const error = new Error(detail.message || `request failed (${response.status})`)
      error.detail = detail
      throw error
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    for (;;) {
      const { done: finished, value } = await reader.read()
      if (finished) break
      buffer += decoder.decode(value, { stream: true })

      // Events are separated by a blank line; anything after the last one is a partial
      // event and stays in the buffer until the next chunk completes it.
      let split
      while ((split = buffer.indexOf('\n\n')) !== -1) {
        const chunk = buffer.slice(0, split)
        buffer = buffer.slice(split + 2)
        let name = 'message'
        const dataLines = []
        for (const line of chunk.split('\n')) {
          if (line.startsWith('event: ')) name = line.slice(7)
          else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
        }
        if (dataLines.length) onEvent(name, JSON.parse(dataLines.join('\n')))
      }
    }
  })()

  return { done, abort: () => controller.abort() }
}

export const api = {
  treebanks: () => call('/treebanks'),
  validate: (request) =>
    call('/validate', { method: 'POST', body: JSON.stringify({ request }) }),
  search: (payload) => call('/search', { method: 'POST', body: JSON.stringify(payload) }),

  presets: (scheme) => call(`/presets?scheme=${encodeURIComponent(scheme)}`),
  languages: (view) => call(`/languages?view=${encodeURIComponent(view)}`),
  configAudit: () => call('/config/audit'),
  cacheStats: () => call('/cache/stats'),
  preview: (payload) => call('/measure/preview', { method: 'POST', body: JSON.stringify(payload) }),
  measure: (payload, onEvent) => stream('/measure', payload, onEvent),
}
