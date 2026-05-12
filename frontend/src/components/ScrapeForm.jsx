import { useEffect, useMemo, useRef, useState } from 'react'
import { api, previewIntent } from '../lib/api.js'
import { Btn } from './UI.jsx'
import { ProgressBarCircle } from './base/progress-indicators/progress-circles.tsx'
import { LoadingIndicator } from './application/loading-indicator/loading-indicator.tsx'

const NICHE_SUGGESTIONS = [
  'dental clinic',
  'roofing contractor',
  'med spa',
  'hvac company',
  'law firm',
  'chiropractor',
  'restaurants without a website',
]

const STAGE_LABELS = {
  queued: 'Queued',
  searching: 'Querying Google Maps',
  scrolling: 'Loading result feed',
  enriching_details: 'Reading detail panels',
  backfill: 'Backfilling from search engine',
  verifying_websites: 'Verifying websites',
  enriching_websites: 'Fetching contact info from websites',
  scoring: 'Scoring leads',
  relaxing_filter: 'No top-tier leads — relaxing filter',
  done: 'Done',
  error: 'Error',
}

const POLL_INTERVAL_MS = 1000
const MAX_POLL_AGE_MS = 5 * 60 * 1000

function tierTone(tier) {
  if (tier === 'A') return 'accent'
  if (tier === 'B') return 'warm'
  if (tier === 'C') return 'info'
  return 'default'
}

function MiniLeadRow({ lead }) {
  const tier = lead.tier || 'C'
  return (
    <div className={`scrape-lead-row tier-${tier.toLowerCase()}`}>
      <span className={`tier-badge tone-${tierTone(tier)}`}>{tier}</span>
      <span className="scrape-lead-name">{lead.name}</span>
      <span className="scrape-lead-meta">
        {lead.category || '—'}
        {lead.phone ? ` · ${lead.phone}` : ''}
        {lead.website ? ' · website' : ''}
      </span>
      <span className="scrape-lead-score">{lead.quality_score ?? '—'}</span>
    </div>
  )
}

export default function ScrapeForm({ onResult }) {
  const [niche, setNiche] = useState('')
  const [location, setLocation] = useState('')
  const [maxResults, setMaxResults] = useState(20)
  const [minScore, setMinScore] = useState(40)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('queued')
  const [message, setMessage] = useState(null)
  const [banner, setBanner] = useState(null)
  const [keptPreview, setKeptPreview] = useState([])
  const [counts, setCounts] = useState({ raw: 0, kept: 0, dropped: 0 })
  const [relaxed, setRelaxed] = useState(false)
  const [partial, setPartial] = useState(false)
  const pollRef = useRef(null)
  const startedAtRef = useRef(0)

  const intent = useMemo(() => previewIntent(niche), [niche])

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearTimeout(pollRef.current)
        pollRef.current = null
      }
    }
  }, [])

  const reset = () => {
    setRunning(false)
    setProgress(0)
    setStage('queued')
    setKeptPreview([])
    setCounts({ raw: 0, kept: 0, dropped: 0 })
    setRelaxed(false)
    setPartial(false)
    if (pollRef.current) {
      clearTimeout(pollRef.current)
      pollRef.current = null
    }
  }

  const pollJob = (jobId) => {
    const tick = async () => {
      try {
        if (Date.now() - startedAtRef.current > MAX_POLL_AGE_MS) {
          setBanner({ type: 'err', text: 'Scrape timed out (5 min). Try a narrower query.' })
          reset()
          return
        }
        const status = await api.getScrapeJob(jobId)
        setProgress(Math.round((status.progress ?? 0) * 100))
        setStage(status.stage || 'queued')
        setCounts({
          raw: status.raw_count || 0,
          kept: status.kept_count || 0,
          dropped: status.dropped_count || 0,
        })
        setKeptPreview(status.kept_preview || [])
        setRelaxed(!!status.relaxed_filter)
        setPartial(!!status.partial)
        if (status.message) setMessage(status.message)

        if (status.finished) {
          if (status.error) {
            setBanner({ type: 'err', text: status.error })
            reset()
            return
          }
          setProgress(100)
          setStage('done')
          const r = status.result || {}
          setBanner({
            type: 'ok',
            text: `Done · kept ${r.kept_count ?? 0}/${r.raw_count ?? 0} · ${
              r.inserted_count ?? 0
            } new, ${r.updated_count ?? 0} updated.${
              status.partial ? ' (partial)' : ''
            }${status.relaxed_filter ? ' (relaxed filter)' : ''}`,
          })
          onResult?.(r)
          setRunning(false)
          if (pollRef.current) {
            clearTimeout(pollRef.current)
            pollRef.current = null
          }
          return
        }
        pollRef.current = setTimeout(tick, POLL_INTERVAL_MS)
      } catch (err) {
        setBanner({ type: 'err', text: err.message || 'Polling failed.' })
        reset()
      }
    }
    tick()
  }

  const submit = async (e) => {
    e?.preventDefault?.()
    if (!niche.trim() || !location.trim()) {
      setBanner({ type: 'err', text: 'Niche and location are both required.' })
      return
    }
    reset()
    setRunning(true)
    setProgress(2)
    setStage('queued')
    startedAtRef.current = Date.now()
    setMessage(`Starting scrape for "${niche}" in ${location}…`)
    setBanner(null)
    try {
      const { job_id: jobId } = await api.createScrapeJob({
        niche: niche.trim(),
        location: location.trim(),
        max_results: Number(maxResults),
        min_quality_score: Number(minScore),
      })
      pollJob(jobId)
    } catch (err) {
      setBanner({ type: 'err', text: err.message || 'Failed to start scrape.' })
      reset()
    }
  }

  const stageLabel = STAGE_LABELS[stage] || stage

  return (
    <form onSubmit={submit}>
      <div className="hero">
        <h1 className="hero-title">What leads do you need?</h1>
      </div>

      <div className="prompt-card">
        <div className="prompt-row">
          <div className="field">
            <label htmlFor="niche">Niche</label>
            <input
              id="niche"
              className="input"
              list="niche-suggestions"
              placeholder="dental clinic"
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
              disabled={running}
              autoComplete="off"
            />
            <datalist id="niche-suggestions">
              {NICHE_SUGGESTIONS.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </div>
          <div className="field">
            <label htmlFor="location">Location</label>
            <input
              id="location"
              className="input"
              placeholder="Portland, OR"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              disabled={running}
              autoComplete="off"
            />
          </div>
          <div className="field">
            <label htmlFor="max">Max results</label>
            <input
              id="max"
              className="input"
              type="number"
              min={1}
              max={100}
              value={maxResults}
              onChange={(e) => setMaxResults(e.target.value)}
              disabled={running}
            />
          </div>
          <div className="field">
            <label htmlFor="score">Min score</label>
            <input
              id="score"
              className="input"
              type="number"
              min={0}
              max={100}
              value={minScore}
              onChange={(e) => setMinScore(e.target.value)}
              disabled={running}
            />
          </div>
        </div>

        {niche.trim() && location.trim() ? (
          <div className="intent-preview">
            <span className="intent-chip">
              Searching: <strong>{intent.cleaned_niche}</strong> in <strong>{location}</strong>
            </span>
            <span className={`intent-chip mode-${intent.require_website ? 'online' : 'offline'}`}>
              {intent.mode_label}
            </span>
          </div>
        ) : null}

        <div className="prompt-foot">
          <div style={{ flex: 1 }} />
          <Btn
            kind="primary"
            icon={running ? 'refresh' : 'bolt'}
            disabled={running}
            type="submit"
          >
            {running ? 'Running scraper…' : 'Generate leads'}
          </Btn>
        </div>
      </div>

      {(running || progress > 0) ? (
        <div className="scrape-progress mt-22">
          <div className="scrape-progress-circle">
            <ProgressBarCircle value={Math.round(progress)} size="xxs" />
          </div>
          <div className="scrape-progress-meta">
            <div className="scrape-progress-row">
              <div className="flux-loading">
                <LoadingIndicator type="line-spinner" size="sm" />
              </div>
              <div className="scrape-progress-text">
                <strong>{stageLabel}</strong>
                <span>
                  {message || `${niche || 'niche'} · ${location || 'location'}`}
                  {counts.raw ? ` · raw ${counts.raw}` : ''}
                  {counts.kept ? ` · kept ${counts.kept}` : ''}
                  {partial ? ' · partial' : ''}
                  {relaxed ? ' · relaxed' : ''}
                </span>
              </div>
            </div>
            <div className="scrape-progress-bar" aria-hidden>
              <div className="scrape-progress-bar-fill" style={{ width: `${Math.round(progress)}%` }} />
            </div>
          </div>
        </div>
      ) : null}

      {keptPreview.length > 0 && running ? (
        <div className="scrape-preview mt-22">
          <header className="scrape-preview-head">
            <strong>Live leads</strong>
            <span>{keptPreview.length} kept · streaming as we score</span>
          </header>
          <div className="scrape-preview-list">
            {keptPreview.map((lead, i) => (
              <MiniLeadRow key={`${lead.name}-${i}`} lead={lead} />
            ))}
          </div>
        </div>
      ) : null}

      {banner && !running ? (
        <div
          className={`banner mt-22 ${
            banner.type === 'err' ? 'err' : banner.type === 'ok' ? 'ok' : ''
          }`}
        >
          {banner.text}
        </div>
      ) : null}
    </form>
  )
}
