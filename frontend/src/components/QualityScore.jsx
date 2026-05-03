export default function QualityScore({ value }) {
  if (value === null || value === undefined) {
    return <span className="muted">—</span>
  }
  const v = Math.max(0, Math.min(100, Number(value)))
  const tier = v >= 70 ? 'high' : v >= 45 ? '' : 'low'
  return (
    <div className="quality" title={`Quality score: ${v}/100`}>
      <div className="track">
        <div className={`fill ${tier}`} style={{ width: `${v}%` }} />
      </div>
      <span className="num">{v}</span>
    </div>
  )
}
