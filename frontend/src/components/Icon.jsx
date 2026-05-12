const STROKE = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

export function Icon({ name, size = 16 }) {
  const props = { width: size, height: size, viewBox: '0 0 24 24', ...STROKE }
  switch (name) {
    case 'spark':
    case 'sparkle':
      return (
        <svg {...props}>
          <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
        </svg>
      )
    case 'bolt':
    case 'zap':
      return (
        <svg {...props}>
          <path d="M13 3 4 14h7l-1 7 9-11h-7z" />
        </svg>
      )
    case 'pulse':
      return (
        <svg {...props}>
          <path d="M3 12h4l2-6 4 12 2-6h6" />
        </svg>
      )
    case 'table':
    case 'leads':
      return (
        <svg {...props}>
          <rect x="3" y="4" width="18" height="16" rx="1.5" />
          <path d="M3 10h18M3 16h18M9 4v16M15 4v16" />
        </svg>
      )
    case 'flow':
      return (
        <svg {...props}>
          <circle cx="5" cy="6" r="2" />
          <circle cx="19" cy="6" r="2" />
          <circle cx="12" cy="18" r="2" />
          <path d="M7 6h10M6 8l5 8M18 8l-5 8" />
        </svg>
      )
    case 'chart':
    case 'insights':
      return (
        <svg {...props}>
          <path d="M3 21V3M3 21h18M7 17V11M12 17V7M17 17v-4" />
        </svg>
      )
    case 'mail':
      return (
        <svg {...props}>
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="m3 7 9 7 9-7" />
        </svg>
      )
    case 'dashboard':
      return (
        <svg {...props}>
          <rect x="3" y="3" width="7" height="9" rx="1.5" />
          <rect x="14" y="3" width="7" height="5" rx="1.5" />
          <rect x="14" y="12" width="7" height="9" rx="1.5" />
          <rect x="3" y="16" width="7" height="5" rx="1.5" />
        </svg>
      )
    case 'scrape':
    case 'search':
      return (
        <svg {...props}>
          <circle cx="11" cy="11" r="6" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      )
    case 'download':
    case 'export':
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
          <path d="M21 12a9 9 0 0 1-9 9 9 9 0 0 1-7-3.3" />
          <path d="M3 12a9 9 0 0 1 9-9 9 9 0 0 1 7 3.3" />
          <path d="M21 3v5h-5M3 21v-5h5" />
        </svg>
      )
    case 'arrow-right':
      return (
        <svg {...props}>
          <path d="M5 12h14" />
          <path d="m13 6 6 6-6 6" />
        </svg>
      )
    case 'arrow-up':
      return (
        <svg {...props}>
          <path d="M12 19V5" />
          <path d="m6 11 6-6 6 6" />
        </svg>
      )
    case 'arrow-down':
      return (
        <svg {...props}>
          <path d="M12 5v14" />
          <path d="m6 13 6 6 6-6" />
        </svg>
      )
    case 'arrow-updown':
      return (
        <svg {...props}>
          <path d="M7 4v16" />
          <path d="m3 8 4-4 4 4" />
          <path d="M17 20V4" />
          <path d="m13 16 4 4 4-4" />
        </svg>
      )
    case 'arrow-left':
      return (
        <svg {...props}>
          <path d="M19 12H5" />
          <path d="m11 6-6 6 6 6" />
        </svg>
      )
    case 'chev-d':
      return (
        <svg {...props}>
          <path d="m6 9 6 6 6-6" />
        </svg>
      )
    case 'chev-r':
      return (
        <svg {...props}>
          <path d="m9 6 6 6-6 6" />
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
    case 'plus':
      return (
        <svg {...props}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      )
    case 'shield':
      return (
        <svg {...props}>
          <path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" />
        </svg>
      )
    case 'bell':
      return (
        <svg {...props}>
          <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10 21a2 2 0 0 0 4 0" />
        </svg>
      )
    case 'team':
      return (
        <svg {...props}>
          <circle cx="9" cy="8" r="3.5" />
          <circle cx="17" cy="9" r="2.5" />
          <path d="M3 21c0-3.3 2.7-6 6-6s6 2.7 6 6M15 21c0-2.5 1.5-4.5 4-5" />
        </svg>
      )
    case 'history':
      return (
        <svg {...props}>
          <path d="M3 12a9 9 0 1 0 3-6.7" />
          <path d="M3 4v5h5M12 7v5l3 2" />
        </svg>
      )
    case 'layers':
      return (
        <svg {...props}>
          <path d="m12 3 9 5-9 5-9-5 9-5z" />
          <path d="m3 13 9 5 9-5M3 18l9 5 9-5" />
        </svg>
      )
    case 'database':
      return (
        <svg {...props}>
          <ellipse cx="12" cy="5" rx="8" ry="3" />
          <path d="M4 5v14a8 3 0 0 0 16 0V5M4 12a8 3 0 0 0 16 0" />
        </svg>
      )
    case 'eye':
      return (
        <svg {...props}>
          <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      )
    case 'flag':
      return (
        <svg {...props}>
          <path d="M4 21V4M4 4h12l-2 4 2 4H4" />
        </svg>
      )
    case 'filter':
      return (
        <svg {...props}>
          <path d="M3 5h18l-7 9v6l-4-2v-4z" />
        </svg>
      )
    case 'more':
      return (
        <svg {...props}>
          <circle cx="5" cy="12" r="1.3" fill="currentColor" stroke="none" />
          <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
          <circle cx="19" cy="12" r="1.3" fill="currentColor" stroke="none" />
        </svg>
      )
    case 'building':
      return (
        <svg {...props}>
          <path d="M4 21V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v15M4 21h16M9 9h.01M15 9h.01M9 13h.01M15 13h.01M9 17h.01M15 17h.01" />
        </svg>
      )
    default:
      return null
  }
}
