import { useCallback, useMemo, useState, type DragEvent } from 'react'
import { ChevronLeft, ChevronRight, Flag, Plus } from 'lucide-react'

import { toast } from '../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../components/states'
import { useHashState } from '../hooks/useHashState'
import { TaskAddModal } from '../features/project/kanban/TaskWindow'
import type { TaskRow } from '../features/project/kanban/model'
import { FIELD, LABEL } from '../features/promptlib/taskstyle'
import { lastProject, scopePatch, useCalendar, useCalendarWrites, useScope } from '../features/calendar/data'
import { usePageKeys } from '../features/calendar/keys'
import { openTaskRow } from '../features/calendar/tasks'
import {
  EMPTY_FACTS, LENSES, addDays, applyLens, dateOf, daysBetween, eachDay, isoToday, itemsByDay, parseLayers, relativeDay,
  serializeLayers, shortDate, sprintSpans, startOfWeek, toSpDate, WEEKDAYS,
  type CalEntry, type CalTask, type DayItem, type Layer, type Lens, type Milestone, type Quick,
  monthOf,
} from '../features/calendar/model'
import {
  CalendarShell, DayHeading, DensityBar, EntryWindow, FactsLine, ItemPill, LayerChips, LensPills, MilestoneWindow, MonthPicker,
  QuickAdd, SessionsOfDay, densityMax, dragTask, droppedEntry, droppedTask,
  type CalendarPageProps,
} from '../features/calendar/parts'
import { factRows, orderDayItems, pickInWeek, stripRange, weekTally } from '../features/calendar/week/model'
import { t } from '../i18n/scope/pages'

/**
 * Calendar v02 — the week workbench.
 *
 * The chats workbench, for time. Three bands: a strip of eight weeks
 * across the top (the density of every day — the project's rhythm at a
 * glance, click a day to go there), the week itself as seven columns (the
 * plan of each day, a quick-add at its foot, a drop target for undated
 * work), and a pane for the picked day (its items with the reason each is
 * there, its chats with the way to each one, its numbers, and the rail
 * of undated tasks to drag from). One payload feeds all three.
 */

const ISO = /^\d{4}-\d{2}-\d{2}$/

type Open =
  | { kind: 'task'; row: TaskRow | null; due?: string; title?: string; project?: string }
  | { kind: 'entry'; entry: CalEntry | null; date: string; seed?: Quick | null }
  | { kind: 'milestone'; milestone: Milestone | null; date: string }

export default function CalendarWeekPage({ projectCode, embedded, views, onView }: CalendarPageProps) {
  const [hash, setHash] = useHashState()
  const today = isoToday()
  const scope = useScope(hash, projectCode)
  const project = scope.key
  const week = ISO.test(hash.week ?? '') ? startOfWeek(hash.week!) : startOfWeek(today)
  const layers = useMemo(() => parseLayers(hash.layers), [hash.layers])
  const lens: Lens = LENSES.some((l) => l.key === hash.lens) ? (hash.lens as Lens) : 'all'
  const q = hash.q ?? ''
  const sel = ISO.test(hash.sel ?? '') ? hash.sel! : today

  const strip = useMemo(() => stripRange(week), [week])
  const query = useCalendar(project, strip.from, strip.to)
  const p = query.data
  const codes = p?.projects?.length ? p.projects : scope.codes
  const writes = useCalendarWrites(project)

  const [open, setOpen] = useState<Open | null>(null)
  const [undatedQ, setUndatedQ] = useState('')

  const shownTasks = useMemo(() => (p ? applyLens(p.tasks, lens, today, q) : []), [p, lens, today, q])
  const counts = useMemo(() => {
    const out: Partial<Record<Lens, number>> = {}
    if (p) for (const l of LENSES) out[l.key] = applyLens(p.tasks, l.key, today, q).length
    return out
  }, [p, today, q])
  const weekDays = useMemo(() => eachDay(week, addDays(week, 6)), [week])
  const byDay = useMemo(() => {
    if (!p) return new Map<string, DayItem[]>()
    const m = itemsByDay(p, strip.from, strip.to, layers, shownTasks)
    for (const [k, v] of m) m.set(k, orderDayItems(v))
    return m
  }, [p, strip.from, strip.to, layers, shownTasks])
  const spans = useMemo(() => (p && layers.includes('sprints') ? sprintSpans(p.sprints, strip.from, strip.to) : []), [p, layers, strip.from, strip.to])
  const max = useMemo(() => densityMax(p?.days ?? {}), [p])
  const undated = useMemo(() => {
    if (!p) return []
    const needle = undatedQ.trim().toLowerCase()
    return applyLens(p.tasks, 'undated', today).filter((t) => !needle || t.title.toLowerCase().includes(needle))
  }, [p, today, undatedQ])

  const goWeek = useCallback((monday: string) => setHash({ week: monday, sel: pickInWeek(sel, monday) }), [setHash, sel])
  const pick = useCallback((d: string) => setHash({ sel: d, week: startOfWeek(d) }), [setHash])
  const toggleLayer = (l: Layer) => {
    const next = layers.includes(l) ? layers.filter((x) => x !== l) : [...layers, l]
    setHash({ layers: next.length === 0 ? 'none' : serializeLayers(next) })
  }

  usePageKeys((e) => {
    if (open) return
    // Escape in a field leaves the field (the hook); the next one clears the pick.
    if (e.key === 'Escape') setHash({ sel: '' })
    else if (e.key === 'ArrowLeft') { e.preventDefault(); goWeek(addDays(week, -7)) }
    else if (e.key === 'ArrowRight') { e.preventDefault(); goWeek(addDays(week, 7)) }
    else if (e.key === 't') { e.preventDefault(); setHash({ week: startOfWeek(today), sel: today }) }
  })

  const openTask = (id: string) => openTaskRow(id, (row) => setOpen({ kind: 'task', row }))
  const onDrop = async (e: DragEvent, date: string) => {
    e.preventDefault()
    const tid = droppedTask(e)
    const eid = droppedEntry(e)
    try {
      if (tid) {
        await writes.patchTask.mutateAsync({ id: tid, due_date: date })
        toast.success(t('Due {date}', { date: shortDate(date) }))
      } else if (eid && p) {
        const en = p.entries.find((x) => x.id === eid)
        if (!en || en.source !== 'calendar') return
        const shift = daysBetween(en.date, date)
        await writes.updateEntry.mutateAsync({ id: eid, date, end_date: en.end_date ? addDays(en.end_date, shift) : '' })
        toast.success(t('Moved to {date}', { date: shortDate(date) }))
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("Couldn't move it"))
    }
  }
  const pillHandlers = {
    showProject: scope.multi,
    onTask: (t: CalTask) => void openTask(t.id),
    onEntry: (en: CalEntry) => setOpen({ kind: 'entry', entry: en, date: en.date }),
    onMilestone: (m: Milestone) => setOpen({ kind: 'milestone', milestone: m, date: m.target_date || sel }),
  }
  const newTask = (title: string, date: string, proj?: string) => {
    setOpen({ kind: 'task', row: null, due: date, title, project: proj })
  }

  const weekLabel = `${shortDate(week)} – ${shortDate(addDays(week, 6))}`
  const selFacts = p?.days[sel] ?? EMPTY_FACTS
  const selItems = byDay.get(sel) ?? []

  return (
    <CalendarShell
      view="week"
      scope={{ ...scope, codes }}
      onScope={(v) => setHash(scopePatch(v))}
      embedded={embedded}
      views={views}
      onView={onView}
      tally={weekTally(p, week, today)}
      right={(
        <>
          <input value={q} onChange={(e) => setHash({ q: e.target.value })} placeholder={t('Find in tasks')} aria-label={t('Find in tasks')} className={`${FIELD} h-24 py-0 w-[180px]`} />
          <div className="inline-flex items-center rounded-input border border-border-default overflow-hidden">
            <button type="button" onClick={() => goWeek(addDays(week, -7))} aria-label={t('Previous week')} title={t('Previous week (←)')} className="h-24 w-24 inline-flex items-center justify-center text-tertiary hover:text-primary hover:bg-hover"><ChevronLeft size={14} aria-hidden /></button>
            <button type="button" onClick={() => setHash({ week: startOfWeek(today), sel: today })} title={t('This week (t)')} className="h-24 px-8 text-11 font-mono text-secondary hover:text-primary hover:bg-hover border-x border-border-default">{t('this week')}</button>
            <button type="button" onClick={() => goWeek(addDays(week, 7))} aria-label={t('Next week')} title={t('Next week (→)')} className="h-24 w-24 inline-flex items-center justify-center text-tertiary hover:text-primary hover:bg-hover"><ChevronRight size={14} aria-hidden /></button>
          </div>
          <MonthPicker month={monthOf(week)} label={weekLabel} today={monthOf(today)} onPick={(m) => goWeek(m === monthOf(today) ? startOfWeek(today) : startOfWeek(`${m}-01`))} className="text-12 font-medium text-primary tabular whitespace-nowrap" />
        </>
      )}
    >
      <div className={`flex flex-col gap-8 min-h-0 min-w-0 ${embedded ? 'h-[calc(100vh-330px)]' : 'h-[calc(100vh-150px)]'}`}>
        <div className="flex items-center gap-12 flex-wrap">
          <LayerChips on={layers} onToggle={toggleLayer} />
          <LensPills value={lens} onChange={(l) => setHash({ lens: l === 'all' ? '' : l })} counts={counts} />
        </div>

        {query.isError && <ErrorBanner title={t('Could not read the calendar')} hideDismiss />}
        {!p && query.isLoading && <LoadingSkeleton variant="row" count={4} />}

        {p && (
          <>
            {/* Band 1 — eight weeks of density */}
            <div className="grid gap-4 shrink-0" style={{ gridTemplateColumns: `repeat(${strip.weeks.length}, minmax(0, 1fr))` }} role="group" aria-label={t('Eight weeks')}>
              {strip.weeks.map((monday) => {
                const current = monday === week
                return (
                  <div key={monday} className={`grid gap-1 rounded-input px-2 py-2 border ${current ? 'border-brand bg-brand-glow' : 'border-transparent'}`} style={{ gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }} title={`week of ${shortDate(monday)}`}>
                    {eachDay(monday, addDays(monday, 6)).map((d) => {
                      const f = p.days[d] ?? EMPTY_FACTS
                      const isToday = d === today
                      const picked = d === sel
                      return (
                        <button
                          key={d}
                          type="button"
                          onClick={() => pick(d)}
                          title={`${relativeDay(d, today)} · ${shortDate(d)}`}
                          aria-label={shortDate(d)}
                          aria-pressed={picked}
                          className={`flex flex-col items-center gap-1 rounded-input px-1 pt-2 pb-1 hover:bg-hover ${picked ? 'bg-hover' : ''}`}
                        >
                          <DensityBar facts={f} max={max} height={22} />
                          <span className={`text-10 font-mono tabular leading-none ${isToday ? 'text-brand font-semibold' : d > today ? 'text-tertiary opacity-60' : 'text-tertiary'}`}>{dateOf(d).getDate()}</span>
                        </button>
                      )
                    })}
                  </div>
                )
              })}
            </div>

            {/* Bands 2 + 3 — the week and the pane */}
            <div className="grid gap-12 min-h-0 min-w-0 flex-1" style={{ gridTemplateColumns: 'minmax(0, 1fr) 320px' }}>
              <div className="grid gap-4 min-h-0 min-w-0" style={{ gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }}>
                {weekDays.map((d, i) => {
                  const items = byDay.get(d) ?? []
                  const f = p.days[d] ?? EMPTY_FACTS
                  const isToday = d === today
                  const picked = d === sel
                  const band = spans.filter((s) => s.from <= d && d <= s.to)
                  const rel = relativeDay(d, today)
                  return (
                    <section
                      key={d}
                      aria-label={shortDate(d)}
                      onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
                      onDrop={(e) => void onDrop(e, d)}
                      className={`flex flex-col min-h-0 min-w-0 rounded-card border bg-surface ${picked ? 'border-brand' : isToday ? 'border-border-strong' : 'border-border-subtle'} `}
                      style={i >= 5 ? { backgroundColor: 'color-mix(in srgb, var(--bg-elevated) 45%, var(--bg-surface))' } : undefined}
                    >
                      <button type="button" onClick={() => pick(d)} className="flex flex-col gap-1 px-8 pt-6 pb-4 text-left hover:bg-hover rounded-t-card" title={`${rel} · pick ${shortDate(d)}`}>
                        <div className="flex items-baseline gap-6 min-w-0 w-full whitespace-nowrap">
                          <span className={`text-12 font-semibold shrink-0 ${isToday ? 'text-brand' : 'text-primary'}`}>{WEEKDAYS[i]} {dateOf(d).getDate()}</span>
                          {rel === 'today' && <span className="text-10 font-mono text-brand">{rel}</span>}
                          <span className="ml-auto text-10 font-mono text-tertiary tabular shrink-0">{items.length || ''}</span>
                        </div>
                        {layers.includes('facts') && <FactsLine facts={f} className="truncate" />}
                      </button>
                      {band.length > 0 && (
                        <div className="flex flex-col gap-1 px-4">
                          {band.map((s) => (
                            <div key={s.sprint.id} className="h-4 rounded-pill" style={{ backgroundColor: 'var(--brand)', opacity: s.open ? 0.7 : 0.4 }} title={`sprint · ${s.sprint.name} · ${s.sprint.status}`} />
                          ))}
                        </div>
                      )}
                      <ol className="flex-1 min-h-0 overflow-y-auto px-4 py-4 flex flex-col gap-1" aria-label={`${shortDate(d)} items`}>
                        {items.map((it) => (
                          <li key={`${it.kind}:${it.id}`}><ItemPill item={it} dense {...pillHandlers} /></li>
                        ))}
                        <li className="pt-2">
                          <ColumnAdd key={project} project={project} projects={codes} date={d} onTask={newTask} onOpen={(seed) => setOpen({ kind: 'entry', entry: null, date: d, seed })} />
                        </li>
                      </ol>
                    </section>
                  )
                })}
              </div>

              {/* Band 3 — the picked day */}
              <aside className="flex flex-col gap-10 min-h-0 min-w-0 overflow-y-auto rounded-card border border-border-subtle bg-surface p-12" aria-label={t('Picked day')}>
                <div className="flex items-start gap-8">
                  <DayHeading date={sel} today={today} />
                  <button type="button" onClick={() => setOpen({ kind: 'milestone', milestone: null, date: sel })} className="ml-auto h-20 px-8 rounded-pill border border-border-default text-10 font-mono text-tertiary hover:text-primary inline-flex items-center gap-4" title={t('Set a milestone on this day')}>
                    <Flag size={10} aria-hidden /> {t('milestone')}
                  </button>
                  <button type="button" onClick={() => setOpen({ kind: 'task', row: null, due: sel })} className="h-20 px-8 rounded-pill border border-border-default text-10 font-mono text-tertiary hover:text-primary inline-flex items-center gap-4" title={t('New task due this day')}>
                    <Plus size={10} aria-hidden /> {t('task')}
                  </button>
                </div>

                <div className="flex flex-col gap-2">
                  <span className={LABEL}>{t('on the day')}</span>
                  {selItems.length === 0 && <p className="text-11 text-tertiary">{t('Nothing planned.')}</p>}
                  <ol className="flex flex-col gap-1">
                    {selItems.map((it) => <li key={`${it.kind}:${it.id}`}><ItemPill item={it} showWhy {...pillHandlers} /></li>)}
                  </ol>
                  {/* Keyed by the scope: a new board means a new default project for the line. */}
                  <QuickAdd key={project} project={project} projects={codes} date={sel} onTask={newTask} onOpen={(seed) => setOpen({ kind: 'entry', entry: null, date: sel, seed })} />
                </div>

                {layers.includes('facts') && (
                  <div className="flex flex-col gap-4">
                    <span className={LABEL}>{t('the work')}</span>
                    {factRows(selFacts).length === 0 ? (
                      <p className="text-11 text-tertiary">{t('No chats or commits on this day.')}</p>
                    ) : (
                      <table className="text-11 font-mono tabular">
                        <tbody>
                          {factRows(selFacts).map(([k, v]) => (
                            <tr key={k}><td className="text-tertiary pr-12 py-1">{k}</td><td className="text-primary text-right py-1">{v}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    <div className="[&_li>a]:h-32"><SessionsOfDay sessions={p.sessions} date={sel} /></div>
                  </div>
                )}

                <div
                  className="flex flex-col gap-4 min-h-0"
                  onDragOver={(e) => { if (e.dataTransfer.types.includes('text/sp-task')) { e.preventDefault(); e.dataTransfer.dropEffect = 'move' } }}
                  onDrop={(e) => { const tid = droppedTask(e); if (tid) { e.preventDefault(); void writes.patchTask.mutateAsync({ id: tid, due_date: '' }).then(() => toast.success(t('Due date cleared.'))).catch(() => toast.error(t('Could not clear the due date'))) } }}
                >
                  <div className="flex items-center gap-6">
                    <span className={LABEL}>{t('undated')}</span>
                    <span className="text-10 font-mono text-tertiary tabular">{undated.length}</span>
                    <input value={undatedQ} onChange={(e) => setUndatedQ(e.target.value)} aria-label={t('Find undated task')} placeholder={t('Find')} className={`${FIELD} ml-auto h-20 py-0 w-[120px]`} />
                  </div>
                  <p className="text-10 text-tertiary leading-snug">{t('Drag a task onto a day to set its due date. Drop one here to clear it.')}</p>
                  <ol className="flex flex-col gap-1 max-h-[280px] overflow-y-auto">
                    {undated.map((task) => (
                      <li key={task.id}>
                        <button
                          type="button"
                          draggable
                          onDragStart={(e) => dragTask(e, task.id)}
                          onClick={() => void openTask(task.id)}
                          title={`${task.title} · ${task.status}${task.assignee ? ` · ${task.assignee}` : ''}. ${t('Drag onto a day.')}`}
                          className="w-full flex items-center gap-6 h-24 px-6 rounded-input text-left text-11 text-primary hover:bg-hover cursor-grab"
                        >
                          <span aria-hidden className="text-tertiary">⋮⋮</span>
                          <span className="truncate">{task.title}</span>
                          <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{task.status}</span>
                        </button>
                      </li>
                    ))}
                    {undated.length === 0 && <li className="text-11 text-tertiary px-6">{t('Every open task has a date.')}</li>}
                  </ol>
                </div>
              </aside>
            </div>
          </>
        )}
      </div>

      {open?.kind === 'task' && (
        <TaskAddModal
          projectCode={open.row?.project || open.project || lastProject(codes, project)}
          boardProjects={!open.row && scope.multi && codes.length > 1 ? codes : undefined}
          initialStatus={open.row?.status || 'todo'}
          initialDue={open.due ? toSpDate(open.due) : undefined}
          initialTitle={open.title}
          existingTask={open.row}
          onClose={() => setOpen(null)}
          onSaved={() => { writes.refresh(); setOpen(null) }}
        />
      )}
      {open?.kind === 'entry' && p && (
        <EntryWindow project={project} projects={codes} date={open.date} entry={open.entry} seed={open.seed} tasks={p.tasks} milestones={p.milestones} onClose={() => setOpen(null)} />
      )}
      {open?.kind === 'milestone' && p && (
        <MilestoneWindow project={project} projects={codes} milestone={open.milestone} tasks={p.tasks} date={open.date} onClose={() => setOpen(null)} />
      )}
    </CalendarShell>
  )
}

/** A day column's quick-add, folded to one "+" until it is wanted, so seven
 *  identical fields do not sit under an empty week. It unfolds focused and
 *  folds again when it loses focus empty. */
function ColumnAdd({ project, projects, date, onTask, onOpen }: { project: string; projects: string[]; date: string; onTask: (title: string, date: string, project: string) => void; onOpen: (q: Quick) => void }) {
  const [on, setOn] = useState(false)
  if (!on) {
    return (
      <button type="button" onClick={() => setOn(true)} title={t('Add a meeting, deadline, note, or /task on this day')} aria-label={t('Add on {date}', { date: shortDate(date) })}
        className="w-full h-20 rounded-input text-10 font-mono text-tertiary opacity-60 hover:opacity-100 hover:bg-hover text-left px-4">
        + {t('add')}
      </button>
    )
  }
  return (
    <div onBlur={(e) => { const v = (e.target as HTMLInputElement).value ?? ''; if (!v.trim() && !e.currentTarget.contains(e.relatedTarget as Node | null)) setOn(false) }}>
      <QuickAdd project={project} projects={projects} date={date} autoFocus onTask={onTask} onOpen={onOpen} />
    </div>
  )
}
