import { useAgentNames } from '../../../lib/useAgentNames'
import type { ReactNode } from 'react'

import { Button } from '../../../components/primitives'
import { formatStamp } from '../../../utils/dateUtils'
import { coreColor, weeksOf, type CoreNote, type GridDay, type Tracking } from './data'
import { t, tn } from '../../../i18n/scope/system'

/** The small square of a type's colour, before a name. */
export function TypeDot({ type, size = 10 }: { type: string; size?: number }) {
  return <i aria-hidden="true" className="inline-block shrink-0 rounded-[2px]" style={{ width: size, height: size, background: coreColor(type) }} />
}

/** The type, in its colour, as a mono label. */
export function TypeWord({ type }: { type: string }) {
  return <span className="text-10 font-mono uppercase tracking-wider" style={{ color: coreColor(type) }}>{typeWord(type)}</span>
}

export function typeWord(type: string): string {
  switch (type) {
    case 'capability': return t('capability')
    case 'feature': return t('feature')
    case 'interface': return t('interface')
    case 'store': return t('store')
    case 'integration': return t('integration')
    case 'internals': return t('internals')
    case 'workflow': return t('workflow')
    case 'experiment': return t('experiment')
    default: return type
  }
}

/** What the type is for, one line each: the tooltip on the picker. */
export function typeHint(type: string): string {
  switch (type) {
    case 'capability': return t('Something the program can do: chat capture.')
    case 'feature': return t('A feature, often for the next release: the ### suppressor.')
    case 'interface': return t('A part of the interface: the kanban, the task window.')
    case 'store': return t('Where data is stored: the CSV files, the DuckDB views.')
    case 'integration': return t('A connection to another tool: the Cursor hooks, the Codex adapter.')
    case 'internals': return t('Internal parts: the #now flow, the tag readers.')
    case 'workflow': return t('Work that runs through several parts: scan → architecture page, audit rounds.')
    case 'experiment': return t('An approach being tried; not promised.')
    default: return ''
  }
}

/**
 * The last 30 days as five weeks of squares, Monday on top, like a
 * contribution calendar. A square's colour is the core's type; its
 * strength the day's story (notes, the linked tasks' events). A day with
 * only commits on an anchor ("touched nearby") is a pale ring: nearby is
 * not the story. An empty square is a quiet day, not a warning.
 */
export function ActivityGrid({ grid, type, cell = 10, gap = 3, label }: {
  grid: GridDay[]; type: string; cell?: number; gap?: number; label?: string
}) {
  const weeks = weeksOf(grid)
  const color = coreColor(type)
  return (
    <div role="img" aria-label={label ?? t('Activity, the last 30 days')} className="flex" style={{ gap }}>
      {weeks.map((week, wi) => (
        <div key={wi} className="flex flex-col" style={{ gap }}>
          {week.map((d, di) => {
            if (!d) return <span key={di} style={{ width: cell, height: cell }} />
            const strength = d.story >= 3 ? 1 : d.story === 2 ? 0.7 : d.story === 1 ? 0.42 : 0
            const title = `${d.day} · ${tn(d.story, '{n} note or task event', '{n} notes and task events')}${d.nearby ? ` · ${tn(d.nearby, '{n} commit in its files', '{n} commits in its files')}` : ''}`
            return (
              <span key={d.day} title={title} className="rounded-[2px] bg-elevated"
                style={{
                  width: cell, height: cell,
                  background: strength ? color : undefined,
                  opacity: strength || 1,
                  boxShadow: !strength && d.nearby ? `inset 0 0 0 1.5px ${color}` : undefined,
                }} />
            )
          })}
        </div>
      ))}
    </div>
  )
}

/** The tracking state in two words: on with its days left, or nothing. */
export function TrackingWord({ tracking }: { tracking: Tracking }) {
  if (!tracking.on) return null
  const left = tracking.days_left == null ? t('no expiry') : tn(tracking.days_left, '{n} day left', '{n} days left')
  return <span className="text-10 font-mono text-brand">{t('tracking')} · {left}</span>
}

/** Who wrote a note and when; an agent's gets its name and its approval state. */
export function NoteMeta({ note, onApprove, busy }: { note: CoreNote; onApprove?: (id: string) => void; busy?: boolean }) {
  const operator = note.author === 'operator' || !note.author
  return (
    <span className="flex items-center gap-8 text-10 font-mono text-tertiary flex-wrap">
      <span>{formatStamp(note.at)}</span>
      <span>·</span>
      {operator ? <span>{t('operator')}</span> : <span>{t('agent')} <AgentName id={note.author} /></span>}
      {note.kind === 'auto' && <span>· {t('on finished work')}</span>}
      {note.kind === 'founding' && <span>· {t('first note')}</span>}
      {note.task_id && <span>· {note.task_id}</span>}
      {!operator && (note.approved
        ? <span className="text-brand">· ✓ {t('approved')}</span>
        : onApprove
          ? <Button variant="text" size="bare" disabled={busy} onClick={() => onApprove(note.id)} className="text-brand">· {t('approve')}</Button>
          : <span>· {t('awaiting approval')}</span>)}
    </span>
  )
}

/** A note's body: the operator's text on paper, the agent's comment tinted. */
export function NoteBody({ note }: { note: CoreNote }) {
  const operator = note.author === 'operator' || !note.author
  return (
    <div className="flex flex-col gap-4 min-w-0">
      {note.text && (
        <p className={`text-13 text-primary whitespace-pre-wrap break-words m-0 ${operator ? '' : 'rounded-input bg-elevated px-8 py-6'}`}>{note.text}</p>
      )}
      {note.comment && (
        <p className="text-12 text-secondary whitespace-pre-wrap break-words m-0 rounded-input px-8 py-6"
          style={{ background: 'var(--brand-glow)' }}>{note.comment}</p>
      )}
    </div>
  )
}

/** A small mono heading over a block of the page. */
export function BlockLabel({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-10">
      <span className="text-10 font-mono uppercase tracking-wider text-tertiary">{children}</span>
      {aside && <span className="text-10 font-mono text-tertiary">{aside}</span>}
    </div>
  )
}

/**
 * An agent's name for the cores pages. A chat's title is its name until the
 * operator renames it; a title that is a pasted log or a long message
 * ("CI / Backend (macos-latest, Python 3.12) (push) Failing after 2m …")
 * says nothing about the agent, so the id stands and the title stays in the
 * tooltip.
 */
export function AgentName({ id, className }: { id: string | null | undefined; className?: string }) {
  const nameOf = useAgentNames()
  const agentId = String(id ?? '')
  if (!agentId) return null
  const name = nameOf(agentId)
  const pasted = name.length > 40 || name.split(/\s+/).length > 6
  return <span className={className} title={name === agentId ? agentId : `${name} · ${agentId}`}>{pasted ? agentId : name}</span>
}
