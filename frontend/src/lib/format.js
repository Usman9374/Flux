export function formatDate(value) {
  if (!value) return '—'
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return '—'
  }
}

export function formatRelative(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const diffMs = Date.now() - d.getTime()
  const sec = Math.round(diffMs / 1000)
  if (sec < 60) return `${sec}s ago`
  const min = Math.round(sec / 60)
  if (min < 60) return `${min}m ago`
  const h = Math.round(min / 60)
  if (h < 24) return `${h}h ago`
  const day = Math.round(h / 24)
  if (day < 30) return `${day}d ago`
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
}

export function hostname(url) {
  if (!url) return null
  try {
    const u = new URL(url.startsWith('http') ? url : `https://${url}`)
    return u.hostname.replace(/^www\./, '')
  } catch {
    return url.replace(/^https?:\/\//, '').split('/')[0]
  }
}

export function leadsToCSV(leads) {
  const cols = [
    'id',
    'name',
    'website',
    'phone',
    'address',
    'location',
    'niche',
    'category',
    'rating',
    'reviews_count',
    'quality_score',
    'source',
    'source_url',
    'created_at',
    'updated_at',
  ]
  const escape = (v) => {
    if (v === null || v === undefined) return ''
    const s = typeof v === 'string' ? v : JSON.stringify(v)
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
    return s
  }
  const header = cols.join(',')
  const rows = leads.map((l) => cols.map((c) => escape(l[c])).join(','))
  return [header, ...rows].join('\n')
}

export function downloadCSV(filename, csv) {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
