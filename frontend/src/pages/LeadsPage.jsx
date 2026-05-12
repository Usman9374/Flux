import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import LeadsTable from '../components/LeadsTable.jsx'
import { Icon } from '../components/Icon.jsx'
import { Btn, Pill } from '../components/UI.jsx'
import { downloadCSV, leadsToCSV } from '../lib/format.js'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from '../components/ui/input-group.jsx'
import { LoadingIndicator } from '../components/application/loading-indicator/loading-indicator.tsx'

const PAGE_SIZE = 25

export default function LeadsPage() {
  const navigate = useNavigate()
  const [niche, setNiche] = useState('')
  const [location, setLocation] = useState('')
  const [minScore, setMinScore] = useState('')
  const [search, setSearch] = useState('')
  const [sorting, setSorting] = useState([{ id: 'added', desc: true }])
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

  const filteredByMinScore = useMemo(() => {
    const min = minScore === '' ? null : Number(minScore)
    if (min === null || Number.isNaN(min)) return items
    return items.filter((l) => (l.quality_score ?? 0) >= min)
  }, [items, minScore])

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  const reset = () => {
    setNiche('')
    setLocation('')
    setMinScore('')
    setSearch('')
    setSorting([{ id: 'added', desc: true }])
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

  const hasFilters = niche || location || minScore || search

  return (
    <>
      {error ? <div className="banner err mb-18">{error}</div> : null}

      <section className="panel">
        <div className="filter-bar">
          <Pill tone="accent" dot>
            {count.toLocaleString()} LEADS
          </Pill>
          <span
            className="text-mute"
            style={{
              fontSize: 11.5,
              fontFamily: 'var(--mono)',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            {loading ? (
              <span className="flux-loading inline-loading" aria-hidden>
                <LoadingIndicator type="line-spinner" size="sm" />
              </span>
            ) : null}
            {loading ? 'Syncing…' : `${filteredByMinScore.length} on this page`}
          </span>

          <div className="grow" />

          <div className="lead-search">
            <InputGroup>
              <InputGroupAddon>
                <Icon name="search" size={14} />
              </InputGroupAddon>
              <InputGroupInput
                placeholder="Search name, website, niche…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </InputGroup>
          </div>

          <label className="filter-input">
            <Icon name="tag" size={12} />
            <span className="label">Niche</span>
            <input
              type="text"
              placeholder="any"
              value={niche}
              onChange={(e) => {
                setNiche(e.target.value)
                setPage(0)
              }}
            />
          </label>

          <label className="filter-input">
            <Icon name="pin" size={12} />
            <span className="label">Location</span>
            <input
              type="text"
              placeholder="any"
              value={location}
              onChange={(e) => {
                setLocation(e.target.value)
                setPage(0)
              }}
            />
          </label>

          <label className="filter-input">
            <Icon name="shield" size={12} />
            <span className="label">Min</span>
            <input
              type="number"
              min={0}
              max={100}
              placeholder="0"
              value={minScore}
              onChange={(e) => setMinScore(e.target.value)}
              style={{ width: 50 }}
            />
          </label>

          {hasFilters ? (
            <Btn kind="ghost" sm icon="x" onClick={reset}>
              Reset
            </Btn>
          ) : null}

          <div className="divider-v" />

          <Btn
            kind="outline"
            sm
            icon="download"
            onClick={exportCSV}
            disabled={loading || filteredByMinScore.length === 0}
          >
            Export
          </Btn>
        </div>

        <div className="panel-body tight">
          <LeadsTable
            leads={filteredByMinScore}
            loading={loading}
            onRowClick={(lead) => navigate(`/leads/${lead.id}`)}
            globalFilter={search}
            onGlobalFilterChange={setSearch}
            sorting={sorting}
            onSortingChange={setSorting}
            emptyTitle={hasFilters ? 'No leads match these filters' : 'No leads yet'}
            emptyHint={
              hasFilters
                ? 'Try widening your filters or running a fresh scrape from the dashboard.'
                : 'Run a scrape from the dashboard to start populating the pipeline.'
            }
          />
        </div>

        <div className="panel-foot">
          <div>
            {loading
              ? 'Loading…'
              : `Showing ${filteredByMinScore.length} of ${count} matching lead${count === 1 ? '' : 's'}`}
          </div>
          <div className="pagination">
            <Btn
              kind="outline"
              sm
              icon="arrow-left"
              disabled={page === 0 || loading}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Prev
            </Btn>
            <span className="info">
              Page {page + 1} / {totalPages}
            </span>
            <Btn
              kind="outline"
              sm
              icon="arrow-right"
              disabled={page + 1 >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Btn>
          </div>
        </div>
      </section>
    </>
  )
}
