import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

/**
 * PageHeader — the one way a page introduces itself.
 *
 * Two registers, one component:
 *
 * - **doc** (default): reading pages — Guide, Info, Setup, Settings, Lab.
 *   An icon beside a text-32 title, an italic one-line tagline under it.
 * - **tool**: working pages — Files, Sprints, Kanban, Search. A text-28
 *   title with a mono sub beside it and controls flowing on the same
 *   line; no icon, no tagline — the data below is the introduction.
 * - **lens**: entry pages — Visions, Rules, Problems, Skills, Artifacts,
 *   Chats, Prompts, Architecture. A text-24 name with its icon, the count
 *   of what is on the page beside it, whatever narrows the list after
 *   that, and the find box and buttons pushed right.
 *
 * `below` is the second row, under the title row, for whatever does not
 * fit beside the name: the project picker, a line of totals. The title
 * row of a lens page is one fixed height, so the name sits at the same
 * place on every page whatever the controls beside it are.
 *
 * Entity pages (a project, an agent) keep their own identity headers
 * (color dot + name + chips); everything else uses this.
 */
export function PageHeader({
  icon: Icon,
  title,
  tagline,
  sub,
  count,
  actions,
  children,
  below,
  variant = 'doc',
}: {
  icon?: LucideIcon
  title: ReactNode
  /** Doc pages: the italic sentence under the title. */
  tagline?: ReactNode
  /** Tool pages: the mono annotation beside the title (counts, mode). */
  sub?: ReactNode
  /** Lens pages: how many entries the page holds, beside the name. */
  count?: ReactNode
  /** Right-aligned controls (tool, lens) or trailing elements (doc). */
  actions?: ReactNode
  /** Lens pages: what narrows the list — project pills, chips, a switch.
   *  Tool pages: the controls that flow after the sub. */
  children?: ReactNode
  /** The second row, under the title row (tool and lens). */
  below?: ReactNode
  variant?: 'doc' | 'tool' | 'lens'
}) {
  if (variant === 'lens') {
    const row = (
      <div className="flex items-center gap-12 flex-wrap min-h-row min-w-0">
        <h1
          className="text-24 font-semibold text-primary leading-none tracking-tight inline-flex items-center gap-8"
        >
          {Icon && <Icon size={18} className="text-brand" aria-hidden />}
          {title}
        </h1>
        {count != null && count !== '' && (
          <span className="text-11 font-mono text-tertiary tabular">{count}</span>
        )}
        {children}
        {actions && <div className="ml-auto flex items-center gap-12">{actions}</div>}
      </div>
    )
    return below == null || below === false
      ? <header className="min-w-0">{row}</header>
      : <header className="flex flex-col gap-10 min-w-0">{row}<div className="min-w-0">{below}</div></header>
  }
  if (variant === 'tool') {
    const row = (
      <div className="flex items-baseline gap-10 flex-wrap min-w-0">
        <h1
          className="text-28 font-semibold text-primary leading-none"
          style={{ letterSpacing: '-0.022em' }}
        >
          {title}
        </h1>
        {sub && <span className="text-12 font-mono text-tertiary">{sub}</span>}
        {children}
        {actions && <span className="ml-auto flex items-center gap-8">{actions}</span>}
      </div>
    )
    return below == null || below === false
      ? <header className="min-w-0">{row}</header>
      : <header className="flex flex-col gap-8 min-w-0">{row}<div className="min-w-0">{below}</div></header>
  }
  return (
    <header>
      <div className="flex items-center gap-12 mb-4">
        {Icon && <Icon size={20} className="text-brand" aria-hidden />}
        <h1
          className="text-32 font-semibold text-primary leading-none"
          style={{ letterSpacing: '-0.022em' }}
        >
          {title}
        </h1>
        {actions && <span className="ml-auto flex items-center gap-8">{actions}</span>}
      </div>
      {tagline && <p className="text-14 text-secondary italic">{tagline}</p>}
    </header>
  )
}
