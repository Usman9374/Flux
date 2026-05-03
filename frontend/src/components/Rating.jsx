import { Icon } from './Icon.jsx'

export default function Rating({ value, count }) {
  if (value === null || value === undefined) return <span className="muted">—</span>
  return (
    <span className="rating">
      <span className="star">
        <Icon name="star" size={12} />
      </span>
      <span>{Number(value).toFixed(1)}</span>
      {count !== null && count !== undefined ? (
        <span className="count">({count})</span>
      ) : null}
    </span>
  )
}
