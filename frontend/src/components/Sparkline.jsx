import { Area, AreaChart, ResponsiveContainer } from 'recharts'

export default function Sparkline({ data, color = 'var(--accent)', height = 36, gradientId = 'sparkGradient' }) {
  if (!data || data.length === 0) {
    return <div style={{ height }} />
  }
  const safe = data.map((v, i) => ({ i, v: Number(v) || 0 }))
  return (
    <div className="sparkline" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={safe} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.45} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.6}
            fill={`url(#${gradientId})`}
            isAnimationActive
            animationDuration={900}
            animationEasing="ease-out"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
