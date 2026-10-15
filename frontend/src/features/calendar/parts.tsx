/**
 * The calendar's shared parts — the same chips, windows and pills on every
 * variant, so the variants differ in layout and nothing else.
 *
 * Windows follow the task window's idiom: labelled mono fields, pill
 * radiogroups, one frame. Pills are dense and colour-coded by *why* a thing
 * is on the day (due, planned, done…) or by an entry's kind; the colour
 * carries meaning, the glyph repeats it for the colour-blind.
 */
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { toast } from '../../components/primitives'
import { FilterPill } from '../../components/FilterPill'
import { Segmented } from '../../components/Segmented'
import { FIELD, LABEL } from '../promptlib/taskstyle'
import { lastProject, useCalendarWrites } from './data'
import {
  KIND_COLOR, KIND_GLYPH, LAYERS, LENSES, dayLabel, factLine, parseQuick, relativeDay, shortDate,
  type CalSession, type DayFacts, type Layer, type Lens, type Quick,
} from './model'

import { t } from '../../i18n/scope/views'
// The parts live in their own files by what they are; the pages import
// them all from here.
export { CalendarShell, type CalendarPageProps, type CalendarView } from './shell'
export { MonthPicker } from './MonthPicker'
export { DensityBar, ItemPill, ProjectDot, densityMax, dragTask, droppedEntry, droppedTask } from './pills'
export { EntryWindow, MilestoneWindow } from './windows'

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

export function LayerChips({ on, onToggle, compact = false }: { on: Layer[]; onToggle: (l: Layer) => void; compact?: boolean }) {
  return (
    <div className="flex items-center gap-4 flex-wrap" role="group" aria-label={t('Layers')}>
      {!compact && <span className={LABEL}>{t('show')}</span>}
      {LAYERS.map((l) => {
        const active = on.includes(l.key)
        return (
          <FilterPill key={l.key} on={active} title={l.hint} onClick={() => onToggle(l.key)} dot={l.color} dotOpacity={active ? 1 : 0.35}>
            {l.label}
          </FilterPill>
        )
      })}
    </div>
  )
}

export function LensPills({ value, onChange, counts }: { value: Lens; onChange: (l: Lens) => void; counts?: Partial<Record<Lens, number>> }) {
  return (
    <div className="flex items-center gap-6 flex-wrap">
      <span className={LABEL}>{t('tasks')}</span>
      <Segmented label={t('Tasks')} value={value} onChange={onChange}
        options={LENSES.map((l) => [l.key, counts?.[l.key] !== undefined ? `${l.label} ${counts[l.key]}` : l.label, l.hint] as const)} />
    </div>
  )
}
// ---------------------------------------------------------------------------
// Quick add — one line on a day
// ---------------------------------------------------------------------------

export function QuickAdd({ project, date, onTask, onOpen, autoFocus = false, className = '', projects }: {
  project: string
  /** The projects in view; more than one → a small picker beside the line. */
  projects?: string[]
  /** The day the line is typed on; "tomorrow" counts from here. */
  date: string
  /** The line asked for a task: open the task window with this title and day, under this project. */
  onTask: (title: string, date: string, project: string) => void
  /** Shift+Enter: open the full entry window with the parsed line. */
  onOpen?: (q: Quick) => void
  autoFocus?: boolean
  className?: string
}) {
  const w = useCalendarWrites(project)
  const [text, setText] = useState('')
  const choices = projects && projects.length > 0 ? projects : [project]
  const [proj, setProj] = useState(lastProject(choices, project))
  const parsed = useMemo(() => (text.trim() ? parseQuick(text, date) : null), [text, date])
  const submit = async () => {
    if (!parsed || !parsed.title) return
    if (parsed.kind === 'task') { onTask(parsed.title, parsed.date, proj); setText(''); return }
    try {
      await w.createEntry.mutateAsync({ project: proj, kind: parsed.kind, title: parsed.title, date: parsed.date, time: parsed.time, end_time: parsed.end_time })
      toast.success(t('Added: {kind} · {when}', { kind: t(parsed.kind), when: [shortDate(parsed.date), parsed.time].filter(Boolean).join(' ') }))
      setText('')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("Couldn't add"))
    }
  }
  return (
    <div className={`flex flex-col gap-2 min-w-0 ${className}`}>
      <div className="flex items-center gap-4 min-w-0">
      {choices.length > 1 && (
        <select value={proj} onChange={(e) => setProj(e.target.value)} aria-label={t('project for the line')} title={t('The project the line is written under')} className={`${FIELD} h-24 py-0 w-[110px] shrink-0`}>
          {choices.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      )}
      <input
        value={text}
        autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && e.shiftKey && parsed && onOpen) { e.preventDefault(); onOpen(parsed); setText(''); return }
          if (e.key === 'Enter') { e.preventDefault(); void submit() }
        }}
        aria-label={t('Quick add')}
        placeholder={t('add: call with Anna tomorrow 14:00')}
        title={t('One line becomes an entry. Words it reads: today, tomorrow, fri, next mon, in 3 days, 24.09, 14:00, 14:00-15:30. Start with deadline:, note, remind, event, or /task for a task.')}
        className={`${FIELD} font-sans text-12 w-full min-w-0`}
      />
      </div>
      {parsed && parsed.title && (
        <div className="text-10 font-mono text-tertiary flex items-center gap-6 px-2">
          <span style={{ color: parsed.kind === 'task' ? 'var(--brand)' : KIND_COLOR[parsed.kind] }}>{parsed.kind === 'task' ? '＋ task' : `${KIND_GLYPH[parsed.kind]} ${parsed.kind}`}</span>
          <span>·</span><span>{dayLabel(parsed.date)}</span>
          {parsed.time && <><span>·</span><span>{parsed.time}{parsed.end_time ? `–${parsed.end_time}` : ''}</span></>}
          <span>·</span><span className="truncate text-secondary">{parsed.title}</span>
          <span className="ml-auto shrink-0">{t('Enter adds')}{onOpen ? t(' · Shift+Enter opens') : ''}</span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// The day's work — sessions, with the way to each chat
// ---------------------------------------------------------------------------

export function SessionsOfDay({ sessions, date }: { sessions: CalSession[]; date: string }) {
  const rows = sessions.filter((s) => s.date === date)
  if (rows.length === 0) return <p className="text-11 text-tertiary">{t('No chats that day.')}</p>
  return (
    <ol className="flex flex-col gap-1">
      {rows.map((s) => (
        <li key={s.id}>
          <Link to={`/sessions#sel=${encodeURIComponent(s.id)}`} className="flex items-center gap-8 h-32 px-6 rounded-input hover:bg-hover no-underline min-w-0">
            <span className="text-11 font-mono text-tertiary tabular shrink-0">{s.start}{s.end ? `–${s.end}` : ''}</span>
            <span className="text-12 text-primary truncate">{s.l1 || s.agent_id}</span>
            <span className="ml-auto text-10 font-mono text-tertiary tabular shrink-0">
              {s.turns} {t('turns')}{s.git.commits ? ` · ${s.git.commits} commits · +${s.git.add} −${s.git.del}` : ''}
            </span>
          </Link>
        </li>
      ))}
    </ol>
  )
}

export function FactsLine({ facts, className = '' }: { facts: DayFacts; className?: string }) {
  const line = factLine(facts)
  return <div className={`text-10 font-mono text-tertiary tabular ${className}`}>{line || t('No activity recorded.')}</div>
}

/** "today · Thu 10 Sep" — the day as a heading. */
export function DayHeading({ date, today }: { date: string; today: string }) {
  const rel = relativeDay(date, today)
  return (
    <div className="flex items-baseline gap-8">
      <span className="text-14 font-semibold text-primary">{dayLabel(date)}</span>
      {rel !== shortDate(date) && <span className="text-11 font-mono text-tertiary">{rel}</span>}
    </div>
  )
}
