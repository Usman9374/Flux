import QualityScore from './QualityScore.jsx'
import Rating from './Rating.jsx'
import EmptyState from './EmptyState.jsx'
import { formatRelative, hostname } from '../lib/format.js'

function SkeletonRows({ rows = 6 }) {
  return Array.from({ length: rows }).map((_, i) => (
    <tr key={i} className="skel-row">
      {Array.from({ length: 7 }).map((__, j) => (
        <td key={j}>
          <div className="skeleton" style={{ height: 12, width: j === 0 ? '70%' : '50%' }} />
        </td>
      ))}
    </tr>
  ))
}

export default function LeadsTable({ leads, loading, onRowClick, emptyTitle, emptyHint, emptyAction }) {
  const clickable = typeof onRowClick === 'function'
  const handleClick = (lead) => {
    if (clickable) onRowClick(lead)
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Business</th>
            <th>Website</th>
            <th>Location</th>
            <th>Niche</th>
            <th>Rating</th>
            <th>Quality</th>
            <th className="num">Added</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <SkeletonRows rows={6} />
          ) : leads.length === 0 ? (
            <tr>
              <td colSpan={7}>
                <EmptyState title={emptyTitle} hint={emptyHint} action={emptyAction} />
              </td>
            </tr>
          ) : (
            leads.map((lead) => {
              const host = hostname(lead.website)
              return (
                <tr
                  key={lead.id}
                  className={clickable ? 'row-link' : undefined}
                  onClick={clickable ? () => handleClick(lead) : undefined}
                  tabIndex={clickable ? 0 : -1}
                  onKeyDown={
                    clickable
                      ? (e) => {
                          if (e.key === 'Enter') handleClick(lead)
                        }
                      : undefined
                  }
                >
                  <td>
                    <div className="name-cell">
                      <span className="primary">{lead.name}</span>
                      {lead.category ? (
                        <span className="secondary">{lead.category}</span>
                      ) : lead.address ? (
                        <span className="secondary">{lead.address}</span>
                      ) : null}
                    </div>
                  </td>
                  <td className="website-cell">
                    {host ? (
                      <a
                        href={lead.website}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {host}
                      </a>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>{lead.location || <span className="muted">—</span>}</td>
                  <td>
                    {lead.niche ? (
                      <span className="pill ghost">{lead.niche}</span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <Rating value={lead.rating} count={lead.reviews_count} />
                  </td>
                  <td>
                    <QualityScore value={lead.quality_score} />
                  </td>
                  <td className="num text-mute">{formatRelative(lead.created_at)}</td>
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
