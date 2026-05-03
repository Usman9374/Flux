import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api.js'
import { Icon } from '../components/Icon.jsx'
import QualityScore from '../components/QualityScore.jsx'
import Rating from '../components/Rating.jsx'
import SignalGrid from '../components/SignalGrid.jsx'
import { downloadCSV, formatDate, formatRelative, hostname, leadsToCSV } from '../lib/format.js'

function tierLabel(score) {
  if (score === null || score === undefined) return { label: 'Unscored', tone: 'ghost' }
  if (score >= 70) return { label: 'High intent', tone: 'ok' }
  if (score >= 45) return { label: 'Promising', tone: 'matcha' }
  return { label: 'Cold', tone: 'warn' }
}

function CopyButton({ value, label = 'Copy' }) {
  const [copied, setCopied] = useState(false)
  if (!value) return null
  const handle = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(String(value))
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      // ignore — older browsers
    }
  }
  return (
    <button type="button" className="copy-chip" onClick={handle} title={`Copy ${label.toLowerCase()}`}>
      <Icon name={copied ? 'check' : 'copy'} size={12} />
      <span>{copied ? 'Copied' : label}</span>
    </button>
  )
}

function DetailRow({ icon, label, value, copy }) {
  return (
    <div className="detail-row">
      <div className="detail-key">
        {icon ? <Icon name={icon} size={13} /> : null}
        <span>{label}</span>
      </div>
      <div className="detail-val">
        {value !== null && value !== undefined && value !== '' ? (
          <>
            <span>{value}</span>
            {copy ? <CopyButton value={typeof copy === 'string' ? copy : value} /> : null}
          </>
        ) : (
          <span className="muted">—</span>
        )}
      </div>
    </div>
  )
}

function DetailSkeleton() {
  return (
    <div className="detail-skeleton">
      <div className="skeleton" style={{ height: 28, width: '40%', marginBottom: 12 }} />
      <div className="skeleton" style={{ height: 14, width: '60%', marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 14, width: '30%' }} />
    </div>
  )
}

export default function LeadDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [lead, setLead] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    const ctrl = new AbortController()
    setLoading(true)
    setError(null)
    setNotFound(false)
    setLead(null)
    api
      .getLead(id, ctrl.signal)
      .then((data) => setLead(data))
      .catch((err) => {
        if (err.name === 'AbortError') return
        const msg = String(err?.message || '')
        if (/not found/i.test(msg) || /404/.test(msg)) {
          setNotFound(true)
        } else {
          setError(msg || 'Failed to load lead.')
        }
      })
      .finally(() => setLoading(false))
    return () => ctrl.abort()
  }, [id])

  if (loading) {
    return (
      <>
        <div className="page-header">
          <div>
            <Link to="/leads" className="back-link">
              <Icon name="arrow-left" size={12} /> Back to leads
            </Link>
            <h2 style={{ marginTop: 8 }}>Loading lead…</h2>
          </div>
        </div>
        <div className="card">
          <div className="card-body">
            <DetailSkeleton />
          </div>
        </div>
      </>
    )
  }

  if (notFound) {
    return (
      <>
        <div className="page-header">
          <div>
            <Link to="/leads" className="back-link">
              <Icon name="arrow-left" size={12} /> Back to leads
            </Link>
            <h2 style={{ marginTop: 8 }}>Lead not found</h2>
            <p>The lead with id <span className="mono">{id}</span> doesn’t exist (or was removed).</p>
          </div>
        </div>
        <div className="card">
          <div className="card-body">
            <div className="empty">
              <div className="title">Nothing to show</div>
              <div className="hint">
                Try returning to the leads table — the row may have been merged or replaced by a fresher scrape.
              </div>
              <div className="mt-12">
                <button className="btn matcha" onClick={() => navigate('/leads')}>
                  Open leads
                </button>
              </div>
            </div>
          </div>
        </div>
      </>
    )
  }

  if (error) {
    return (
      <>
        <div className="page-header">
          <div>
            <Link to="/leads" className="back-link">
              <Icon name="arrow-left" size={12} /> Back to leads
            </Link>
            <h2 style={{ marginTop: 8 }}>Couldn’t load lead</h2>
          </div>
        </div>
        <div className="banner err">{error}</div>
      </>
    )
  }

  const tier = tierLabel(lead.quality_score)
  const host = hostname(lead.website)
  const sourceHost = hostname(lead.source_url)
  const exportOne = () => {
    const stamp = new Date().toISOString().slice(0, 10)
    const slug = (lead.name || `lead-${lead.id}`)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 60)
    downloadCSV(`flux-${slug}-${stamp}.csv`, leadsToCSV([lead]))
  }

  return (
    <>
      <div className="page-header detail-header">
        <div>
          <Link to="/leads" className="back-link">
            <Icon name="arrow-left" size={12} /> Back to leads
          </Link>
          <h2 className="detail-title">{lead.name}</h2>
          <div className="detail-meta">
            {lead.niche ? <span className="pill matcha">{lead.niche}</span> : null}
            {lead.location ? (
              <span className="pill outline">
                <Icon name="pin" size={11} /> {lead.location}
              </span>
            ) : null}
            <span className="pill ghost">
              <Icon name="info" size={11} /> Source · {lead.source}
            </span>
            <span className="text-mute" style={{ fontSize: 12.5 }}>
              Added {formatRelative(lead.created_at)}
            </span>
          </div>
        </div>
        <div className="page-actions">
          {lead.website ? (
            <a className="btn primary" href={lead.website} target="_blank" rel="noreferrer">
              <Icon name="external" size={13} /> Open website
            </a>
          ) : null}
          <button className="btn" onClick={exportOne}>
            <Icon name="download" size={13} /> Export CSV
          </button>
        </div>
      </div>

      <div className="detail-grid">
        <div className="detail-col">
          <div className="card">
            <div className="card-head">
              <div>
                <h3>Lead intelligence</h3>
                <div className="sub">Composite quality score and the signals that drove it.</div>
              </div>
              <span className={`pill ${tier.tone}`}>{tier.label}</span>
            </div>
            <div className="card-body">
              <div className="quality-hero">
                <div className="quality-hero-num">
                  {lead.quality_score === null || lead.quality_score === undefined
                    ? '—'
                    : lead.quality_score}
                  <span className="quality-hero-of">/100</span>
                </div>
                <div className="quality-hero-bar">
                  <QualityScore value={lead.quality_score} />
                </div>
                <p className="quality-hero-note">
                  Score combines presence of a first-party website, contact channels, location alignment
                  with the search query, category-niche fit, and reputation strength. Higher scores
                  indicate leads that are more likely to be reachable and on-target.
                </p>
              </div>

              <div className="section-divider" />

              <div className="section-head">
                <h4>
                  <Icon name="sparkle" size={14} /> Business intelligence signals
                </h4>
                <span className="text-mute" style={{ fontSize: 12 }}>
                  Filled signals contributed to this lead's score.
                </span>
              </div>
              <SignalGrid signals={lead.signals} />
            </div>
          </div>

          <div className="card mt-18">
            <div className="card-head">
              <div>
                <h3>Reputation</h3>
                <div className="sub">Public-facing rating and review volume.</div>
              </div>
            </div>
            <div className="card-body">
              <div className="reputation">
                <div className="rep-rating">
                  <Rating value={lead.rating} count={lead.reviews_count} />
                </div>
                <div className="rep-meta">
                  {lead.rating !== null && lead.rating !== undefined ? (
                    <>
                      <strong>{Number(lead.rating).toFixed(1)} ★</strong> from{' '}
                      {lead.reviews_count !== null && lead.reviews_count !== undefined
                        ? `${lead.reviews_count.toLocaleString()} review${lead.reviews_count === 1 ? '' : 's'}`
                        : 'an unknown number of reviews'}
                      .
                    </>
                  ) : (
                    <span className="muted">No rating data captured.</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="detail-col">
          <div className="card">
            <div className="card-head">
              <div>
                <h3>Contact</h3>
                <div className="sub">Channels surfaced from public listings.</div>
              </div>
            </div>
            <div className="card-body">
              <div className="detail-list">
                <DetailRow
                  icon="globe"
                  label="Website"
                  value={
                    host ? (
                      <a href={lead.website} target="_blank" rel="noreferrer" className="ext-link">
                        {host} <Icon name="external" size={11} />
                      </a>
                    ) : null
                  }
                  copy={lead.website}
                />
                <DetailRow icon="phone" label="Phone" value={lead.phone} copy={lead.phone} />
                <DetailRow icon="pin" label="Address" value={lead.address} copy={lead.address} />
                <DetailRow icon="pin" label="Location" value={lead.location} copy={lead.location} />
              </div>
            </div>
          </div>

          <div className="card mt-18">
            <div className="card-head">
              <div>
                <h3>Categorization</h3>
                <div className="sub">How Flux classified this business.</div>
              </div>
            </div>
            <div className="card-body">
              <div className="detail-list">
                <DetailRow icon="tag" label="Niche" value={lead.niche} />
                <DetailRow icon="tag" label="Category" value={lead.category} />
              </div>
            </div>
          </div>

          <div className="card mt-18">
            <div className="card-head">
              <div>
                <h3>Provenance</h3>
                <div className="sub">Where this record came from and when it changed.</div>
              </div>
            </div>
            <div className="card-body">
              <div className="detail-list">
                <DetailRow icon="info" label="Source" value={lead.source} />
                <DetailRow
                  icon="external"
                  label="Source URL"
                  value={
                    sourceHost ? (
                      <a
                        href={lead.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="ext-link"
                      >
                        {sourceHost} <Icon name="external" size={11} />
                      </a>
                    ) : null
                  }
                  copy={lead.source_url}
                />
                <DetailRow
                  icon="calendar"
                  label="First seen"
                  value={formatDate(lead.created_at)}
                />
                <DetailRow
                  icon="calendar"
                  label="Last updated"
                  value={formatDate(lead.updated_at)}
                />
                <DetailRow
                  icon="info"
                  label="Internal id"
                  value={<span className="mono">#{lead.id}</span>}
                  copy={String(lead.id)}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
