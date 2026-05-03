import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import ScrapeForm from '../components/ScrapeForm.jsx'
import LeadsTable from '../components/LeadsTable.jsx'
import { Icon } from '../components/Icon.jsx'

function avg(values) {
  const xs = values.filter((v) => v !== null && v !== undefined)
  if (!xs.length) return null
  return Math.round(xs.reduce((a, b) => a + Number(b), 0) / xs.length)
}

function StatCard({ label, value, delta }) {
  return (
    <div className="stat">
      <span className="accent" aria-hidden />
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {delta ? <div className="delta">{delta}</div> : null}
    </div>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [allLeads, setAllLeads] = useState([])
  const [recent, setRecent] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [allRes, recentRes] = await Promise.all([
        api.listLeads({ limit: 500, offset: 0 }),
        api.listLeads({ limit: 8, offset: 0 }),
      ])
      setAllLeads(allRes.items || [])
      setTotal(allRes.count || 0)
      setRecent(recentRes.items || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const niches = new Set()
  const locations = new Set()
  for (const l of allLeads) {
    if (l.niche) niches.add(l.niche.toLowerCase())
    if (l.location) locations.add(l.location.toLowerCase())
  }
  const avgQuality = avg(allLeads.map((l) => l.quality_score))
  const highQuality = allLeads.filter((l) => (l.quality_score ?? 0) >= 70).length

  return (
    <>
      <div className="page-header">
        <div>
          <h2>Pipeline overview</h2>
          <p>
            High-quality, structured B2B leads — scraped, scored, and stored. Run a new scrape or
            jump into the leads table.
          </p>
        </div>
        <div className="page-actions">
          <button className="btn ghost" onClick={load} disabled={loading}>
            <Icon name="refresh" size={14} /> Refresh
          </button>
          <Link to="/leads" className="btn primary">
            Open leads <Icon name="arrow-right" size={14} />
          </Link>
        </div>
      </div>

      {error ? <div className="banner err" style={{ marginBottom: 18 }}>{error}</div> : null}

      <div className="stat-grid">
        <StatCard label="Total leads" value={total} delta={`${allLeads.length} loaded`} />
        <StatCard
          label="High quality"
          value={highQuality}
          delta={`${total ? Math.round((highQuality / total) * 100) : 0}% of pipeline`}
        />
        <StatCard
          label="Avg quality"
          value={avgQuality !== null ? `${avgQuality}` : '—'}
          delta="Score 0–100"
        />
        <StatCard
          label="Niches × Locations"
          value={`${niches.size} × ${locations.size}`}
          delta="Distinct values seen"
        />
      </div>

      <div style={{ marginBottom: 18 }}>
        <ScrapeForm onResult={() => load()} />
      </div>

      <div className="card">
        <div className="card-head">
          <div>
            <h3>Recent leads</h3>
            <div className="sub">Latest 8 entries · click a row to view details.</div>
          </div>
          <Link to="/leads" className="btn sm ghost">
            View all <Icon name="arrow-right" size={12} />
          </Link>
        </div>
        <div className="card-body tight">
          <LeadsTable
            leads={recent}
            loading={loading}
            onRowClick={(lead) => navigate(`/leads/${lead.id}`)}
            emptyTitle="No leads yet"
            emptyHint="Run your first scrape above to populate the pipeline."
          />
        </div>
      </div>
    </>
  )
}
