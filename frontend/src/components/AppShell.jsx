import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
import { Icon } from './Icon.jsx'
import { CmdPalette, Pill } from './UI.jsx'
import { SpotlightNavbar } from './ui/spotlight-navbar.jsx'
import { api } from '../lib/api.js'
import { signOut as authSignOut, useAuth } from '../lib/auth.js'

const NAV = [
  { to: '/', label: 'New run', icon: 'spark', end: true },
  { to: '/leads', label: 'Leads', icon: 'table' },
]

const SPOTLIGHT_ITEMS = [
  { label: 'New run', href: '/' },
  { label: 'Leads', href: '/leads' },
]

const PAGE_META = {
  '/': { title: 'New run', sub: 'Pick a niche and a location — Flux scrapes the leads' },
  '/leads': { title: 'Leads', sub: 'All scraped, scored leads' },
}

function resolveMeta(pathname) {
  if (PAGE_META[pathname]) return PAGE_META[pathname]
  if (/^\/leads\/[^/]+$/.test(pathname)) {
    return { title: 'Lead detail', sub: 'Full business intelligence for a single lead' }
  }
  return { title: 'Flux', sub: 'Lead intelligence' }
}

function activeSpotlightIndex(pathname) {
  if (pathname === '/') return 0
  if (pathname.startsWith('/leads')) return 1
  return 0
}

export default function AppShell() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const meta = resolveMeta(pathname)
  const [backend, setBackend] = useState({ ok: null, version: null })
  const [cmdOpen, setCmdOpen] = useState(false)
  const [leadsCount, setLeadsCount] = useState(null)
  const { user, isAdmin } = useAuth()

  const spotlightActive = useMemo(() => activeSpotlightIndex(pathname), [pathname])

  useEffect(() => {
    let cancelled = false
    api
      .health()
      .then((d) => !cancelled && setBackend({ ok: true, version: d?.version || null }))
      .catch(() => !cancelled && setBackend({ ok: false, version: null }))
    api
      .listLeads({ limit: 1, offset: 0 })
      .then((d) => !cancelled && setLeadsCount(d?.count ?? 0))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [pathname])

  useEffect(() => {
    const h = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCmdOpen((o) => !o)
      }
      if (e.key === 'Escape') setCmdOpen(false)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  const handleSpotlightClick = (item) => {
    navigate(item.href)
  }

  const handleSignOut = async () => {
    try {
      await authSignOut()
    } finally {
      navigate('/signin', { replace: true })
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="workspace">
          <div className="workspace-mark">F</div>
          <div className="workspace-info">
            <div className="workspace-name">
              Flux
              {isAdmin ? <span className="role-badge">admin</span> : null}
            </div>
            <div className="workspace-plan">
              {user?.email || 'Lead intelligence'}
            </div>
          </div>
        </div>

        <div className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              <span className="nav-icon">
                <Icon name={item.icon} size={15} />
              </span>
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.to === '/leads' && leadsCount !== null ? (
                <span className="nav-meta">{formatCount(leadsCount)}</span>
              ) : null}
            </NavLink>
          ))}
        </div>

        <div className="sidebar-spacer" />

        <div className="sidebar-footer">
          <button className="nav-link sign-out" onClick={handleSignOut}>
            <span className="nav-icon">
              <Icon name="x" size={14} />
            </span>
            <span style={{ flex: 1 }}>Sign out</span>
          </button>
        </div>

        <div className="credits">
          <div className="credits-head">
            <span className="credits-label">Backend</span>
            <span className="credits-num">
              {backend.ok === null
                ? '…'
                : backend.ok
                  ? `v${backend.version || '1.0'}`
                  : 'offline'}
            </span>
          </div>
          <div className="credits-track">
            <div
              className="credits-fill"
              style={{
                width: backend.ok ? '100%' : '0%',
                background:
                  backend.ok === false ? 'var(--accent-err)' : 'var(--accent)',
              }}
            />
          </div>
          <div className="credits-foot">
            <span>Supabase · Render</span>
            <span style={{ color: backend.ok ? 'var(--accent)' : 'var(--text-muted)' }}>
              {backend.ok ? 'Live' : '—'}
            </span>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar topbar-spot">
          <div className="topbar-titles">
            <div className="topbar-title-row">
              <h1>{meta.title}</h1>
              {pathname === '/' ? <Pill tone="accent" dot>FLUX AI</Pill> : null}
            </div>
            <div className="topbar-sub">{meta.sub}</div>
          </div>

          <div className="topbar-spot-center">
            <SpotlightNavbar
              key={spotlightActive}
              items={SPOTLIGHT_ITEMS}
              defaultActiveIndex={spotlightActive}
              onItemClick={handleSpotlightClick}
            />
          </div>

          <button className="cmd-trigger" onClick={() => setCmdOpen(true)}>
            <Icon name="search" size={13} />
            <span className="cmd-text">Jump to…</span>
            <span style={{ display: 'flex', gap: 3 }}>
              <span className="kbd">⌘</span>
              <span className="kbd">K</span>
            </span>
          </button>
          <span
            className={`api-status${backend.ok === false ? ' err' : ''}`}
            title="Backend status"
          >
            <span className="dot" />
            {backend.ok === null
              ? 'Checking…'
              : backend.ok
                ? 'API live'
                : 'API offline'}
          </span>
        </header>

        <div className="content">
          <div className="content-inner content-fade" key={pathname}>
            <Outlet />
          </div>
        </div>
      </div>

      <CmdPalette
        open={cmdOpen}
        onClose={() => setCmdOpen(false)}
        onNavigate={(path) => navigate(path)}
      />
    </div>
  )
}

function formatCount(n) {
  if (n === null || n === undefined) return ''
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K`
  return String(n)
}
