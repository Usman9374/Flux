import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthShell from '../components/AuthShell.jsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card.jsx'
import { Input } from '../components/ui/input.jsx'
import { Button } from '../components/ui/button.jsx'
import { SocialButton } from '../components/base/buttons/social-button.tsx'
import { signInWithEmail, signInWithGoogle } from '../lib/auth.js'

function friendlyError(err) {
  const code = err?.code || ''
  if (code === 'auth/invalid-credential' || code === 'auth/wrong-password' || code === 'auth/user-not-found') {
    return 'Incorrect email or password.'
  }
  if (code === 'auth/too-many-requests') return 'Too many attempts. Try again later.'
  if (code === 'auth/popup-closed-by-user') return ''
  return err?.message || 'Something went wrong. Try again.'
}

export default function SignInPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e?.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await signInWithEmail(email, password)
      navigate('/intro', { replace: true })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

  const google = async () => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await signInWithGoogle()
      navigate('/intro', { replace: true })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell>
      <Card className="auth-card">
        <CardHeader className="auth-card-head">
          <CardTitle className="auth-card-title">welcome back to flux.</CardTitle>
          <CardDescription className="auth-card-sub">sign in to start prospecting</CardDescription>
        </CardHeader>
        <CardContent className="auth-card-body">
          <form onSubmit={submit} className="auth-form">
            <label className="auth-field">
              <span className="auth-field-label">email</span>
              <Input
                type="email"
                placeholder="you@workmail.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </label>
            <label className="auth-field">
              <span className="auth-field-label">password</span>
              <Input
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </label>
            {error ? <div className="auth-error">{error}</div> : null}
            <Button type="submit" className="auth-submit" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
          <div className="auth-divider"><span>or</span></div>
          <SocialButton social="google" theme="gray" size="lg" onClick={google} className="auth-social" disabled={busy}>
            Continue with Google
          </SocialButton>
          <p className="auth-foot">
            New to flux? <Link to="/signup">Create an account</Link>
          </p>
        </CardContent>
      </Card>
    </AuthShell>
  )
}
