import { doc, getDoc, serverTimestamp, setDoc } from 'firebase/firestore'
import { db, isAdminEmail } from './firebase.js'

export async function ensureUserProfile(user) {
  if (!user) return null
  const ref = doc(db, 'users', user.uid)
  const snap = await getDoc(ref)
  const desiredRole = isAdminEmail(user.email) ? 'admin' : 'user'

  if (!snap.exists()) {
    const profile = {
      uid: user.uid,
      email: user.email || null,
      displayName: user.displayName || null,
      photoURL: user.photoURL || null,
      role: desiredRole,
      createdAt: serverTimestamp(),
      lastSeenAt: serverTimestamp(),
    }
    await setDoc(ref, profile)
    return { ...profile, createdAt: null, lastSeenAt: null }
  }

  const existing = snap.data()
  const patch = { lastSeenAt: serverTimestamp() }
  if (existing.role !== desiredRole && isAdminEmail(user.email)) {
    patch.role = 'admin'
  }
  await setDoc(ref, patch, { merge: true })
  return { ...existing, ...patch, role: patch.role || existing.role }
}
