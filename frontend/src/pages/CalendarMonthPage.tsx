import { useCallback, useMemo, useState, type DragEvent } from 'react'
import { ChevronLeft, ChevronRight, Flag, PanelLeft, Plus } from 'lucide-react'

import { Input } from '../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../components/states'
import { useHashState } from '../hooks/useHashState'
import { toast } from '../components/primitives'
import { TaskAddModal } from '../features/project/kanban/TaskWindow'
import type { TaskRow } from '../features/project/kanban/model'
import { LABEL } from '../features/promptlib/taskstyle'
import { lastProject, scopePatch, useCalendar, useCalendarWrites, useScope } from '../features/calendar/data'
import { usePageKeys } from '../features/calendar/keys'
import { openTaskRow } from '../features/calendar/tasks'
import {
  LENSES, applyLens, isDone, isoToday, itemsByDay, monthGrid, monthLabel, monthOf, parseLayers,
  serializeLayers, shiftMonth, sprintSpans, WEEKDAYS,
  type CalEntry, type CalSession, type CalSprint, type CalTask, type DayFacts, type DayItem, type Layer, type Lens, type Milestone, type Quick, firstOfMonth, daysBetween, addDays, lastOfMonth, shortDate, toSpDate,
} from '../features/calendar/model'
import {
  CalendarShell, DayHeading, DensityBar, EntryWindow, FactsLine, ItemPill, LayerChips, LensPills, MilestoneWindow,
  MonthPicker, ProjectDot, QuickAdd, SessionsOfDay, densityMax, droppedEntry, droppedTask, dragTask,
  type CalendarPageProps,
} from '../features/calendar/parts'
import { t, tn } from '../i18n/scope/pages'

/**
 * Calendar v01 — the plan, a month at a time.
 *
 * A Monday-first grid. Every cell is a day: its number, the work under it
 * as four hairline bars, and what is planned on it as dense pills. Sprints
 * run across the weeks as thin strips at the top of the cells. The control
 * row above switches layers, narrows the tasks, and finds; the rail on the
 * left holds the open tasks without a date, to be dragged onto a day. A
 * day opens a panel on the right: one line adds an entry or a task, and
 * the day's chats are one click away.
 */

const SPRINT_COLORS = ['var(--brand)', 'var(--status-purple)', 'var(--status-info)', 'var(--status-amber)']
const MAX_PILLS = 4

export default function CalendarMonthPage({ projectCode, embedded, views, onView }: CalendarPageProps) {
  const [hash, setHash] = useHashState()
  const today = isoToday()
  const scope = useScope(hash, projectCode)
  const project = scope.key
  const month = /^\d{4}-\d{2}$/.test(hash.month ?? '') ? hash.month! : monthOf(today)
  const layers = useMemo(() => parseLayers(hash.layers), [hash.layers])
  const lens = (LENSES.some((l) => l.key === hash.lens) ? hash.lens : 'all') as Lens
  const q = hash.q ?? ''
  const sel = /^\d{4}-\d{2}-\d{2}$/.test(hash.sel ?? '') ? hash.sel! : ''
  const [railOpen, setRailOpen] = useState(true)

  const weeks = useMemo(() => monthGrid(month), [month])
  const first = weeks[0]![0]!
  const last = weeks[weeks.length - 1]![6]!
  const cal = useCalendar(project, first, last)
  const writes = useCalendarWrites(project)
  const data = cal.data
  const codes = data?.projects?.length ? data.projects : scope.codes

  // Windows. The board's lesson applies: state lives up here, not in a cell.
  const [editingTask, setEditingTask] = useState<TaskRow | null>(null)
  const [newTask, setNewTask] = useState<{ date: string; title?: string; project?: string } | null>(null)
  const [entryWin, setEntryWin] = useState<{ date: string; entry?: CalEntry | null; seed?: Quick | null } | null>(null)
  const [msWin, setMsWin] = useState<{ date?: string; milestone?: Milestone | null } | null>(null)
  const [over, setOver] = useState<string | null>(null)

  const tasks = useMemo(() => (data ? applyLens(data.tasks, lens, today, q) : []), [data, lens, today, q])
  const counts = useMemo(() => {
    const out: Partial<Record<Lens, number>> = {}
    if (!data) return out
    for (const l of LENSES) out[l.key] = applyLens(data.tasks, l.key, today, q).length
    return out
  }, [data, today, q])
  const byDay = useMemo(() => (data ? itemsByDay(data, first, last, layers, tasks) : new Map<string, DayItem[]>()), [data, first, last, layers, tasks])
  const max = useMemo(() => (data ? densityMax(data.days) : { sessions: 0, commits: 0, lines: 0, hours: 0 }), [data])
  const spans = useMemo(() => (data && layers.includes('sprints') ? sprintSpans(data.sprints, first, last) : []), [data, layers, first, last])
  const sprintColor = useMemo(() => {
    const m = new Map<string, string>()
    ;(data?.sprints ?? []).forEach((s, i) => m.set(s.id, SPRINT_COLORS[i % SPRINT_COLORS.length]!))
    return m
  }, [data?.sprints])
  const undated = useMemo(
    () => (data ? data.tasks.filter((t) => !isDone(t) && !t.archived && !t.due).sort((a, b) => (a.created < b.created ? 1 : -1)) : []),
    [data],
  )

  const tally = useMemo(() => {
    if (!data) return undefined
    const inMonth = (d: string) => d && monthOf(d) === month
    const due = data.tasks.filter((t) => inMonth(t.due) && !isDone(t)).length
    // A span that started last month and runs into this one counts too.
    const entries = data.entries.filter((e) => e.date <= lastOfMonth(month) && (e.end_date || e.date) >= firstOfMonth(month)).length
    const ms = data.milestones.filter((m) => inMonth(m.target_date)).length
    return `${t('{n} due', { n: due })} · ${tn(entries, '{n} entry', '{n} entries')} · ${tn(ms, '{n} milestone', '{n} milestones')} · ${tn(data.tasks.length, '{n} task', '{n} tasks')}`
  }, [data, month])

  const toggleLayer = (l: Layer) => {
    const next = layers.includes(l) ? layers.filter((x) => x !== l) : [...layers, l]
    setHash({ layers: serializeLayers(next) || (next.length === 0 ? 'none' : '') })
  }
  const go = useCallback((n: number) => setHash({ month: shiftMonth(month, n) }), [month, setHash])
  const goToday = useCallback(() => setHash({ month: monthOf(today), sel: today }), [today, setHash])

  usePageKeys((e) => {
    // Escape in a field leaves the field (the hook); the next one closes the day.
    if (e.key === 'Escape') { if (sel) setHash({ sel: '' }) }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1) }
    else if (e.key === 'ArrowRight') { e.preventDefault(); go(1) }
    else if (e.key === 't') { e.preventDefault(); goToday() }
  })

  const openTask = (t: CalTask) => openTaskRow(t.id, setEditingTask)
  const onDrop = async (e: DragEvent, day: string) => {
    e.preventDefault()
    setOver(null)
    const tid = droppedTask(e)
    const eid = droppedEntry(e)
    try {
      if (tid) {
        await writes.patchTask.mutateAsync({ id: tid, due_date: toSpDate(day) })
        toast.success(t('Due {date}', { date: shortDate(day) }))
      } else if (eid && data) {
        const en = data.entries.find((x) => x.id === eid)
        if (!en || en.source !== 'calendar') return
        // A span keeps its length: both ends move by the same days.
        const shift = daysBetween(en.date, day)
        await writes.updateEntry.mutateAsync({ id: eid, date: day, end_date: en.end_date ? addDays(en.end_date, shift) : '' })
        toast.success(t('Moved to {date}', { date: shortDate(day) }))
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Couldn't move it"))
    }
  }
  const pillHandlers = {
    showProject: scope.multi,
    onTask: (t: CalTask) => void openTask(t),
    onEntry: (en: CalEntry) => setEntryWin({ date: en.date, entry: en }),
    onMilestone: (m: Milestone) => setMsWin({ milestone: m }),
  }

  const find = (
    <Input value={q} onChange={(e) => setHash({ q: e.target.value })} placeholder={t('Find in tasks')} aria-label={t('Find in tasks')} className="w-[200px] h-24 text-12" />
  )
  const nav = (
    <div className="flex items-center gap-8">
      <MonthPicker month={month} label={monthLabel(month)} today={monthOf(today)} onPick={(m) => setHash({ month: m === monthOf(today) ? '' : m, sel: m === monthOf(today) ? today : '' })} className="text-16 font-semibold text-primary tabular whitespace-nowrap min-w-[150px]" />
      <div className="inline-flex items-center rounded-input border border-border-default overflow-hidden">
        <button type="button" onClick={() => go(-1)} aria-label={t('Previous month')} title={t('Previous month (←)')} className="h-24 w-24 inline-flex items-center justify-center text-tertiary hover:text-primary hover:bg-hover"><ChevronLeft size={14} aria-hidden /></button>
        <button type="button" onClick={goToday} title={t('This month, today picked (t)')} className="h-24 px-8 text-11 font-mono text-tertiary hover:text-primary hover:bg-hover border-x border-border-default">{t('today')}</button>
        <button type="button" onClick={() => go(1)} aria-label={t('Next month')} title={t('Next month (→)')} className="h-24 w-24 inline-flex items-center justify-center text-tertiary hover:text-primary hover:bg-hover"><ChevronRight size={14} aria-hidden /></button>
      </div>
    </div>
  )

  return (
    <CalendarShell view="month" scope={{ ...scope, codes }} onScope={(v) => setHash({ ...scopePatch(v), sel: '' })} right={find} tally={tally} embedded={embedded} views={views} onView={onView}>
      <div className="flex items-center gap-12 flex-wrap">
        {nav}
        <LayerChips on={layers} onToggle={toggleLayer} />
      </div>
      <div className="flex items-center gap-12 flex-wrap">
        <LensPills value={lens} onChange={(l) => setHash({ lens: l === 'all' ? '' : l })} counts={counts} />
        <button
          type="button"
          onClick={() => setRailOpen((v) => !v)}
          aria-pressed={railOpen}
          title={t('Show or hide the list of undated open tasks')}
          className={`ml-auto h-24 px-8 inline-flex items-center gap-4 rounded-input border text-11 font-mono ${railOpen ? 'border-border-strong text-primary' : 'border-border-subtle text-tertiary hover:text-primary'}`}
        >
          <PanelLeft size={12} aria-hidden /> {t('undated')} <span className="tabular opacity-70">{undated.length}</span>
        </button>
      </div>

      {cal.isLoading && !data && <LoadingSkeleton variant="card" count={2} />}
      {cal.isError && <ErrorBanner title={t('Could not read the calendar')} hideDismiss />}

      {data && (
        <div className="flex gap-12 min-w-0 items-start">
          {railOpen && !sel && (
            <aside className="w-[180px] shrink-0 flex flex-col gap-4 rounded-card border border-border-subtle bg-surface p-8 max-h-[calc(100vh-220px)] overflow-y-auto" aria-label={t('Undated tasks')}>
              <div className="flex items-baseline gap-6"><span className={LABEL}>{t('undated')}</span><span className="text-10 font-mono text-tertiary tabular">{undated.length}</span></div>
              <p className="text-10 text-tertiary leading-snug">{t('Drag onto a day to give it a due date.')}</p>
              {undated.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  draggable
                  onDragStart={(e) => dragTask(e, t.id)}
                  onClick={() => void openTask(t)}
                  title={`${t.title} · ${t.status}`}
                  className="w-full shrink-0 flex items-center gap-4 text-left text-11 text-primary px-6 h-24 rounded-input hover:bg-hover cursor-grab min-w-0"
                  style={{ boxShadow: 'inset 2px 0 0 var(--status-neutral)' }}
                >
                  {scope.multi && t.project && <ProjectDot code={t.project} />}
                  <span className="truncate">{t.title}</span>
                </button>
              ))}
              {undated.length === 0 && <p className="text-10 font-mono text-tertiary/70">{t('Every open task has a date.')}</p>}
            </aside>
          )}

          <div className="flex-1 min-w-0 flex flex-col">
            <div className="grid" style={{ gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }}>
              {WEEKDAYS.map((w, i) => (
                <div key={w} className={`px-6 pb-4 text-10 uppercase tracking-wider font-mono ${i >= 5 ? 'text-tertiary/70' : 'text-tertiary'}`}>{w}</div>
              ))}
            </div>
            <div className="rounded-card border border-border-subtle overflow-hidden bg-surface">
              {weeks.map((week, wi) => (
                <div key={week[0]} className={`grid ${wi > 0 ? 'border-t border-border-subtle' : ''}`} style={{ gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }}>
                  {week.map((day, di) => (
                    <DayCell
                      key={day}
                      day={day}
                      today={today}
                      inMonth={monthOf(day) === month}
                      weekend={di >= 5}
                      first={di === 0}
                      picked={sel === day}
                      over={over === day}
                      items={byDay.get(day) ?? []}
                      facts={data.days[day]}
                      max={max}
                      showFacts={layers.includes('facts')}
                      sprints={spans.filter((s) => s.from <= day && day <= s.to).map((s) => ({ ...s, color: sprintColor.get(s.sprint.id)! }))}
                      onPick={() => setHash({ sel: sel === day ? '' : day })}
                      onDragOver={(e) => { e.preventDefault(); if (over !== day) setOver(day) }}
                      onDragLeave={() => setOver((cur) => (cur === day ? null : cur))}
                      onDrop={(e) => void onDrop(e, day)}
                      {...pillHandlers}
                    />
                  ))}
                </div>
              ))}
            </div>
            <div className="mt-6 flex items-center gap-12 text-10 font-mono text-tertiary flex-wrap">
              <span>{t('bars under each day: chats · commits · lines · hours')}</span>
              {spans.length > 0 && spans.map((s) => (
                <span key={s.sprint.id} className="inline-flex items-center gap-4"><span aria-hidden className="inline-block w-12 h-3" style={{ backgroundColor: sprintColor.get(s.sprint.id) }} />{s.sprint.name}</span>
              ))}
              <span className="ml-auto">{t('← → month · t today · Esc closes the day')}</span>
            </div>
          </div>

          {sel && (
            <DayPanel
              day={sel}
              today={today}
              project={project}
              items={byDay.get(sel) ?? []}
              facts={data.days[sel]}
              sessions={data.sessions}
              onClose={() => setHash({ sel: '' })}
              onNewTask={(date, title, proj) => setNewTask({ date, title, project: proj })}
              projects={codes}
              onNewEntry={(date, seed) => setEntryWin({ date, seed })}
              onNewMilestone={(date) => setMsWin({ date })}
              {...pillHandlers}
            />
          )}
        </div>
      )}

      {editingTask && (
        <TaskAddModal
          projectCode={editingTask.project || codes[0] || project}
          initialStatus={editingTask.status || 'todo'}
          existingTask={editingTask}
          onClose={() => setEditingTask(null)}
          onSaved={() => { writes.refresh(); setEditingTask(null) }}
        />
      )}
      {newTask && (
        <TaskAddModal
          projectCode={newTask.project || lastProject(codes, project)}
          boardProjects={scope.multi && codes.length > 1 ? codes : undefined}
          initialStatus="todo"
          initialDue={toSpDate(newTask.date)}
          initialTitle={newTask.title}
          onClose={() => setNewTask(null)}
          onSaved={(o) => { writes.refresh(); if (!o?.keepOpen) setNewTask(null) }}
        />
      )}
      {entryWin && data && (
        <EntryWindow project={project} projects={codes} date={entryWin.date} entry={entryWin.entry} seed={entryWin.seed} tasks={data.tasks} milestones={data.milestones} onClose={() => setEntryWin(null)} />
      )}
      {msWin && data && (
        <MilestoneWindow project={project} projects={codes} milestone={msWin.milestone} date={msWin.date} tasks={data.tasks} onClose={() => setMsWin(null)} />
      )}
    </CalendarShell>
  )
}

// ---------------------------------------------------------------------------
// One day of the grid
// ---------------------------------------------------------------------------

type PillHandlers = {
  showProject?: boolean
  onTask: (t: CalTask) => void
  onEntry: (e: CalEntry) => void
  onMilestone: (m: Milestone) => void
}

function DayCell({
  day, today, inMonth, weekend, first, picked, over, items, facts, max, showFacts, sprints,
  onPick, onDragOver, onDragLeave, onDrop, onTask, onEntry, onMilestone, showProject,
}: {
  day: string
  today: string
  inMonth: boolean
  weekend: boolean
  first: boolean
  picked: boolean
  over: boolean
  items: DayItem[]
  facts: DayFacts | undefined
  max: { sessions: number; commits: number; lines: number; hours: number }
  showFacts: boolean
  sprints: Array<{ sprint: CalSprint; from: string; to: string; open: boolean; color: string }>
  onPick: () => void
  onDragOver: (e: DragEvent) => void
  onDragLeave: () => void
  onDrop: (e: DragEvent) => void
} & PillHandlers) {
  const isToday = day === today
  const past = day < today
  const shown = items.slice(0, MAX_PILLS)
  const more = items.length - shown.length
  const num = Number(day.slice(8))
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${day}${items.length ? `, ${tn(items.length, '{n} item', '{n} items')}` : ''}`}
      aria-pressed={picked}
      onClick={onPick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick() } }}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={`relative min-w-0 min-h-[104px] flex flex-col gap-2 p-4 pt-6 cursor-pointer transition-colors ${first ? '' : 'border-l border-border-subtle'} ${
        over ? 'bg-brand-glow' : picked ? 'bg-hover' : weekend ? 'bg-elevated/40 hover:bg-hover' : 'hover:bg-hover'
      } ${inMonth ? '' : 'opacity-50'}`}
    >
      {/* Sprint strips: thin, at the very top, one per sprint that runs through the day. */}
      {sprints.length > 0 && (
        <div className="absolute left-0 right-0 top-0 flex flex-col gap-1" aria-hidden>
          {sprints.map((s) => (
            <span
              key={s.sprint.id}
              title={`${s.sprint.name} · sprint`}
              className="block h-2"
              style={{
                backgroundColor: s.color,
                opacity: 0.7,
                marginLeft: s.sprint.started === day ? 4 : 0,
                marginRight: s.to === day && !s.open ? 4 : 0,
                borderRadius: `${s.sprint.started === day ? 2 : 0}px ${s.to === day && !s.open ? 2 : 0}px ${s.to === day && !s.open ? 2 : 0}px ${s.sprint.started === day ? 2 : 0}px`,
              }}
            />
          ))}
        </div>
      )}
      <div className="flex items-start justify-between gap-4 min-w-0">
        <span
          className={`inline-flex items-center justify-center min-w-[20px] h-20 px-4 rounded-pill text-11 tabular font-mono ${
            isToday ? 'bg-brand text-on-brand font-semibold' : past ? 'text-tertiary' : 'text-secondary'
          }`}
          title={isToday ? t('today') : day}
        >
          {num}
        </span>
        {showFacts && facts && facts.sessions + facts.commits + facts.add + facts.del + facts.hours_min > 0 && <DensityBar facts={facts} max={max} height={14} className="shrink-0 pr-2" />}
      </div>
      <div className="flex flex-col gap-1 min-w-0" onClick={(e) => e.stopPropagation()}>
        {shown.map((it) => (
          <ItemPill key={`${it.kind}:${it.id}`} item={it} dense showProject={showProject} onTask={onTask} onEntry={onEntry} onMilestone={onMilestone} />
        ))}
        {more > 0 && (
          <button type="button" onClick={onPick} className="text-left text-10 font-mono text-tertiary hover:text-primary px-4 h-16" title={t('Open the day')}>
            {t('+{n} more', { n: more })}
          </button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// The picked day
// ---------------------------------------------------------------------------

function DayPanel({
  day, today, project, projects, items, facts, sessions, onClose, onNewTask, onNewEntry, onNewMilestone, onTask, onEntry, onMilestone, showProject,
}: {
  day: string
  today: string
  project: string
  projects: string[]
  items: DayItem[]
  facts: DayFacts | undefined
  sessions: CalSession[]
  onClose: () => void
  onNewTask: (date: string, title?: string, project?: string) => void
  onNewEntry: (date: string, seed?: Quick | null) => void
  onNewMilestone: (date: string) => void
} & PillHandlers) {
  return (
    <aside className="w-[320px] shrink-0 flex flex-col gap-10 rounded-card border border-brand/40 bg-surface p-12 max-h-[calc(100vh-220px)] overflow-y-auto" aria-label={t('Day {date}', { date: day })}>
      <div className="flex items-start gap-8">
        <DayHeading date={day} today={today} />
        <button type="button" onClick={onClose} aria-label={t('Close the day')} title={t('Close (Esc)')} className="ml-auto text-10 font-mono text-tertiary hover:text-primary">× {t('close')}</button>
      </div>
      {/* Keyed by the scope: a new board means a new default project for the line. */}
      <QuickAdd key={project} project={project} projects={projects} date={day} onTask={(title, date, proj) => onNewTask(date, title, proj)} onOpen={(qk) => onNewEntry(day, qk)} autoFocus />
      <div className="flex items-center gap-6 flex-wrap text-11 font-mono">
        <button type="button" onClick={() => onNewTask(day)} className="h-20 px-8 rounded-pill border border-border-default text-tertiary hover:text-primary hover:border-border-strong inline-flex items-center gap-4" title={t('A task due this day')}><Plus size={11} aria-hidden /> {t('task')}</button>
        <button type="button" onClick={() => onNewEntry(day)} className="h-20 px-8 rounded-pill border border-border-default text-tertiary hover:text-primary hover:border-border-strong inline-flex items-center gap-4" title={t('A meeting, deadline, reminder or note on this day')}><Plus size={11} aria-hidden /> {t('entry')}</button>
        <button type="button" onClick={() => onNewMilestone(day)} className="h-20 px-8 rounded-pill border border-border-default text-tertiary hover:text-primary hover:border-border-strong inline-flex items-center gap-4" title={t('A milestone with this target day')}><Flag size={11} aria-hidden /> {t('milestone')}</button>
      </div>
      <div className="flex flex-col gap-2">
        <span className={LABEL}>{t('on this day')} <span className="normal-case tracking-normal tabular">{items.length}</span></span>
        {items.length === 0 && <p className="text-11 text-tertiary">{t('Nothing planned.')}</p>}
        {items.map((it) => (
          <ItemPill key={`${it.kind}:${it.id}`} item={it} showWhy showProject={showProject} onTask={onTask} onEntry={onEntry} onMilestone={onMilestone} />
        ))}
      </div>
      <div className="flex flex-col gap-4 border-t border-border-subtle pt-8">
        <span className={LABEL}>{t('the work')}</span>
        {facts ? <FactsLine facts={facts} /> : <p className="text-10 font-mono text-tertiary">{t('quiet')}</p>}
        <SessionsOfDay sessions={sessions} date={day} />
      </div>
    </aside>
  )
}
