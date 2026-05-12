import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api.js'
import ScrapeForm from '../components/ScrapeForm.jsx'
import LeadsTable from '../components/LeadsTable.jsx'
import { Btn } from '../components/UI.jsx'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [recent, setRecent] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const recentRes = await api.listLeads({ limit: 6, offset: 0 })
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

  return (
    <>
      <ScrapeForm onResult={() => load()} />

      {error ? <div className="banner err mt-22">{error}</div> : null}

      <section className="panel mt-22">
        <header className="panel-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            <h3>Recent leads</h3>
          </div>
          <Btn
            kind="ghost"
            sm
            as={Link}
            to="/leads"
            style={{ textDecoration: 'none' }}
          >
            View all
          </Btn>
        </header>
        <div className="panel-body tight">
          <LeadsTable
            leads={recent}
            loading={loading}
            onRowClick={(lead) => navigate(`/leads/${lead.id}`)}
            emptyTitle="No leads yet"
            emptyHint="Run your first scrape above to populate the pipeline."
          />
        </div>
      </section>
    </>
  )
}
