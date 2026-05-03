import { useState } from 'react'
import { api } from '../lib/api.js'
import { Icon } from './Icon.jsx'

const NICHE_SUGGESTIONS = [
  'dental clinic',
  'chiropractor',
  'law firm',
  'roofing contractor',
  'med spa',
  'hvac company',
]

export default function ScrapeForm({ onResult }) {
  const [niche, setNiche] = useState('')
  const [location, setLocation] = useState('')
  const [maxResults, setMaxResults] = useState(20)
  const [minScore, setMinScore] = useState(35)
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    if (!niche.trim() || !location.trim()) {
      setMessage({ type: 'err', text: 'Niche and location are both required.' })
      return
    }
    setRunning(true)
    setMessage({ type: 'info', text: `Scraping "${niche}" in ${location}…` })
    try {
      const result = await api.scrape({
        niche: niche.trim(),
        location: location.trim(),
        max_results: Number(maxResults),
        min_quality_score: Number(minScore),
      })
      setMessage({
        type: 'ok',
        text: `Done · kept ${result.kept_count}/${result.raw_count} · ${result.inserted_count} new, ${result.updated_count} updated.`,
      })
      onResult?.(result)
    } catch (err) {
      setMessage({ type: 'err', text: err.message || 'Scrape failed.' })
    } finally {
      setRunning(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <div className="card-head">
        <div>
          <h3>Scrape new leads</h3>
          <div className="sub">Niche + location → filtered, scored business intelligence.</div>
        </div>
      </div>
      <div className="card-body">
        <div className="form-row">
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
            <label htmlFor="score">Min quality</label>
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
          <div className="field submit">
            <label>&nbsp;</label>
            <button type="submit" className="btn matcha" disabled={running}>
              <Icon name={running ? 'refresh' : 'scrape'} size={14} />
              {running ? 'Scraping…' : 'Run scrape'}
            </button>
          </div>
        </div>

        {message ? (
          <div
            className={`banner mt-12 ${message.type === 'err' ? 'err' : message.type === 'ok' ? 'ok' : ''}`}
          >
            {message.text}
          </div>
        ) : null}
      </div>
    </form>
  )
}
