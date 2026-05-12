import { Icon } from './Icon.jsx'

const CANONICAL_SIGNALS = [
  {
    key: 'own_website',
    label: 'First-party website',
    hint: 'Lead operates its own domain — strongest reachability signal.',
    weight: '+30',
  },
  {
    key: 'website_aggregator',
    label: 'Aggregator profile',
    hint: 'Listed only on a directory or social profile (Yelp, Facebook, etc.).',
    weight: '+8',
  },
  {
    key: 'has_phone',
    label: 'Phone listed',
    hint: 'Public phone number is available for outreach.',
    weight: '+10',
  },
  {
    key: 'has_address',
    label: 'Physical address',
    hint: 'Street address resolved — confirms a real-world location.',
    weight: '+10',
  },
  {
    key: 'location_match',
    label: 'Location match',
    hint: 'Address contains tokens from the searched city / region.',
    weight: '+10',
  },
  {
    key: 'category_match',
    label: 'Category match',
    hint: 'Listed business category aligns with your niche query.',
    weight: '+15',
  },
  {
    key: 'rating_strong',
    label: 'Strong reputation',
    hint: '4.0★ or higher across public reviews.',
    weight: '+10',
  },
  {
    key: 'reviews_high',
    label: 'Established footprint',
    hint: 'Has 50+ public reviews — long-running operation.',
    weight: '+10',
  },
  {
    key: 'has_name',
    label: 'Verified name',
    hint: 'Business name was extracted cleanly during the scrape.',
    weight: '+5',
  },
]

const KNOWN_KEYS = new Set(CANONICAL_SIGNALS.map((s) => s.key))

function SignalCard({ on, label, hint, weight, index }) {
  return (
    <div
      className={`signal ${on ? 'on' : 'off'} signal-enter`}
      style={{ animationDelay: `${Math.min(index * 50, 600)}ms` }}
    >
      <div className="signal-mark" aria-hidden>
        <Icon name={on ? 'check' : 'x'} size={12} />
      </div>
      <div className="signal-body">
        <div className="signal-row">
          <span className="signal-label">{label}</span>
          {weight ? <span className="signal-weight">{weight}</span> : null}
        </div>
        <div className="signal-hint">{hint}</div>
      </div>
    </div>
  )
}

export default function SignalGrid({ signals }) {
  const map = signals && typeof signals === 'object' ? signals : {}
  const extras = Object.entries(map).filter(([k, v]) => v && !KNOWN_KEYS.has(k))

  return (
    <div className="signal-grid">
      {CANONICAL_SIGNALS.map((s, i) => (
        <SignalCard
          key={s.key}
          on={!!map[s.key]}
          label={s.label}
          hint={s.hint}
          weight={s.weight}
          index={i}
        />
      ))}
      {extras.map(([k], i) => (
        <SignalCard
          key={k}
          on
          label={k.replace(/_/g, ' ')}
          hint="Custom signal recorded by the scraper."
          index={CANONICAL_SIGNALS.length + i}
        />
      ))}
    </div>
  )
}
