import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthShell from '../components/AuthShell.jsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card.jsx'
import { Input } from '../components/ui/input.jsx'
import { Button } from '../components/ui/button.jsx'
import { SocialButton } from '../components/base/buttons/social-button.tsx'
import { signUpWithEmail, signInWithGoogle } from '../lib/auth.js'

function friendlyError(err) {
  const code = err?.code || ''
  if (code === 'auth/email-already-in-use') return 'An account with that email already exists.'
  if (code === 'auth/invalid-email') return 'Enter a valid email address.'
  if (code === 'auth/weak-password') return 'Password must be at least 6 characters.'
  if (code === 'auth/popup-closed-by-user') return ''
  return err?.message || 'Something went wrong. Try again.'
}

export default function SignUpPage() {
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
      await signUpWithEmail(email, password)
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
          <CardTitle className="auth-card-title">create your flux account.</CardTitle>
          <CardDescription className="auth-card-sub">leads that ship in minutes, not days</CardDescription>
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
                placeholder="at least 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                minLength={8}
              />
            </label>
            {error ? <div className="auth-error">{error}</div> : null}
            <Button type="submit" className="auth-submit" disabled={busy}>
              {busy ? 'Creating account…' : 'Create account'}
            </Button>
          </form>
          <div className="auth-divider"><span>or</span></div>
          <SocialButton social="google" theme="gray" size="lg" onClick={google} className="auth-social" disabled={busy}>
            Sign up with Google
          </SocialButton>
          <p className="auth-foot">
            Already have an account? <Link to="/signin">Sign in</Link>
          </p>
        </CardContent>
      </Card>
    </AuthShell>
  )
}
