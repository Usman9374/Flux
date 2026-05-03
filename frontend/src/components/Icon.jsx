const STROKE = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

export function Icon({ name, size = 16 }) {
  const props = { width: size, height: size, viewBox: '0 0 24 24', ...STROKE }
  switch (name) {
    case 'dashboard':
      return (
        <svg {...props}>
          <rect x="3" y="3" width="7" height="9" rx="1.5" />
          <rect x="14" y="3" width="7" height="5" rx="1.5" />
          <rect x="14" y="12" width="7" height="9" rx="1.5" />
          <rect x="3" y="16" width="7" height="5" rx="1.5" />
        </svg>
      )
    case 'leads':
      return (
        <svg {...props}>
          <path d="M4 6h16M4 12h16M4 18h10" />
        </svg>
      )
    case 'scrape':
      return (
        <svg {...props}>
          <circle cx="11" cy="11" r="6" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      )
    case 'download':
      return (
        <svg {...props}>
          <path d="M12 4v12" />
          <path d="m7 11 5 5 5-5" />
          <path d="M5 20h14" />
        </svg>
      )
    case 'refresh':
      return (
        <svg {...props}>
          <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8" />
          <path d="M21 3v5h-5" />
          <path d="M21 12a9 9 0 0 1-15.5 6.3L3 16" />
          <path d="M3 21v-5h5" />
        </svg>
      )
    case 'arrow-right':
      return (
        <svg {...props}>
          <path d="M5 12h14" />
          <path d="m13 6 6 6-6 6" />
        </svg>
      )
    case 'arrow-left':
      return (
        <svg {...props}>
          <path d="M19 12H5" />
          <path d="m11 6-6 6 6 6" />
        </svg>
      )
    case 'external':
      return (
        <svg {...props}>
          <path d="M14 4h6v6" />
          <path d="M20 4 10 14" />
          <path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" />
        </svg>
      )
    case 'star':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2.5l2.9 6.3 6.6.7-4.9 4.6 1.4 6.7L12 17.5 5.9 20.8l1.4-6.7L2.5 9.5l6.6-.7L12 2.5z" />
        </svg>
      )
    case 'globe':
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18" />
          <path d="M12 3a14 14 0 0 1 0 18" />
          <path d="M12 3a14 14 0 0 0 0 18" />
        </svg>
      )
    case 'phone':
      return (
        <svg {...props}>
          <path d="M5 4h3l2 5-2 1a11 11 0 0 0 6 6l1-2 5 2v3a2 2 0 0 1-2 2A17 17 0 0 1 3 6a2 2 0 0 1 2-2z" />
        </svg>
      )
    case 'pin':
      return (
        <svg {...props}>
          <path d="M12 21s7-6.5 7-12a7 7 0 1 0-14 0c0 5.5 7 12 7 12z" />
          <circle cx="12" cy="9" r="2.5" />
        </svg>
      )
    case 'copy':
      return (
        <svg {...props}>
          <rect x="9" y="9" width="11" height="11" rx="2" />
          <path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" />
        </svg>
      )
    case 'tag':
      return (
        <svg {...props}>
          <path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9-9-9z" />
          <circle cx="8" cy="8" r="1.4" fill="currentColor" stroke="none" />
        </svg>
      )
    case 'calendar':
      return (
        <svg {...props}>
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <path d="M3 10h18" />
          <path d="M8 3v4M16 3v4" />
        </svg>
      )
    case 'info':
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v5" />
          <circle cx="12" cy="8" r="0.7" fill="currentColor" stroke="none" />
        </svg>
      )
    case 'check':
      return (
        <svg {...props}>
          <path d="m5 12 4.5 4.5L19 7" />
        </svg>
      )
    case 'x':
      return (
        <svg {...props}>
          <path d="M6 6l12 12" />
          <path d="M18 6 6 18" />
        </svg>
      )
    case 'sparkle':
      return (
        <svg {...props}>
          <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" />
        </svg>
      )
    default:
      return null
  }
}
