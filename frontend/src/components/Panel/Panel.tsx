import type { ReactNode } from 'react'

/**
 * Panel — the standard Command-Center dashboard container.
 *
 *   ┌───────────────────────────────────────────┐
 *   │ ▮ TITLE · L2                     [tabs]  │  ← header (uppercase mono)
 *   ├───────────────────────────────────────────┤
 *   │  body                                     │
 *   └───────────────────────────────────────────┘
 *
 * The marker slice on the left of the title is a jade token — never a raw hex.
 * Header uses uppercase mono type with letter-spacing 0.06em to hit the
 * terminal aesthetic of variant-2 (see draft/variants/layout/variant-2.html).
 *
 * `tabs` slot is a right-aligned inline element (a Segmented, chips, or plain text).
 */

interface PanelProps {
  title: ReactNode
  tabs?: ReactNode
  /** Removes internal body padding — useful when body renders its own list rows. */
  bodyPadding?: 'md' | 'tight' | 'none'
  className?: string
  bodyClassName?: string
  children: ReactNode
  /** Optional aria-label if the title is decorative or split across nodes. */
  'aria-label'?: string
}

const bodyPadMap = {
  md: 'p-16',
  tight: 'px-16 py-4',
  none: '',
} as const

export function Panel({
  title,
  tabs,
  bodyPadding = 'md',
  className = '',
  bodyClassName = '',
  children,
  'aria-label': ariaLabel,
}: PanelProps) {
  return (
    <section
      aria-label={typeof title === 'string' ? title : ariaLabel}
      className={`rounded-card border border-border-default bg-surface overflow-hidden flex flex-col ${className}`.trim()}
    >
      <header className="flex items-center justify-between gap-8 px-16 py-12 border-b border-border-subtle">
        <div className="flex items-center gap-8 min-w-0">
          <span
            aria-hidden
            className="inline-block w-4 h-16 rounded-input shrink-0"
            style={{ background: 'var(--brand)' }}
          />
          <h2
            className="text-12 font-semibold text-primary uppercase font-mono truncate"
            style={{ letterSpacing: '0.06em' }}
          >
            {title}
          </h2>
        </div>
        {tabs && (
          <div className="flex items-center gap-4 shrink-0 text-11 text-tertiary font-mono">
            {tabs}
          </div>
        )}
      </header>
      <div className={`${bodyPadMap[bodyPadding]} ${bodyClassName}`.trim()}>{children}</div>
    </section>
  )
}
