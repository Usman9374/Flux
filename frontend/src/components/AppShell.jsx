import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Icon } from './Icon.jsx'
import { api } from '../lib/api.js'

const NAV = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/leads', label: 'Leads', icon: 'leads' },
]

const PAGE_TITLES = {
  '/': { crumb: 'Overview', title: 'Dashboard' },
  '/leads': { crumb: 'Pipeline', title: 'Leads' },
}

function resolveMeta(pathname) {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname]
  if (/^\/leads\/[^/]+$/.test(pathname)) return { crumb: 'Pipeline · Lead', title: 'Lead detail' }
  return { crumb: 'Flux', title: 'Flux' }
}

export default function AppShell() {
  const { pathname } = useLocation()
  const meta = resolveMeta(pathname)
  const [backend, setBackend] = useState({ ok: null, version: null })

  useEffect(() => {
    let cancelled = false
    api
      .health()
      .then((d) => !cancelled && setBackend({ ok: true, version: d?.version || null }))
      .catch(() => !cancelled && setBackend({ ok: false, version: null }))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden />
          <span className="brand-name">Flux</span>
          <span className="brand-sub">Leads</span>
        </div>

        <nav className="nav" aria-label="Primary">
          <div className="nav-section">Workspace</div>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              <span className="nav-icon">
                <Icon name={item.icon} size={16} />
              </span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="who">Flux Operator</span>
          <span>Production-grade lead intelligence</span>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <span className="crumb">{meta.crumb}</span>
          <h1>· {meta.title}</h1>
          <div className="spacer" />
          <span className="env" title="Backend status">
            <span className={`dot ${backend.ok === false ? 'err' : ''}`} />
            {backend.ok === null
              ? 'Checking backend…'
              : backend.ok
                ? `API live${backend.version ? ` · v${backend.version}` : ''}`
                : 'API offline'}
          </span>
        </header>

        <div className="content">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
