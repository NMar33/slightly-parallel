import type { ReactNode } from 'react'

/**
 * The small filter pill: outlined, mono 11, 20 high; jade outline, text
 * and tint when on. The project picker is a row of these; a filter that
 * toggles on its own (a layer, a kind) is one. An optional dot carries a
 * colour that means something (a project, a group); the pill itself never
 * takes that colour.
 */
export const filterPill = (on: boolean) =>
  `text-11 font-mono px-8 h-20 inline-flex items-center gap-4 rounded-pill border whitespace-nowrap shrink-0 transition-colors ${
    on ? 'border-brand text-brand bg-brand-glow' : 'border-border-subtle text-secondary hover:text-primary'}`

export function FilterPill({
  on, onClick, dot, dotOpacity, count, title, children, className = '',
}: {
  on: boolean
  onClick: () => void
  /** A colour that means something, drawn as a dot before the word. */
  dot?: string
  dotOpacity?: number
  count?: number
  title?: string
  children: ReactNode
  className?: string
}) {
  return (
    <button type="button" aria-pressed={on} title={title} onClick={onClick} className={`${filterPill(on)} ${className}`}>
      {dot && <span className="w-6 h-6 rounded-pill shrink-0" style={{ background: dot, opacity: dotOpacity }} aria-hidden />}
      {children}
      {count != null && <span className="opacity-60 tabular-nums">{count}</span>}
    </button>
  )
}
