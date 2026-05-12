import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api.js'
import { Icon } from '../components/Icon.jsx'
import QualityScore from '../components/QualityScore.jsx'
import Rating from '../components/Rating.jsx'
import SignalGrid from '../components/SignalGrid.jsx'
import { Btn, Panel, Pill, ScoreRing } from '../components/UI.jsx'
import { downloadCSV, formatDate, formatRelative, hostname, leadsToCSV } from '../lib/format.js'

function tierLabel(tier, score) {
  if (tier === 'A') return { label: 'TIER A · HIGH INTENT', tone: 'accent' }
  if (tier === 'B') return { label: 'TIER B · STRONG', tone: 'warm' }
  if (tier === 'C') return { label: 'TIER C · PROMISING', tone: 'info' }
  if (score === null || score === undefined) return { label: 'UNSCORED', tone: 'default' }
  if (score >= 80) return { label: 'HIGH INTENT', tone: 'accent' }
  if (score >= 65) return { label: 'STRONG', tone: 'warm' }
  if (score >= 45) return { label: 'PROMISING', tone: 'info' }
  return { label: 'COLD', tone: 'err' }
}

const TOP_SIGNAL_LABELS = {
  own_website: 'verified website',
  website_confirmed: 'website cross-verified',
  has_phone: 'phone listed',
  has_named_email: 'named email',
  has_generic_email: 'generic email',
  category_match: 'category match',
  location_match: 'location match',
  rating_strong: 'strong reputation',
  reviews_high: 'established footprint',
  has_socials: 'active socials',
  offline_verified: 'verified offline',
}

function whyKept(lead) {
  const signals = lead.signals || {}
  const reasons = []
  // Reputation gets a numeric chip so it reads more concretely than just a flag.
  if (lead.rating && lead.reviews_count) {
    reasons.push(`★ ${Number(lead.rating).toFixed(1)} · ${lead.reviews_count} reviews`)
  }
  for (const key of [
    'own_website',
    'website_confirmed',
    'has_named_email',
    'has_phone',
    'category_match',
    'location_match',
    'rating_strong',
    'reviews_high',
    'offline_verified',
  ]) {
    if (signals[key]) reasons.push(TOP_SIGNAL_LABELS[key] || key)
    if (reasons.length >= 3) break
  }
  return reasons
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
    <button
      type="button"
      className="copy-chip"
      onClick={handle}
      title={`Copy ${label.toLowerCase()}`}
    >
      <Icon name={copied ? 'check' : 'copy'} size={11} />
      <span>{copied ? 'COPIED' : label.toUpperCase()}</span>
    </button>
  )
}

function DetailRow({ icon, label, value, copy }) {
  return (
    <div className="detail-row">
      <div className="detail-key">
        {icon ? <Icon name={icon} size={12} /> : null}
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
    <div>
      <div className="skeleton" style={{ height: 32, width: '40%', marginBottom: 14 }} />
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
        <div className="detail-header">
          <div>
            <Link to="/leads" className="back-link">
              <Icon name="arrow-left" size={11} /> Back to leads
            </Link>
            <h2 className="detail-title">Loading lead…</h2>
          </div>
        </div>
        <Panel>
          <DetailSkeleton />
        </Panel>
      </>
    )
  }

  if (notFound) {
    return (
      <>
        <div className="detail-header">
          <div>
            <Link to="/leads" className="back-link">
              <Icon name="arrow-left" size={11} /> Back to leads
            </Link>
            <h2 className="detail-title">Lead not found</h2>
            <p className="text-mute">
              The lead with id <span className="mono">#{id}</span> doesn't exist (or was removed).
            </p>
          </div>
        </div>
        <Panel>
          <div className="empty">
            <div className="title">Nothing to show</div>
            <div className="hint">
              Try returning to the leads table — the row may have been merged or replaced by a fresher
              scrape.
            </div>
            <div className="mt-12">
              <Btn kind="primary" onClick={() => navigate('/leads')}>
                Open leads
              </Btn>
            </div>
          </div>
        </Panel>
      </>
    )
  }

  if (error) {
    return (
      <>
        <div className="detail-header">
          <div>
            <Link to="/leads" className="back-link">
              <Icon name="arrow-left" size={11} /> Back to leads
            </Link>
            <h2 className="detail-title">Couldn't load lead</h2>
          </div>
        </div>
        <div className="banner err">{error}</div>
      </>
    )
  }

  const tier = tierLabel(lead.tier, lead.quality_score)
  const reasons = whyKept(lead)
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
      <div className="detail-header">
        <div style={{ minWidth: 0 }}>
          <Link to="/leads" className="back-link">
            <Icon name="arrow-left" size={11} /> Back to leads
          </Link>
          <h2 className="detail-title">{lead.name}</h2>
          <div className="detail-meta">
            <Pill tone={tier.tone} dot>
              {tier.label}
            </Pill>
            {lead.confidence !== null && lead.confidence !== undefined ? (
              <Pill tone="info">
                Confidence {Math.round(Number(lead.confidence) * 100)}%
              </Pill>
            ) : null}
            {reasons.slice(0, 3).map((r) => (
              <Pill key={r}>{r}</Pill>
            ))}
            {lead.niche ? <Pill>{lead.niche.toUpperCase()}</Pill> : null}
            {lead.location ? (
              <Pill>
                <Icon name="pin" size={10} /> {lead.location}
              </Pill>
            ) : null}
            <Pill>
              <Icon name="database" size={10} /> {(lead.sources && lead.sources.length > 0)
                ? lead.sources.join(' + ')
                : lead.source || 'unknown source'}
            </Pill>
            <span className="text-mute mono" style={{ fontSize: 11.5 }}>
              Added {formatRelative(lead.created_at)}
            </span>
          </div>
        </div>
        <div className="page-actions">
          {lead.website ? (
            <Btn
              kind="primary"
              icon="external"
              as="a"
              href={lead.website}
              target="_blank"
              rel="noreferrer"
            >
              Open website
            </Btn>
          ) : null}
          <Btn kind="secondary" icon="download" onClick={exportOne}>
            Export CSV
          </Btn>
        </div>
      </div>

      <div className="detail-grid">
        <div className="detail-col">
          <Panel
            title="Lead intelligence"
            sub="Composite quality score + the signals that drove it"
            action={
              <Pill tone={tier.tone} dot>
                {tier.label}
              </Pill>
            }
          >
            <div className="quality-hero">
              <ScoreRing score={lead.quality_score} size={88} sw={6} />
              <div className="quality-hero-bar">
                <div style={{ width: '100%' }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'baseline',
                      justifyContent: 'space-between',
                      gap: 12,
                      marginBottom: 8,
                    }}
                  >
                    <div className="quality-hero-num">
                      {lead.quality_score === null || lead.quality_score === undefined
                        ? '—'
                        : lead.quality_score}
                      <span className="quality-hero-of">/100</span>
                    </div>
                    <Rating value={lead.rating} count={lead.reviews_count} />
                  </div>
                  <QualityScore value={lead.quality_score} />
                </div>
              </div>
              <p className="quality-hero-note">
                Score combines presence of a first-party website, contact channels, location alignment
                with the search query, category-niche fit, and reputation strength. Higher scores
                indicate leads that are more reachable and on-target.
              </p>
            </div>

            <div className="section-divider" />

            <div className="section-head">
              <h4>
                <Icon name="spark" size={13} /> Business intelligence signals
              </h4>
              <span
                className="text-mute"
                style={{ fontSize: 11.5, fontFamily: 'var(--mono)', fontWeight: 600 }}
              >
                Filled signals contributed to the score
              </span>
            </div>
            <SignalGrid signals={lead.signals} />
          </Panel>

          <Panel
            title="Reputation"
            sub="Public-facing rating and review volume"
          >
            <div className="reputation">
              <div className="rep-rating">
                <Rating value={lead.rating} count={lead.reviews_count} />
              </div>
              <div className="rep-meta">
                {lead.rating !== null && lead.rating !== undefined ? (
                  <>
                    <strong>{Number(lead.rating).toFixed(1)} ★</strong> from{' '}
                    {lead.reviews_count !== null && lead.reviews_count !== undefined
                      ? `${lead.reviews_count.toLocaleString()} review${
                          lead.reviews_count === 1 ? '' : 's'
                        }`
                      : 'an unknown number of reviews'}
                    .
                  </>
                ) : (
                  <span className="text-mute">No rating data captured.</span>
                )}
              </div>
            </div>
          </Panel>
        </div>

        <div className="detail-col">
          <Panel title="Contact" sub="Channels surfaced from public listings + the company website">
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
              <DetailRow
                icon="mail"
                label="Email"
                value={
                  lead.email ? (
                    <a href={`mailto:${lead.email}`} className="ext-link">
                      {lead.email}
                    </a>
                  ) : null
                }
                copy={lead.email}
              />
              <DetailRow icon="phone" label="Phone" value={lead.phone} copy={lead.phone} />
              <DetailRow icon="pin" label="Address" value={lead.address} copy={lead.address} />
              <DetailRow icon="pin" label="Location" value={lead.location} copy={lead.location} />
              <DetailRow icon="calendar" label="Hours" value={lead.hours} />
            </div>
          </Panel>

          {lead.social_links && Object.keys(lead.social_links).length > 0 ? (
            <Panel title="Social profiles" sub="Linked from the company website">
              <div className="detail-list">
                {Object.entries(lead.social_links).map(([key, url]) => (
                  <DetailRow
                    key={key}
                    icon="external"
                    label={key.charAt(0).toUpperCase() + key.slice(1)}
                    value={
                      <a href={url} target="_blank" rel="noreferrer" className="ext-link">
                        {hostname(url) || url} <Icon name="external" size={11} />
                      </a>
                    }
                    copy={url}
                  />
                ))}
              </div>
            </Panel>
          ) : null}

          <Panel title="Categorization" sub="How Flux classified this business">
            <div className="detail-list">
              <DetailRow icon="tag" label="Niche" value={lead.niche} />
              <DetailRow icon="tag" label="Category" value={lead.category} />
              <DetailRow icon="pin" label="Plus code" value={lead.plus_code} copy={lead.plus_code} />
            </div>
          </Panel>

          {lead.description ? (
            <Panel title="About" sub="Pulled from the company's website or Google's editorial summary">
              <p style={{ margin: 0, lineHeight: 1.55, color: 'var(--text)' }}>
                {lead.description}
              </p>
            </Panel>
          ) : null}

          <Panel title="Provenance" sub="Where this record came from and when it changed">
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
              <DetailRow icon="calendar" label="First seen" value={formatDate(lead.created_at)} />
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
          </Panel>
        </div>
      </div>
    </>
  )
}
