import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import LeadsTable from '../components/LeadsTable.jsx'
import { Icon } from '../components/Icon.jsx'
import { downloadCSV, leadsToCSV } from '../lib/format.js'

const PAGE_SIZE = 25

export default function LeadsPage() {
  const navigate = useNavigate()
  const [niche, setNiche] = useState('')
  const [location, setLocation] = useState('')
  const [minScore, setMinScore] = useState('')
  const [sort, setSort] = useState('newest')
  const [page, setPage] = useState(0)

  const [items, setItems] = useState([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const ctrl = new AbortController()
    setLoading(true)
    setError(null)
    api
      .listLeads(
        {
          niche: niche || undefined,
          location: location || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        },
        ctrl.signal,
      )
      .then((res) => {
        setItems(res.items || [])
        setCount(res.count || 0)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => setLoading(false))
    return () => ctrl.abort()
  }, [niche, location, page])

  const filtered = useMemo(() => {
    const min = minScore === '' ? null : Number(minScore)
    let arr = items
    if (min !== null && !Number.isNaN(min)) {
      arr = arr.filter((l) => (l.quality_score ?? 0) >= min)
    }
    const cmp = (a, b) => {
      switch (sort) {
        case 'oldest':
          return new Date(a.created_at) - new Date(b.created_at)
        case 'quality':
          return (b.quality_score ?? -1) - (a.quality_score ?? -1)
        case 'rating':
          return (b.rating ?? -1) - (a.rating ?? -1)
        case 'name':
          return (a.name || '').localeCompare(b.name || '')
        case 'newest':
        default:
          return new Date(b.created_at) - new Date(a.created_at)
      }
    }
    return [...arr].sort(cmp)
  }, [items, minScore, sort])

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  const reset = () => {
    setNiche('')
    setLocation('')
    setMinScore('')
    setSort('newest')
    setPage(0)
  }

  const exportCSV = async () => {
    try {
      const all = await api.listLeads({
        niche: niche || undefined,
        location: location || undefined,
        limit: 500,
        offset: 0,
      })
      const stamp = new Date().toISOString().slice(0, 10)
      downloadCSV(`flux-leads-${stamp}.csv`, leadsToCSV(all.items || []))
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Leads</h2>
          <p>Search, filter, and export the structured business intelligence Flux has captured.</p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={exportCSV} disabled={loading || filtered.length === 0}>
            <Icon name="download" size={14} /> Export CSV
          </button>
        </div>
      </div>

      {error ? <div className="banner err" style={{ marginBottom: 18 }}>{error}</div> : null}

      <div className="card">
        <div className="filters">
          <div className="field">
            <label htmlFor="f-niche">Niche</label>
            <input
              id="f-niche"
              className="input"
              placeholder="e.g. dental clinic"
              value={niche}
              onChange={(e) => {
                setNiche(e.target.value)
                setPage(0)
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="f-loc">Location</label>
            <input
              id="f-loc"
              className="input"
              placeholder="e.g. Portland"
              value={location}
              onChange={(e) => {
                setLocation(e.target.value)
                setPage(0)
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="f-score">Min quality</label>
            <input
              id="f-score"
              className="input"
              type="number"
              min={0}
              max={100}
              placeholder="0–100"
              value={minScore}
              onChange={(e) => setMinScore(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="f-sort">Sort by</label>
            <select
              id="f-sort"
              className="select"
              value={sort}
              onChange={(e) => setSort(e.target.value)}
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="quality">Quality (high → low)</option>
              <option value="rating">Rating (high → low)</option>
              <option value="name">Name (A → Z)</option>
            </select>
          </div>
          <div className="field">
            <label>&nbsp;</label>
            <button className="btn ghost" onClick={reset} type="button">
              Reset
            </button>
          </div>
        </div>

        <div className="card-body tight">
          <LeadsTable
            leads={filtered}
            loading={loading}
            onRowClick={(lead) => navigate(`/leads/${lead.id}`)}
            emptyTitle={
              niche || location || minScore
                ? 'No leads match these filters'
                : 'No leads yet'
            }
            emptyHint={
              niche || location || minScore
                ? 'Try widening your filters or running a new scrape from the dashboard.'
                : 'Run a scrape from the dashboard to start populating the pipeline.'
            }
          />
        </div>

        <div className="card-foot">
          <div className="info">
            {loading
              ? 'Loading…'
              : `Showing ${filtered.length} of ${count} matching lead${count === 1 ? '' : 's'}`}
          </div>
          <div className="pagination">
            <button
              className="btn sm"
              disabled={page === 0 || loading}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              <Icon name="arrow-left" size={12} /> Prev
            </button>
            <span className="info">
              Page {page + 1} / {totalPages}
            </span>
            <button
              className="btn sm"
              disabled={page + 1 >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next <Icon name="arrow-right" size={12} />
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
