import { type ReactNode } from 'react'
import { Card } from '../primitives/Card'
import { Button } from '../primitives/Button'

/**
 * EmptyState — the "nothing here yet" surface. Non-negotiable per aesthetic
 * critic §7 & architecture §3 P0 item 9.
 *
 * Guarantees:
 *   • Title + subtitle always present (no "No data" ever)
 *   • Optional icon (lucide-react node) at top
 *   • Optional CTA button — either an href (link) or an onClick (action)
 *   • Composes on Card so borders/spacing match the surrounding grid
 *
 *   <EmptyState
 *     icon={<Inbox size={24} />}
 *     title="No projects yet"
 *     subtitle="Start an agent to populate…"
 *     cta={{ label: 'Docs', href: '/docs' }}
 *   />
 */

interface EmptyStateProps {
  title: string
  /** Plain string or rich node (e.g. with inline `<code>` styling). */
  subtitle?: ReactNode
  icon?: ReactNode
  cta?: {
    label: string
    href?: string
    onClick?: () => void
  }
  /** Render without the wrapping Card (use inside an existing Card). */
  bare?: boolean
  /** One quiet line inside a card or a list: the title, then the subtitle. */
  compact?: boolean
  className?: string
}

export function EmptyState({ title, subtitle, icon, cta, bare = false, compact = false, className = '' }: EmptyStateProps) {
  if (compact) {
    return (
      <p role="status" className={`text-11 text-tertiary m-0 ${className}`.trim()}>
        {title}{subtitle != null && subtitle !== '' && <> <span className="text-tertiary">{subtitle}</span></>}
      </p>
    )
  }
  const body = (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-col items-center justify-center text-center gap-8 py-32 px-16 ${className}`.trim()}
    >
      {icon && (
        <div aria-hidden="true" className="text-tertiary mb-4 flex items-center justify-center">
          {icon}
        </div>
      )}
      <h3 className="text-14 font-semibold text-primary m-0">{title}</h3>
      {subtitle != null && <p className="text-13 text-secondary max-w-[52ch] m-0 leading-normal">{subtitle}</p>}
      {cta && (
        <div className="mt-8">
          {cta.href ? (
            <a
              href={cta.href}
              className="inline-flex items-center h-32 px-12 rounded-input text-13 font-medium bg-surface text-primary border border-border-default hover:bg-hover transition-colors duration-fast ease-out"
            >
              {cta.label}
            </a>
          ) : (
            <Button variant="secondary" size="md" onClick={cta.onClick}>
              {cta.label}
            </Button>
          )}
        </div>
      )}
    </div>
  )

  if (bare) return body
  return <Card padding="none">{body}</Card>
}
