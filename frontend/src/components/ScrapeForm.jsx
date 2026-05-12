import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
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
]

export default function ScrapeForm({ onResult }) {
  const [niche, setNiche] = useState('')
  const [location, setLocation] = useState('')
  const [maxResults, setMaxResults] = useState(20)
  const [minScore, setMinScore] = useState(35)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState(null)
  const tickRef = useRef(null)

  useEffect(() => {
    if (!running) {
      if (tickRef.current) clearInterval(tickRef.current)
      tickRef.current = null
      return
    }
    setProgress(8)
    tickRef.current = setInterval(() => {
      setProgress((p) => {
        if (p >= 92) return p
        const remaining = 92 - p
        return Math.min(92, p + Math.max(0.6, remaining * 0.06))
      })
    }, 320)
    return () => {
      if (tickRef.current) clearInterval(tickRef.current)
      tickRef.current = null
    }
  }, [running])

  const submit = async (e) => {
    e?.preventDefault?.()
    if (!niche.trim() || !location.trim()) {
      setMessage({ type: 'err', text: 'Niche and location are both required.' })
      return
    }
    setRunning(true)
    setProgress(8)
    setMessage({ type: 'info', text: `Scraping "${niche}" in ${location}…` })
    try {
      const result = await api.scrape({
        niche: niche.trim(),
        location: location.trim(),
        max_results: Number(maxResults),
        min_quality_score: Number(minScore),
      })
      setProgress(100)
      setMessage({
        type: 'ok',
        text: `Done · kept ${result.kept_count}/${result.raw_count} · ${result.inserted_count} new, ${result.updated_count} updated.`,
      })
      onResult?.(result)
    } catch (err) {
      setMessage({ type: 'err', text: err.message || 'Scrape failed.' })
    } finally {
      setRunning(false)
      setTimeout(() => setProgress(0), 800)
    }
  }

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
                <strong>Scraping leads</strong>
                <span>
                  {niche || 'niche'} · {location || 'location'} · target {maxResults}
                </span>
              </div>
            </div>
            <div className="scrape-progress-bar" aria-hidden>
              <div className="scrape-progress-bar-fill" style={{ width: `${Math.round(progress)}%` }} />
            </div>
          </div>
        </div>
      ) : null}

      {message && !running ? (
        <div
          className={`banner mt-22 ${
            message.type === 'err' ? 'err' : message.type === 'ok' ? 'ok' : ''
          }`}
        >
          {message.text}
        </div>
      ) : null}
    </form>
  )
}
