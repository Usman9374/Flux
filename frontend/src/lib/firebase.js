import { initializeApp } from 'firebase/app'
import { getAuth, GoogleAuthProvider } from 'firebase/auth'
import { getFirestore } from 'firebase/firestore'

const firebaseConfig = {
  apiKey: 'AIzaSyA1m-TfUJDuInw177F8BKnBYKQNlmaU4BQ',
  authDomain: 'flux-a0191.firebaseapp.com',
  projectId: 'flux-a0191',
  storageBucket: 'flux-a0191.firebasestorage.app',
  messagingSenderId: '653587379932',
  appId: '1:653587379932:web:232fd2bd6a8c5aa103e619',
  measurementId: 'G-V2BWG1C3FK',
}

export const app = initializeApp(firebaseConfig)
export const auth = getAuth(app)
export const db = getFirestore(app)
export const googleProvider = new GoogleAuthProvider()

export const ADMIN_EMAILS = [
  'muhammadnabeer2004@gmail.com',
  'muhammadusman193744@gmail.com',
]

export function isAdminEmail(email) {
  if (!email) return false
  return ADMIN_EMAILS.includes(email.toLowerCase())
}
