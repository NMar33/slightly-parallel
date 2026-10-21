import type { ReactNode } from 'react'

import { ActivityBadge, AgentIdentity, OriginLine } from './parts'
import { fmtLines, fmtMinutes, profileHeadline, type AgentProfile } from './profile'

/**
 * One agent's header — identity, the headline, the numbers, the folder.
 * The same on the stage (a project's #agents) and on the agent's own page,
 * so a link lands on the reading the operator already knows; each place
 * brings its own walk (`nav`) and its own buttons (`actions`).
 */
export function AgentHeader({ p, nav, actions }: { p: AgentProfile; nav?: ReactNode; actions?: ReactNode }) {
  const tot = p.totals
  const headline = profileHeadline(p)
  const chips: Array<[string, string]> = [
    ['time', `${fmtMinutes(tot.minutes)} · ${tot.sessions_n} ses · ${tot.days_active} d`],
    ['turns', String(tot.turns)],
    ['lines', fmtLines(tot.lines_add, tot.lines_del)],
    ['files', tot.files_n ? `${tot.files_n} · ${tot.scans_n} scans` : '—'],
    ['tasks', tot.tasks_handed_n ? `${tot.tasks_done_n} / ${tot.tasks_handed_n}` : '—'],
    ['features · fixes', `${tot.features_n} · ${tot.bugs_resolved_n}`],
    ['decisions', String(tot.decisions_n)],
  ]
  return (
    <header className="flex flex-col gap-8 min-w-0 border-b border-border-subtle pb-12">
      <div className="flex items-start gap-10 min-w-0">
        <AgentIdentity p={p} size="lg" linkTo={false} />
        <span className="mt-4"><ActivityBadge p={p} /></span>
        <div className="ml-auto flex items-center gap-4 shrink-0">
          {nav}
          {actions}
        </div>
      </div>
      {headline && <p className="text-13 text-secondary leading-relaxed max-w-[1000px]" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{headline}</p>}
      <div className="flex items-center gap-8 flex-wrap">
        {chips.map(([label, value]) => (
          <span key={label} className="inline-flex items-baseline gap-6 rounded-pill border border-border-subtle bg-base/40 px-10 py-3">
            <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{label}</span>
            <span className="text-12 font-semibold text-primary tabular">{value}</span>
          </span>
        ))}
        <span className="ml-auto min-w-0 max-w-[520px]"><OriginLine p={p} /></span>
      </div>
    </header>
  )
}
