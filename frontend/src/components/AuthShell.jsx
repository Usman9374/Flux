import LumaDrift from './forgeui/lumadrift.jsx'
import { RatingBadge } from './foundations/rating-badge.tsx'

const TESTIMONIALS = [
  { title: 'Cut prospecting time in half.', subtitle: 'verified operator' },
  { title: 'Best lead quality I’ve seen.', subtitle: 'agency owner' },
  { title: 'Closes the gap between scrape and outreach.', subtitle: 'B2B founder' },
]

export default function AuthShell({ children }) {
  return (
    <div className="auth-shell">
      <div className="auth-bg" aria-hidden>
        <LumaDrift speed={1.2} height="100%" />
      </div>
      <div className="auth-overlay" aria-hidden />
      <div className="auth-frame">
        <div className="auth-brand">
          <span className="auth-brand-mark">F</span>
          <span className="auth-brand-name">flux<span className="auth-brand-dot">.</span></span>
        </div>
        <div className="auth-card-wrap">{children}</div>
        <div className="auth-testimonials">
          {TESTIMONIALS.map((t) => (
            <RatingBadge
              key={t.title}
              title={t.title}
              subtitle={t.subtitle}
              rating={5}
              theme="light"
              className="auth-testimonial"
            />
          ))}
        </div>
      </div>
    </div>
  )
}
