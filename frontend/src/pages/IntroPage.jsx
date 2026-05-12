import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Velaris from '../components/forgeui/velaris.jsx'

const VELARIS_COLORS = ['#86efac', '#4ade80', '#1f6b45', '#0a0e0c']

export default function IntroPage() {
  const navigate = useNavigate()

  useEffect(() => {
    const t = setTimeout(() => navigate('/', { replace: true }), 2500)
    return () => clearTimeout(t)
  }, [navigate])

  return (
    <div className="intro-screen" onClick={() => navigate('/', { replace: true })}>
      <Velaris bg="#07090a" colors={VELARIS_COLORS} speed={1.6} grain={0.25} height="100vh">
        <div className="intro-center">
          <h1 className="intro-mark">flux<span className="intro-dot">.</span></h1>
        </div>
      </Velaris>
    </div>
  )
}
