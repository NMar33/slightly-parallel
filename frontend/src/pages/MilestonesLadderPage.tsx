import { forwardRef, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, Check, ChevronDown, ChevronRight, Flag, Pencil, Plus } from 'lucide-react'

import { toast } from '../components/primitives'
import { Button } from '../components/primitives/Button'
import { IconButton } from '../components/primitives/IconButton'
import { ErrorBanner, LoadingSkeleton } from '../components/states'
import { useHashState } from '../hooks/useHashState'
import { CalendarShell, MilestoneWindow, type CalendarPageProps } from '../features/calendar/parts'
import { lastProject, rememberProject, scopePatch, useProjectCodes, useScope } from '../features/calendar/data'
import { usePageKeys } from '../features/calendar/keys'
import { openTaskRow } from '../features/calendar/tasks'
import { isDone, isoToday, relativeDay, type Milestone } from '../features/calendar/model'

import { readLadder, useMilestoneWrites, useMilestones, type StepRead, useProjectTasks } from '../features/milestones/data'
import { Distance, ProofLine, ReasonLine, StepProgress, TaskLine, TemplateOffer } from '../features/milestones/parts'
import { TaskAddModal } from '../features/project/kanban/TaskWindow'
import type { TaskRow } from '../features/project/kanban/model'
import { FIELD, LABEL, PillGroup } from '../features/promptlib/taskstyle'
import { t, tn } from '../i18n/scope/pages'

/**
 * Milestones v01 — the ladder.
 *
 * The steps top to bottom, joined by a rail; the step the project is on
 * stands open with its outcome, its check, its distance and the tasks that
 * still stand between. Reached steps carry their date and proof; the rest
 * are folded to one line each. Order is the operator's: the arrows write
 * `position`.
 */

const NODE = 12

type TaskWin = { kind: 'edit'; row: TaskRow } | { kind: 'new'; milestone: Milestone }

export default function MilestonesLadderPage({ projectCode, embedded, views, onView }: CalendarPageProps) {
  const [hash, setHash] = useHashState()
  // Milestones are per project. Inside the calendar the scope may be a
  // board or every project; the ladder then shows one of them and offers
  // the others as pills.
  const scope = useScope(hash, projectCode)
  const known = useProjectCodes()
  const choices = scope.multi ? (scope.codes.length ? scope.codes : known) : []
  const project = projectCode || (scope.multi ? (hash.ladder && choices.includes(hash.ladder) ? hash.ladder : lastProject(choices)) : scope.key)
  const showDropped = hash.dropped === '1'
  const openIds = useMemo(() => new Set((hash.open ?? '').split(',').filter(Boolean)), [hash.open])
  const today = isoToday()

  const ms = useMilestones(project)
  const tasksQ = useProjectTasks(project)
  const writes = useMilestoneWrites(project)
  const tasks = useMemo(() => tasksQ.data ?? [], [tasksQ.data])
  const steps = useMemo(() => readLadder(ms.data?.milestones ?? [], tasks, today), [ms.data, tasks, today])
  const shown = useMemo(() => steps.filter((s) => showDropped || !s.dropped), [steps, showDropped])

  const [msWin, setMsWin] = useState<{ milestone?: Milestone | null } | null>(null)
  const [taskWin, setTaskWin] = useState<TaskWin | null>(null)
  const [focus, setFocus] = useState<number>(-1)
  const rowRefs = useRef<Array<HTMLElement | null>>([])

  const isOpen = (s: StepRead) => s.current || openIds.has(s.milestone.id)
  const toggle = useCallback((id: string) => {
    const next = new Set(openIds)
    if (next.has(id)) next.delete(id); else next.add(id)
    setHash({ open: [...next].join(',') })
  }, [openIds, setHash])

  const openTask = (id: string) => openTaskRow(id, (row) => setTaskWin({ kind: 'edit', row }))

  /** A task written from a step joins it: the task window hands back the
   *  id it created, and only that id is linked. */
  const afterNewTask = async (milestone: Milestone, id?: string) => {
    if (id) {
      try {
        await writes.linkTasks.mutateAsync({ id: milestone.id, add: [id] })
      } catch {
        toast.error(t('The task was saved but not linked. Pick the milestone in its window.'))
      }
    }
    writes.refresh()
  }

  const reorder = async (from: number, dir: -1 | 1) => {
    // Over the rows that are shown: with dropped ones hidden, "down" means
    // the next visible neighbour, never a hidden dropped row.
    const order = shown.map((s) => s.milestone)
    const to = from + dir
    if (to < 0 || to >= order.length) return
    const a = order[from]!
    const b = order[to]!
    // Swap the two neighbours' positions; only when positions collide (rows
    // written without one) does the whole ladder get renumbered.
    const distinct = new Set(order.map((m) => m.position)).size === order.length && order.every((m) => m.position > 0)
    let changes: Array<{ id: string; position: number }>
    if (distinct) {
      changes = [{ id: a.id, position: b.position }, { id: b.id, position: a.position }]
    } else {
      const next = [...order]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved!)
      changes = next.map((m, i) => ({ id: m.id, position: i + 1 })).filter((c) => order.find((m) => m.id === c.id)!.position !== c.position)
    }
    try {
      for (const c of changes) await writes.updateMilestone.mutateAsync({ id: c.id, position: c.position })
      setFocus(to)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('Could not reorder'))
    }
  }

  const reach = async (m: Milestone, proof: string) => {
    try {
      await writes.updateMilestone.mutateAsync({ id: m.id, status: 'reached', proof })
      toast.success(t('Reached: {title}', { title: m.title }))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('Could not mark it reached'))
    }
  }

  // j / k walk the ladder, Enter unfolds; nothing while a window or a field has focus.
  usePageKeys((e) => {
    if (msWin || taskWin) return
    // Enter on a button or a link is that control's own.
    if (e.key === 'Enter' && (e.target as HTMLElement | null)?.closest?.('button, a, [role="radio"], [role="tab"]')) return
    if (e.key === 'j' || e.key === 'k') {
      e.preventDefault()
      setFocus((f) => {
        const n = Math.min(shown.length - 1, Math.max(0, f + (e.key === 'j' ? 1 : -1)))
        rowRefs.current[n]?.scrollIntoView({ block: 'nearest' })
        return n
      })
    } else if (e.key === 'Enter' && focus >= 0 && shown[focus]) {
      e.preventDefault()
      const s = shown[focus]!
      if (!s.current) toggle(s.milestone.id)
    }
  })

  const reached = steps.filter((s) => s.reached).length
  const live = steps.filter((s) => !s.dropped).length
  const current = steps.find((s) => s.current)
  const tally = steps.length ? t('{reached} of {live} reached', { reached, live }) : undefined
  const summary = current
    ? `${t('next milestone: {title}', { title: current.milestone.title })}${current.daysLeft !== null ? ` · ${relativeDay(current.milestone.target_date, today)}` : ''} · ${tn(current.open.length, '{n} open task', '{n} open tasks')}`
    : steps.length ? t('every step reached') : ''

  return (
    <CalendarShell
      view="milestones"
      scope={scope}
      onScope={(v) => setHash({ ...scopePatch(v), open: '', ladder: '' })}
      embedded={embedded}
      views={views}
      onView={onView}
      tally={tally}
      right={(
        <>
          <button
            type="button"
            onClick={() => setHash({ dropped: showDropped ? '' : '1' })}
            aria-pressed={showDropped}
            className={`h-24 px-8 rounded-pill border text-11 font-mono ${showDropped ? 'border-border-strong text-primary' : 'border-border-subtle text-tertiary hover:text-primary'}`}
            title={t('Show dropped milestones')}
          >
            {t('dropped')} {steps.filter((s) => s.dropped).length}
          </button>
          <Button variant="primary" size="sm" onClick={() => setMsWin({ milestone: null })} iconLeft={<Plus size={12} aria-hidden />}>
            {t('New milestone')}
          </Button>
        </>
      )}
    >
      <div className="flex flex-col gap-12 max-w-[720px] min-w-0">
        {scope.multi && choices.length > 1 && (
          <PillGroup label={t('ladder of')} value={project} onChange={(v) => { if (v) { rememberProject(v); setHash({ ladder: v, open: '' }) } }} options={choices.map((c) => [c, c])} hint={t('Milestones are per project')} />
        )}
        <ReasonLine project={project} />

        {(ms.isLoading || tasksQ.isLoading) && <LoadingSkeleton variant="row" count={4} />}
        {ms.isError && <ErrorBanner title={t('Could not read the milestones')} hideDismiss />}

        {ms.data && steps.length === 0 && <TemplateOffer project={project} />}

        {steps.length > 0 && (
          <>
            {summary && (
              <div className="text-12 font-mono text-secondary tabular flex items-center gap-8">
                <Flag size={12} aria-hidden className="text-brand" />
                <span>{summary}</span>
              </div>
            )}

            <ol className="relative flex flex-col" aria-label={t('Milestones')}>
              {/* The rail: one line behind every node. */}
              <span aria-hidden className="absolute top-12 bottom-12 w-2 bg-border-default" style={{ left: NODE / 2 - 1 }} />
              {shown.map((s, i) => (
                <Step
                  key={s.milestone.id}
                  ref={(el) => { rowRefs.current[i] = el }}
                  step={s}
                  open={isOpen(s)}
                  focused={focus === i}
                  today={today}
                  first={i === 0}
                  last={i === shown.length - 1}
                  onToggle={() => { setFocus(i); if (!s.current) toggle(s.milestone.id) }}
                  onEdit={() => setMsWin({ milestone: s.milestone })}
                  onReach={(proof) => void reach(s.milestone, proof)}
                  onAddTask={() => setTaskWin({ kind: 'new', milestone: s.milestone })}
                  onTask={(id) => void openTask(id)}
                  onMove={(dir) => void reorder(shown.findIndex((x) => x.milestone.id === s.milestone.id), dir)}
                  busy={writes.updateMilestone.isPending}
                />
              ))}
            </ol>
            <div className="text-10 font-mono text-tertiary px-24">{t('j k move · Enter unfolds · arrows on a step reorder')}</div>
          </>
        )}
      </div>

      {msWin && (
        <MilestoneWindow project={project} milestone={msWin.milestone} tasks={tasks} onClose={() => { setMsWin(null); writes.refresh() }} />
      )}
      {taskWin?.kind === 'edit' && (
        <TaskAddModal
          projectCode={taskWin.row.project || project}
          initialStatus={taskWin.row.status || 'todo'}
          existingTask={taskWin.row}
          onClose={() => setTaskWin(null)}
          onSaved={() => { writes.refresh(); setTaskWin(null) }}
        />
      )}
      {taskWin?.kind === 'new' && (
        <TaskAddModal
          projectCode={project}
          initialStatus="todo"
          onClose={() => setTaskWin(null)}
          onSaved={(o) => { void afterNewTask(taskWin.milestone, o?.id); if (!o?.keepOpen) setTaskWin(null) }}
        />
      )}
    </CalendarShell>
  )
}

// ---------------------------------------------------------------------------
// One step
// ---------------------------------------------------------------------------

const Step = forwardRef<HTMLLIElement, {
  step: StepRead
  open: boolean
  focused: boolean
  today: string
  first: boolean
  last: boolean
  busy: boolean
  onToggle: () => void
  onEdit: () => void
  onReach: (proof: string) => void
  onAddTask: () => void
  onTask: (id: string) => void
  onMove: (dir: -1 | 1) => void
}>(function Step({ step, open, focused, today, first, last, busy, onToggle, onEdit, onReach, onAddTask, onTask, onMove }, ref) {
  const m = step.milestone
  const [proof, setProof] = useState(m.proof || '')
  const [reaching, setReaching] = useState(false)
  useEffect(() => setProof(m.proof || ''), [m.proof])
  const tone = step.reached ? 'var(--status-green)' : step.dropped ? 'var(--status-neutral)' : step.current ? 'var(--brand)' : 'var(--border-strong)'

  return (
    <li ref={ref} className={`relative pl-24 py-6 rounded-card ${focused ? 'ring-1 ring-brand' : ''}`} aria-current={step.current ? 'step' : undefined}>
      {/* the node on the rail */}
      <span
        aria-hidden
        className="absolute rounded-pill"
        style={{
          left: 0, top: 12, width: NODE, height: NODE,
          backgroundColor: step.reached ? tone : 'var(--bg-base)',
          border: `2px ${step.dropped ? 'dashed' : 'solid'} ${tone}`,
          boxShadow: step.current ? '0 0 0 3px var(--brand-glow)' : 'none',
        }}
      />
      {/* the row: always there */}
      <div className="flex items-center gap-8 min-w-0">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex-1 min-w-0 flex items-center gap-8 text-left rounded-input px-4 -mx-4 h-24 hover:bg-hover"
          title={step.current ? t('The step the project is on') : open ? t('Fold') : t('Unfold')}
        >
          {!step.current && (open ? <ChevronDown size={12} aria-hidden className="text-tertiary shrink-0" /> : <ChevronRight size={12} aria-hidden className="text-tertiary shrink-0" />)}
          <span className={`truncate ${open ? 'text-16 font-semibold text-primary' : 'text-13 text-primary'} ${step.dropped ? 'line-through text-tertiary' : ''}`}>{m.title}</span>
          {step.current && <span className="text-10 font-mono uppercase tracking-wider text-brand shrink-0">{t('now')}</span>}
        </button>
        <Distance step={step} />
        <StepProgress step={step} width={80} />
        <span className="inline-flex items-center">
          <IconButton size={20} label={t('Move up')} onClick={() => onMove(-1)} disabled={first || busy}><ArrowUp size={11} aria-hidden /></IconButton>
          <IconButton size={20} label={t('Move down')} onClick={() => onMove(1)} disabled={last || busy}><ArrowDown size={11} aria-hidden /></IconButton>
        </span>
      </div>

      {open && (
        <div className="mt-6 flex flex-col gap-8 rounded-card border border-border-subtle bg-surface p-12">
          {(m.outcome || m.check) ? (
            <div className="grid gap-x-12 gap-y-4" style={{ gridTemplateColumns: 'max-content minmax(0, 1fr)' }}>
              {m.outcome && <><span className={LABEL}>{t('outcome')}</span><span className="text-13 text-primary">{m.outcome}</span></>}
              {m.check && <><span className={LABEL}>{t('done when')}</span><span className="text-13 text-primary">{m.check}</span></>}
            </div>
          ) : (
            <p className="text-12 text-tertiary italic">{t('No outcome or check yet. Edit the milestone to add them.')}</p>
          )}
          {step.reached && <ProofLine proof={m.proof} />}

          <div className="flex flex-col gap-1">
            <div className="flex items-baseline gap-8">
              <span className={LABEL}>{t('tasks')}</span>
              <span className="text-11 font-mono text-tertiary tabular">
                {step.tasks.length === 0 ? t('none yet') : step.open.length === 0 ? t('all {n} done', { n: step.tasks.length }) : tn(step.open.length, '{n} task still open on this milestone', '{n} tasks still open on this milestone')}
                {step.slipping > 0 && <span className="text-status-amber"> · {t('{n} slipping', { n: step.slipping })}</span>}
              </span>
              <button type="button" onClick={onAddTask} className="ml-auto h-20 px-8 rounded-pill border border-border-default text-10 font-mono text-tertiary hover:text-primary inline-flex items-center gap-4" title={t('New task for this milestone')}><Plus size={10} aria-hidden /> {t('task')}</button>
            </div>
            {[...step.open, ...step.tasks.filter((t) => isDone(t) || t.archived)].map((t) => <TaskLine key={t.id} task={t} today={today} dates="relative" onOpen={() => onTask(t.id)} />)}
          </div>

          <div className="flex items-center gap-8 flex-wrap pt-6 border-t border-border-subtle">
            {!step.reached && !step.dropped && !reaching && (
              <Button variant="primary" size="sm" onClick={() => setReaching(true)} iconLeft={<Check size={12} aria-hidden />}>{t('Reached')}</Button>
            )}
            {reaching && (
              <div className="flex items-center gap-6 flex-1 min-w-0">
                <span className={LABEL}>{t('proof')}</span>
                <input value={proof} onChange={(e) => setProof(e.target.value)} aria-label={t('proof')} placeholder={t('Proof: a link, a number or a sentence')} autoFocus
                  onKeyDown={(e) => { if (e.key === 'Enter') { onReach(proof); setReaching(false) } if (e.key === 'Escape') setReaching(false) }}
                  className={`${FIELD} font-sans text-12 flex-1 min-w-0`} />
                <Button variant="primary" size="sm" onClick={() => { onReach(proof); setReaching(false) }} disabled={busy} iconLeft={<Check size={12} aria-hidden />}>{t('Reached')}</Button>
                <Button size="sm" onClick={() => setReaching(false)}>{t('Cancel')}</Button>
              </div>
            )}
            {!reaching && (
              <Button size="sm" onClick={onEdit} iconLeft={<Pencil size={11} aria-hidden />}>{t('Edit')}</Button>
            )}
          </div>
        </div>
      )}
    </li>
  )
})

