export default function EmptyState({ title, hint, action }) {
  return (
    <div className="empty">
      <div className="title">{title}</div>
      {hint ? <div className="hint">{hint}</div> : null}
      {action ? <div className="mt-12">{action}</div> : null}
    </div>
  )
}
