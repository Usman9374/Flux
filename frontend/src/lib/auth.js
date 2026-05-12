import { useEffect, useState } from 'react'
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as firebaseSignOut,
} from 'firebase/auth'
import { auth, googleProvider, isAdminEmail } from './firebase.js'
import { ensureUserProfile } from './userProfile.js'

export function isSignedIn() {
  return !!auth.currentUser
}

export function signInWithEmail(email, password) {
  return signInWithEmailAndPassword(auth, email, password)
}

export function signUpWithEmail(email, password) {
  return createUserWithEmailAndPassword(auth, email, password)
}

export function signInWithGoogle() {
  return signInWithPopup(auth, googleProvider)
}

export function signOut() {
  return firebaseSignOut(auth)
}

export function useAuth() {
  const [user, setUser] = useState(() => auth.currentUser)
  const [profile, setProfile] = useState(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    const unsub = onAuthStateChanged(auth, async (u) => {
      setUser(u)
      if (!u) {
        setProfile(null)
        setReady(true)
        return
      }
      try {
        const timeout = new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Firestore profile lookup timed out')), 3000),
        )
        const p = await Promise.race([ensureUserProfile(u), timeout])
        if (!cancelled) setProfile(p)
      } catch (err) {
        if (!cancelled) {
          setProfile({
            uid: u.uid,
            email: u.email,
            role: isAdminEmail(u.email) ? 'admin' : 'user',
            _error: err?.message || String(err),
          })
        }
      } finally {
        if (!cancelled) setReady(true)
      }
    })
    return () => {
      cancelled = true
      unsub()
    }
  }, [])

  const role = profile?.role || (isAdminEmail(user?.email) ? 'admin' : user ? 'user' : null)

  return {
    user,
    profile,
    role,
    isAdmin: role === 'admin',
    signedIn: !!user,
    ready,
    signInWithEmail,
    signUpWithEmail,
    signInWithGoogle,
    signOut,
  }
}
