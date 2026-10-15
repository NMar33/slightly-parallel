import type { ReactNode } from 'react'

import { LABEL } from './ui'

/**
 * The one number tile, as the Timer tab draws it: a flat elevated tile, the
 * label above in mono capitals, the value, and one quiet line under it.
 * No border, no shadow. Put several in a grid:
 * `grid gap-10` with `repeat(auto-fit, minmax(160px, 1fr))` columns.
 */
export function StatTile({
  label, value, sub, children, hot = false, valueClassName, wrapSub = false, title, className = '',
}: {
  label: ReactNode
  value: ReactNode
  /** The line under the value. */
  sub?: ReactNode
  /** Drawn between the value and the line under it (a sparkline). */
  children?: ReactNode
  /** The value is past a limit: drawn in amber. */
  hot?: boolean
  /** The value's colour when the page has its own (a red for errors). */
  valueClassName?: string
  /** Let the line under the value wrap instead of cutting it. */
  wrapSub?: boolean
  title?: string
  className?: string
}) {
  return (
    <div className={`rounded-input bg-elevated px-12 py-10 min-w-0 flex flex-col ${className}`} title={title}>
      <div className={`${LABEL} truncate`}>{label}</div>
      <div className={`text-20 font-semibold tabular leading-tight truncate ${valueClassName ?? (hot ? 'text-status-amber' : 'text-primary')}`}>{value}</div>
      {children}
      {sub != null && sub !== '' && (
        <div className={`text-10 font-mono text-tertiary ${wrapSub ? 'leading-snug' : 'truncate'}`}>{sub}</div>
      )}
    </div>
  )
}

/** The grid the tiles sit in. */
export function StatTiles({ children, min = 160, className = '' }: { children: ReactNode; min?: number; className?: string }) {
  return (
    <div className={`grid gap-10 ${className}`} style={{ gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))` }}>
      {children}
    </div>
  )
}
