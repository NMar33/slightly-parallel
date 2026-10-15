import type { KeyboardEvent, MouseEvent } from 'react'

import { StarButton } from '../../components/StarButton'
import { useMarks, useMarkToggle } from '../../lib/marks'
import {
  ActivityBadge,
  AgentIdentity,
  DaySpark,
  DidChips,
  EditAgentButton,
  HourStrip,
  OpenAgentButton,
  OriginLine,
  Stat,
  TaskRows,
  fmtDay,
} from './parts'
import { fmtMinutes, profileHeadline, type AgentProfile } from './profile'

import { t } from '../../i18n/scope/views'
/**
 * AgentCard — one agent's face: name and origin, the one line that says
 * what it did, when it worked (days) and when in the day (hours), four
 * numbers, what it posted, the tasks it held, and the doors in.
 *
 * Used as-is by the cards roster; the expanding rosters pass `onToggle`
 * (the card becomes a button that opens its dossier) and, in the split
 * layout, `compact` for the narrow column.
 */
export function AgentCard({
  p, code, range, peak, onOpenLens, onOpenTask, onToggle, expanded = false, compact = false,
}: {
  p: AgentProfile
  code: string
  range: [number, number]
  peak: number
  onOpenLens: (lens: string, id: string) => void
  onOpenTask: (id: string) => void
  /** When set, clicking the card (not its buttons) calls this. */
  onToggle?: () => void
  expanded?: boolean
  compact?: boolean
}) {
  const tot = p.totals
  const headline = profileHeadline(p)
  const star = useMarks()
  const toggleStar = useMarkToggle()
  const important = star.has('agent', p.agent.agent_id)
  const starButton = (
    <StarButton on={important} what={t('this agent')} quiet
      onToggle={(next) => toggleStar(next, 'agent', p.agent.agent_id, { project: code, agent_id: p.agent.agent_id })} />
  )
  const lastSession = p.sessions[p.sessions.length - 1]
  const doors: Array<[string, () => void, boolean]> = [
    [t('last scan'), () => p.scans[0] && onOpenLens('scans', p.scans[0].id), p.scans.length > 0],
    [t('last chat'), () => lastSession && onOpenLens('sessions', lastSession.id), !!lastSession],
  ]
  const stop = (e: MouseEvent) => e.stopPropagation()
  const onKey = (e: KeyboardEvent) => {
    if (!onToggle) return
    if (e.target !== e.currentTarget) return
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle() }
  }
  const interactive = !!onToggle
  const frame = `group rounded-card border bg-surface flex flex-col min-w-0 transition-colors ${
    expanded ? 'border-brand shadow-md' : 'border-border-subtle'
  } ${interactive ? 'cursor-pointer hover:border-border-strong focus:outline-none focus-visible:border-brand' : ''}`

  if (compact) {
    return (
      <article
        className={`${frame} p-10 gap-6`}
        aria-label={p.agent.agent_name}
        onClick={onToggle}
        onKeyDown={onKey}
        tabIndex={interactive ? 0 : undefined}
        aria-expanded={interactive ? expanded : undefined}
      >
        <header className="flex items-start gap-6">
          <AgentIdentity p={p} size="sm" linkTo={false} />
          <span className="ml-auto shrink-0 inline-flex items-center gap-2" onClick={stop}>{starButton}<ActivityBadge p={p} /></span>
        </header>
        <p className={`text-12 leading-snug ${headline ? 'text-secondary' : 'text-tertiary italic'}`} style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {headline || t('No messages yet')}
        </p>
        <div className="flex items-center gap-8">
          <DaySpark byDay={p.by_day} range={range} max={peak} width={130} height={16} />
          <span className="ml-auto text-10 font-mono text-tertiary tabular whitespace-nowrap">
            {fmtMinutes(tot.minutes)} · {tot.turns}{t('t')}{tot.tasks_handed_n ? ` · ${tot.tasks_done_n}/${tot.tasks_handed_n}` : ''}
          </span>
        </div>
      </article>
    )
  }

  return (
    <article
      className={`${frame} p-14 gap-10`}
      aria-label={p.agent.agent_name}
      onClick={onToggle}
      onKeyDown={onKey}
      tabIndex={interactive ? 0 : undefined}
      aria-expanded={interactive ? expanded : undefined}
    >
      <header className="flex items-start gap-8">
        <AgentIdentity p={p} size="md" linkTo={!interactive} />
        <div className="ml-auto flex items-center gap-2 shrink-0" onClick={stop}>
          {starButton}
          <ActivityBadge p={p} />
          <OpenAgentButton p={p} />
          <EditAgentButton p={p} code={code} />
        </div>
      </header>

      <p className={`text-13 leading-relaxed ${headline ? 'text-secondary' : 'text-tertiary italic'}`} style={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
        {headline || t('No summary line for this agent yet')}
      </p>

      <div className="flex items-end gap-12">
        <div className="flex flex-col gap-2">
          <span className="text-10 font-mono text-tertiary uppercase tracking-wide">{t('days ·')}{' '}{fmtDay(p.agent.created_date)} → {fmtDay(p.agent.last_active)}</span>
          <DaySpark byDay={p.by_day} range={range} max={peak} width={180} height={26} />
        </div>
        <div className="flex flex-col gap-2 ml-auto">
          <span className="text-10 font-mono text-tertiary uppercase tracking-wide">{t('hours of the day')}</span>
          <HourStrip byHour={p.by_hour} width={120} height={26} />
        </div>
      </div>

      <div className="grid grid-cols-4 gap-8 border-t border-border-subtle pt-10">
        <Stat label={t('agent time')} value={fmtMinutes(tot.minutes)} sub={t('{sessions_n} chats', { sessions_n: tot.sessions_n })} size="sm" />
        <Stat label={t('turns')} value={tot.turns} sub={t('{days_active} days', { days_active: tot.days_active })} size="sm" />
        <Stat label={t('lines')} value={tot.lines_add || tot.lines_del ? `+${tot.lines_add}` : '—'} sub={tot.lines_del ? `−${tot.lines_del} · ${tot.files_n} files` : tot.files_n ? `${tot.files_n} files` : undefined} size="sm" />
        <Stat label={t('tasks')} value={tot.tasks_handed_n ? `${tot.tasks_done_n}/${tot.tasks_handed_n}` : '—'} sub={t('done / handed')} size="sm" />
      </div>

      <div onClick={stop}>
        <DidChips p={p} onOpen={(lens) => {
          const first = lens === 'architecture' ? p.architecture[0] : lens === 'problems' ? p.problems[0] : lens === 'decisions' ? p.decisions[0] : lens === 'scans' ? p.scans[0] : lens === 'rules' ? p.rules[0] : undefined
          if (first) onOpenLens(lens, first.id)
        }} />
      </div>

      {p.tasks.length > 0 && (
        <div className="border-t border-border-subtle pt-8" onClick={stop}>
          <TaskRows tasks={p.tasks} limit={4} onOpen={onOpenTask} dense />
        </div>
      )}

      <footer className="flex items-center gap-6 flex-wrap border-t border-border-subtle pt-8 text-11" onClick={stop}>
        {doors.map(([label, go, ok]) => (
          <button key={label} type="button" onClick={go} disabled={!ok}
            className={`rounded-pill border border-border-subtle px-8 py-2 font-mono ${ok ? 'text-secondary hover:text-primary hover:bg-hover' : 'text-tertiary opacity-50 cursor-default'}`}>
            {label}
          </button>
        ))}
        {interactive && (
          <button type="button" onClick={onToggle} className="rounded-pill border border-brand px-8 py-2 font-mono text-brand hover:bg-brand-glow">
            {expanded ? 'close' : 'open ▸'}
          </button>
        )}
        <span className="ml-auto min-w-0"><OriginLine p={p} /></span>
      </footer>
    </article>
  )
}
