import { Icon } from './Icon.jsx'

const CANONICAL_SIGNALS = [
  {
    key: 'own_website',
    label: 'First-party website',
    hint: 'Lead operates its own domain — strongest reachability signal.',
    weight: '+25',
  },
  {
    key: 'website_confirmed',
    label: 'Website cross-verified',
    hint: 'Independent search-engine result matched the same homepage.',
    weight: '+ confidence',
  },
  {
    key: 'has_phone',
    label: 'Phone listed',
    hint: 'Public phone number passes spam/toll-free checks.',
    weight: '+15',
  },
  {
    key: 'has_named_email',
    label: 'Named email address',
    hint: 'A direct mailbox (named contact) was found, not just info@.',
    weight: '+20',
  },
  {
    key: 'has_generic_email',
    label: 'Generic email address',
    hint: 'A shared mailbox (info@/contact@) was found.',
    weight: '+12',
  },
  {
    key: 'has_socials',
    label: 'Active social presence',
    hint: '2+ social platforms with real business handles (not share buttons).',
    weight: '+4',
  },
  {
    key: 'category_match',
    label: 'Category match',
    hint: "Listed Maps category matches one of your niche's tokens.",
    weight: '+15',
  },
  {
    key: 'location_match',
    label: 'Location match',
    hint: 'Address contains a token from your queried location.',
    weight: '+10',
  },
  {
    key: 'rating_strong',
    label: 'Strong reputation',
    hint: '4.0★ or higher with 25+ public reviews.',
    weight: '+8',
  },
  {
    key: 'reviews_high',
    label: 'Established footprint',
    hint: '100+ public reviews — long-running operation.',
    weight: '+5',
  },
  {
    key: 'offline_verified',
    label: 'Verified offline',
    hint: 'Search engine could not find a first-party website for this business.',
    weight: 'offline mode',
  },
  {
    key: 'website_unverified',
    label: 'Possible website (low confidence)',
    hint: 'A homepage may exist but the match confidence is below the verify threshold.',
    weight: 'flagged',
  },
  {
    key: 'has_description',
    label: 'Editorial description',
    hint: '80+ char description from the homepage <meta> or Maps summary.',
    weight: '+3',
  },
  {
    key: 'has_hours',
    label: 'Hours present',
    hint: 'Public operating hours found.',
    weight: '+2',
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
  const extras = Object.entries(map).filter(
    ([k, v]) => v && !KNOWN_KEYS.has(k) && typeof v !== 'string',
  )

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
