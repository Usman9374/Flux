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
  // Async job flow — preferred over the legacy sync POST /scrape. Returns
  // { job_id } immediately; the caller then polls getScrapeJob.
  createScrapeJob: (body, signal) =>
    request('/scrape/jobs', { method: 'POST', body, signal }),
  getScrapeJob: (jobId, signal) =>
    request(`/scrape/jobs/${encodeURIComponent(jobId)}`, { signal }),
}

// Live intent preview — mirrors backend `parse_intent`. Used by ScrapeForm
// to show the user what we'll actually search for before they hit submit,
// so "restaurants in Islamabad without a website" displays as a known mode
// rather than just being submitted as raw text.
const NO_WEBSITE_PATTERNS = [
  /\bwithout\s+(?:a\s+)?website/i,
  /\bno\s+website/i,
  /\bnot\s+having\s+(?:a\s+)?website/i,
  /\b(?:doesn'?t|don'?t|do\s+not|does\s+not)\s+have\s+(?:a\s+)?website/i,
  /\boffline(?:\s+only)?\b/i,
]
export function previewIntent(niche) {
  let cleaned = niche || ''
  let requireWebsite = true
  for (const pat of NO_WEBSITE_PATTERNS) {
    if (pat.test(cleaned)) {
      requireWebsite = false
      cleaned = cleaned.replace(pat, ' ')
    }
  }
  cleaned = cleaned.replace(/\s+/g, ' ').replace(/^[ ,.\-]+|[ ,.\-]+$/g, '').trim()
  if (!cleaned) cleaned = niche || ''
  return {
    cleaned_niche: cleaned,
    require_website: requireWebsite,
    mode_label: requireWebsite
      ? 'Mode: businesses with first-party websites'
      : 'Mode: offline businesses only (no first-party website)',
  }
}

export { API_BASE }
