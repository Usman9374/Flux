import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/auth.js'

export default function AuthGate() {
  const { signedIn, ready } = useAuth()
  const location = useLocation()
  if (!ready) return null
  if (!signedIn) {
    return <Navigate to="/signin" replace state={{ from: location.pathname + location.search }} />
  }
  return <Outlet />
}

export function PublicOnly() {
  const { signedIn, ready } = useAuth()
  if (!ready) return null
  if (signedIn) return <Navigate to="/" replace />
  return <Outlet />
}

export function AdminGate() {
  const { ready, signedIn, isAdmin } = useAuth()
  const location = useLocation()
  if (!ready) return null
  if (!signedIn) {
    return <Navigate to="/signin" replace state={{ from: location.pathname + location.search }} />
  }
  if (!isAdmin) {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}
