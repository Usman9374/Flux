import { auth } from './firebase.js'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

async function authHeader() {
  const user = auth.currentUser
  if (!user) return null
  const token = await user.getIdToken()
  return token ? `Bearer ${token}` : null
}

async function request(path, { method = 'GET', body, signal, params, auth: needsAuth = true } = {}) {
  let url = `${API_BASE}${path}`
  if (params) {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '') continue
      qs.set(k, v)
    }
    const s = qs.toString()
    if (s) url += `?${s}`
  }

  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  if (needsAuth) {
    const ah = await authHeader()
    if (ah) headers['Authorization'] = ah
  }

  const res = await fetch(url, {
    method,
    signal,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  const ct = res.headers.get('content-type') || ''
  const data = ct.includes('application/json') ? await res.json() : await res.text()

  if (!res.ok) {
    const detail =
      (data && typeof data === 'object' && (data.detail || data.message)) ||
      (typeof data === 'string' ? data : `HTTP ${res.status}`)
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    err.status = res.status
    throw err
  }

  return data
}

export const api = {
  health: (signal) => request('/health', { signal, auth: false }),
  listLeads: (params, signal) => request('/leads', { params, signal }),
  getLead: (id, signal) => request(`/leads/${id}`, { signal }),
  scrape: (body, signal) => request('/scrape', { method: 'POST', body, signal }),
}

export { API_BASE }
