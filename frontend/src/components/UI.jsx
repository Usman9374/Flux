import { Icon } from './Icon.jsx'

export function Pill({ tone = 'default', dot = false, children, className = '' }) {
  const cls = `pill${tone !== 'default' ? ' ' + tone : ''}${className ? ' ' + className : ''}`
  return (
    <span className={cls}>
      {dot ? <span className="dot" /> : null}
      {children}
    </span>
  )
}

export function Btn({
  kind = 'ghost',
  icon,
  children,
  sm,
  type = 'button',
  onClick,
  disabled,
  className = '',
  as,
  ...rest
}) {
  const Tag = as || 'button'
  const cls = `btn ${kind}${sm ? ' sm' : ''}${className ? ' ' + className : ''}`
  const iconSize = sm ? 12 : 14
  const props = {
    className: cls,
    onClick,
    disabled,
    ...(Tag === 'button' ? { type } : {}),
    ...rest,
  }
  return (
    <Tag {...props}>
      {icon ? <Icon name={icon} size={iconSize} /> : null}
      {children}
    </Tag>
  )
}

export function Panel({ title, sub, action, children, className = '' }) {
  return (
    <section className={`panel${className ? ' ' + className : ''}`}>
      {title || action ? (
        <header className="panel-head">
          <div style={{ flex: 1, minWidth: 0 }}>
            {title ? <h3>{title}</h3> : null}
            {sub ? <div className="sub">{sub}</div> : null}
          </div>
          {action}
        </header>
      ) : null}
      <div className="panel-body">{children}</div>
    </section>
  )
}

export function ScoreRing({ score, size = 36, sw = 3 }) {
  if (score === null || score === undefined) {
    return (
      <div
        className="score-ring"
        style={{ width: size, height: size }}
        aria-label="Unscored"
      >
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={(size - sw) / 2}
            stroke="var(--border)"
            strokeWidth={sw}
            fill="none"
          />
        </svg>
        <div
          className="score-ring-num"
          style={{ fontSize: size * 0.32, color: 'var(--text-muted)' }}
        >
          —
        </div>
      </div>
    )
  }
  const v = Math.max(0, Math.min(100, Number(score)))
  const r = (size - sw) / 2
  const c = 2 * Math.PI * r
  const off = c - (v / 100) * c
  const tone =
    v >= 80
      ? 'var(--accent)'
      : v >= 65
        ? 'var(--accent-warm)'
        : v >= 50
          ? 'var(--accent-amber)'
          : 'var(--text-dim)'
  return (
    <div
      className="score-ring"
      style={{ width: size, height: size }}
      aria-label={`Quality score ${v}/100`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="var(--border)"
          strokeWidth={sw}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={tone}
          strokeWidth={sw}
          fill="none"
          strokeDasharray={c}
          strokeDashoffset={off}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 800ms cubic-bezier(.2,.8,.2,1)' }}
        />
      </svg>
      <div
        className="score-ring-num"
        style={{ fontSize: size * 0.32, color: tone }}
      >
        {v}
      </div>
    </div>
  )
}

export function CmdPalette({ open, onClose, onNavigate }) {
  if (!open) return null
  const items = [
    { k: '/', label: 'Open dashboard', hint: 'G then D', icon: 'dashboard' },
    { k: '/leads', label: 'Browse leads', hint: 'G then L', icon: 'leads' },
  ]
  return (
    <div
      className="cmd-overlay"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.72)',
        zIndex: 50,
        display: 'grid',
        placeItems: 'start center',
        paddingTop: '12vh',
        animation: 'fadeIn 120ms ease',
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 560,
          maxWidth: 'calc(100vw - 32px)',
          background: 'var(--surface-1)',
          border: '1px solid var(--border-strong)',
          borderRadius: 12,
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '14px 16px',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <Icon name="search" size={16} />
          <input
            autoFocus
            placeholder="Type a command, lead, workflow…"
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: 14,
              fontFamily: 'var(--sans)',
              color: 'var(--text)',
              fontWeight: 600,
            }}
          />
          <span className="kbd">ESC</span>
        </div>
        <div style={{ padding: 6 }}>
          <div
            style={{
              fontSize: 10,
              fontFamily: 'var(--mono)',
              letterSpacing: '0.08em',
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              padding: '6px 10px',
              fontWeight: 700,
            }}
          >
            Quick actions
          </div>
          {items.map((it) => (
            <button
              key={it.k}
              onClick={() => {
                onNavigate(it.k)
                onClose()
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                width: '100%',
                padding: '9px 10px',
                border: 'none',
                background: 'transparent',
                color: 'var(--text)',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 13,
                fontFamily: 'var(--sans)',
                fontWeight: 600,
              }}
              onMouseEnter={(e) =>
                (e.currentTarget.style.background = 'var(--surface-2)')
              }
              onMouseLeave={(e) =>
                (e.currentTarget.style.background = 'transparent')
              }
            >
              <Icon name={it.icon} size={15} />
              <span style={{ flex: 1, textAlign: 'left' }}>{it.label}</span>
              <span
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 10,
                  color: 'var(--text-muted)',
                  fontWeight: 600,
                }}
              >
                {it.hint}
              </span>
            </button>
          ))}
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            padding: '10px 14px',
            borderTop: '1px solid var(--border)',
            fontSize: 11,
            color: 'var(--text-muted)',
            fontFamily: 'var(--mono)',
            fontWeight: 600,
          }}
        >
          <span>↑↓ navigate</span>
          <span>↵ select</span>
          <span style={{ flex: 1 }} />
          <span style={{ color: 'var(--accent)' }}>● flux v2.4.1</span>
        </div>
      </div>
    </div>
  )
}
