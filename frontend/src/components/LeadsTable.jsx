import { useMemo } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { Pill, ScoreRing } from './UI.jsx'
import Rating from './Rating.jsx'
import EmptyState from './EmptyState.jsx'
import { Icon } from './Icon.jsx'
import { formatRelative, hostname } from '../lib/format.js'

function tierTone(score) {
  if (score === null || score === undefined) return 'default'
  if (score >= 80) return 'accent'
  if (score >= 65) return 'warm'
  if (score >= 50) return 'info'
  return 'default'
}

function tierLabel(score) {
  if (score === null || score === undefined) return 'UNSCORED'
  if (score >= 80) return 'HIGH'
  if (score >= 65) return 'STRONG'
  if (score >= 50) return 'MID'
  return 'COLD'
}

function SortIndicator({ direction }) {
  if (!direction) return <Icon name="arrow-updown" size={11} />
  if (direction === 'asc') return <Icon name="arrow-up" size={11} />
  return <Icon name="arrow-down" size={11} />
}

function SkeletonRows({ rows = 6, cols }) {
  return Array.from({ length: rows }).map((_, i) => (
    <tr key={i} className="skel-row">
      {Array.from({ length: cols }).map((__, j) => (
        <td key={j}>
          <div className="skeleton" style={{ height: 12, width: j === 0 ? '70%' : '50%' }} />
        </td>
      ))}
    </tr>
  ))
}

function fuzzyIncludes(haystack, needle) {
  if (!needle) return true
  if (haystack === null || haystack === undefined) return false
  return String(haystack).toLowerCase().includes(String(needle).toLowerCase())
}

function globalFilterFn(row, columnId, filterValue) {
  if (!filterValue) return true
  const lead = row.original
  return (
    fuzzyIncludes(lead.name, filterValue) ||
    fuzzyIncludes(lead.website, filterValue) ||
    fuzzyIncludes(lead.niche, filterValue) ||
    fuzzyIncludes(lead.location, filterValue) ||
    fuzzyIncludes(lead.category, filterValue)
  )
}

export default function LeadsTable({
  leads,
  loading,
  onRowClick,
  emptyTitle,
  emptyHint,
  emptyAction,
  globalFilter = '',
  onGlobalFilterChange,
  sorting,
  onSortingChange,
  enableInternalSort = true,
}) {
  const clickable = typeof onRowClick === 'function'

  const columns = useMemo(
    () => [
      {
        id: 'score',
        header: 'Score',
        accessorFn: (l) => l.quality_score ?? -1,
        sortingFn: 'basic',
        size: 60,
        cell: ({ row }) => <ScoreRing score={row.original.quality_score} size={36} sw={3} />,
      },
      {
        id: 'business',
        header: 'Business',
        accessorFn: (l) => l.name || '',
        sortingFn: 'alphanumeric',
        cell: ({ row }) => (
          <div className="name-cell">
            <span className="primary">{row.original.name}</span>
            <span className="secondary">
              {row.original.category || row.original.address || `#${row.original.id}`}
            </span>
          </div>
        ),
      },
      {
        id: 'website',
        header: 'Website',
        accessorFn: (l) => hostname(l.website) || '',
        sortingFn: 'alphanumeric',
        cell: ({ row }) => {
          const host = hostname(row.original.website)
          return host ? (
            <a
              href={row.original.website}
              target="_blank"
              rel="noreferrer"
              className="website-link"
              onClick={(e) => e.stopPropagation()}
            >
              {host}
            </a>
          ) : (
            <span className="muted">—</span>
          )
        },
      },
      {
        id: 'location',
        header: 'Location',
        accessorFn: (l) => l.location || '',
        sortingFn: 'alphanumeric',
        cell: ({ row }) => row.original.location || <span className="muted">—</span>,
      },
      {
        id: 'niche',
        header: 'Niche',
        accessorFn: (l) => l.niche || '',
        sortingFn: 'alphanumeric',
        cell: ({ row }) =>
          row.original.niche ? (
            <Pill tone={tierTone(row.original.quality_score)} dot>
              {tierLabel(row.original.quality_score)} · {row.original.niche}
            </Pill>
          ) : (
            <span className="muted">—</span>
          ),
      },
      {
        id: 'rating',
        header: 'Rating',
        accessorFn: (l) => l.rating ?? -1,
        sortingFn: 'basic',
        cell: ({ row }) => <Rating value={row.original.rating} count={row.original.reviews_count} />,
      },
      {
        id: 'added',
        header: 'Added',
        accessorFn: (l) => (l.created_at ? new Date(l.created_at).getTime() : 0),
        sortingFn: 'basic',
        cell: ({ row }) => (
          <span className="num text-mute">{formatRelative(row.original.created_at)}</span>
        ),
        meta: { align: 'right' },
      },
    ],
    [],
  )

  const table = useReactTable({
    data: leads,
    columns,
    state: {
      globalFilter,
      ...(sorting !== undefined ? { sorting } : {}),
    },
    onGlobalFilterChange,
    ...(onSortingChange ? { onSortingChange } : {}),
    globalFilterFn,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    ...(enableInternalSort ? { getSortedRowModel: getSortedRowModel() } : {}),
    enableSorting: enableInternalSort,
  })

  const rows = table.getRowModel().rows
  const headerGroups = table.getHeaderGroups()
  const totalCols = columns.length

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          {headerGroups.map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const canSort = h.column.getCanSort()
                const dir = h.column.getIsSorted()
                const align = h.column.columnDef.meta?.align
                return (
                  <th
                    key={h.id}
                    className={align === 'right' ? 'num' : undefined}
                    style={{ width: h.column.columnDef.size }}
                  >
                    {canSort ? (
                      <button
                        type="button"
                        className={`th-sort${dir ? ' is-sorted' : ''}`}
                        onClick={h.column.getToggleSortingHandler()}
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        <span className="th-sort-ico" aria-hidden>
                          <SortIndicator direction={dir} />
                        </span>
                      </button>
                    ) : (
                      flexRender(h.column.columnDef.header, h.getContext())
                    )}
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {loading ? (
            <SkeletonRows rows={6} cols={totalCols} />
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={totalCols}>
                <EmptyState title={emptyTitle} hint={emptyHint} action={emptyAction} />
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={row.id}
                className={clickable ? 'row-link' : undefined}
                onClick={clickable ? () => onRowClick(row.original) : undefined}
                tabIndex={clickable ? 0 : -1}
                onKeyDown={
                  clickable
                    ? (e) => {
                        if (e.key === 'Enter') onRowClick(row.original)
                      }
                    : undefined
                }
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={cell.column.columnDef.meta?.align === 'right' ? 'num' : undefined}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
