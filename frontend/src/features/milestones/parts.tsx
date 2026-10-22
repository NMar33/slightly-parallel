/**
 * Shared parts of the milestones view: the project's reason, the ladder to
 * start from when there is none, and the small readings of a step.
 */
import { useEffect, useState } from 'react'
import { Check, Flag, Link2 } from 'lucide-react'

import { toast } from '../../components/primitives'
import { Button } from '../../components/primitives/Button'
import { isDone, isoToday, relativeDay, shortDate, type CalTask } from '../calendar/model'
import { dragTask } from '../calendar/parts'
import { FIELD, LABEL, PillGroup } from '../promptlib/taskstyle'
import {
  LADDERS, REASON_KINDS, distanceWord, useMilestoneWrites, useReason, useReasonWrite, type ReasonKind, type StepRead,
} from './data'

import { t } from '../../i18n/scope/views'
// ---------------------------------------------------------------------------
// The reason — one line, set once, edited in place
// ---------------------------------------------------------------------------

export function ReasonLine({ project, compact = false }: { project: string; compact?: boolean }) {
  const q = useReason(project)
  const write = useReasonWrite(project)
  const [editing, setEditing] = useState(false)
  const [kind, setKind] = useState<string>('')
  const [text, setText] = useState('')
  useEffect(() => {
    if (q.data && !editing) { setKind(q.data.kind); setText(q.data.text) }
  }, [q.data, editing])
  const save = async () => {
    try {
      await write.mutateAsync({ kind, text })
      setEditing(false)
      toast.success(t('Reason kept'))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("Couldn't save"))
    }
  }
  const kindLabel = REASON_KINDS.find((k) => k.key === q.data?.kind)?.label
  if (!editing) {
    const empty = !q.data?.kind && !q.data?.text
    return (
      <button type="button" onClick={() => setEditing(true)} title={t('Click to change the reason')}
        className={`text-left rounded-input px-8 py-6 -mx-8 hover:bg-hover flex items-baseline gap-8 min-w-0 ${compact ? '' : 'w-full'}`}>
        <span className={LABEL}>{t('for')}</span>
        {empty ? (
          <span className="text-12 text-tertiary italic">{t('Set the project goal: attention, money, time saved or learning.')}</span>
        ) : (
          <>
            {kindLabel && <span className="text-11 font-mono px-6 h-20 inline-flex items-center rounded-pill border border-brand text-brand bg-brand-glow">{kindLabel}</span>}
            <span className="text-13 text-primary truncate">{q.data?.text}</span>
          </>
        )}
      </button>
    )
  }
  return (
    <div className="flex flex-col gap-8 rounded-card border border-brand/40 bg-surface p-10">
      <PillGroup label={t('for')} value={kind} onChange={setKind} options={REASON_KINDS.map((k) => [k.key, k.label])} hint={t('the kind of value the project is after')} />
      <div className="flex flex-col gap-3">
        <span className={LABEL}>{t('in a line')}</span>
        <input value={text} onChange={(e) => setText(e.target.value)} aria-label={t('reason')} placeholder={t('an open-source dashboard people find and star')} autoFocus
          onKeyDown={(e) => { if (e.key === 'Enter') void save(); if (e.key === 'Escape') setEditing(false) }}
          className={`${FIELD} font-sans text-13`} />
      </div>
      <div className="flex items-center gap-8">
        <Button variant="primary" size="sm" onClick={() => void save()} disabled={write.isPending} iconLeft={<Check size={12} aria-hidden />}>{t('Keep')}</Button>
        <Button size="sm" onClick={() => setEditing(false)}>{t('Cancel')}</Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// A ladder to start from
// ---------------------------------------------------------------------------

export function TemplateOffer({ project, onDone }: { project: string; onDone?: () => void }) {
  const reason = useReason(project)
  const w = useMilestoneWrites(project)
  const [kind, setKind] = useState<ReasonKind>('attention')
  useEffect(() => { if (reason.data?.kind) setKind(reason.data.kind as ReasonKind) }, [reason.data?.kind])
  const [picked, setPicked] = useState<Set<number>>(() => new Set(LADDERS.attention.map((_, i) => i)))
  useEffect(() => { setPicked(new Set(LADDERS[kind].map((_, i) => i))) }, [kind])
  const steps = LADDERS[kind]
  const [busy, setBusy] = useState(false)
  const start = async () => {
    const chosen = steps.filter((_, i) => picked.has(i))
    if (chosen.length === 0) return
    setBusy(true)
    try {
      let pos = 1
      for (const s of chosen) {
        await w.createMilestone.mutateAsync({ title: s.title, outcome: s.outcome, check: s.check, position: pos++ })
      }
      toast.success(t('{length} milestones added. Edit them to fit the project.', { length: chosen.length }))
      onDone?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('Couldn\'t add the milestones'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="rounded-card border border-border-subtle bg-surface p-12 flex flex-col gap-10 max-w-[640px]">
      <div className="flex flex-col gap-4">
        <span className="text-14 font-semibold text-primary">{t('No milestones yet')}</span>
        <p className="text-12 text-secondary leading-snug">{t('Start from a template for this kind of project, or add your own milestones.')}</p>
      </div>
      <PillGroup label={t('project for')} value={kind} onChange={(v) => v && setKind(v as ReasonKind)} options={REASON_KINDS.map((k) => [k.key, k.label])} />
      <ol className="flex flex-col gap-2">
        {steps.map((s, i) => (
          <li key={s.title}>
            <label className={`flex items-start gap-8 px-8 py-6 rounded-input cursor-pointer ${picked.has(i) ? 'bg-hover' : 'hover:bg-hover'}`}>
              <input type="checkbox" checked={picked.has(i)} onChange={() => setPicked((cur) => { const n = new Set(cur); if (n.has(i)) n.delete(i); else n.add(i); return n })} className="accent-[var(--brand)] mt-2" aria-label={s.title} />
              <span className="flex flex-col gap-1 min-w-0">
                <span className="text-13 text-primary">{i + 1}. {s.title}</span>
                <span className="text-11 text-tertiary">{s.outcome} · <span className="text-secondary">{t('done when')}</span> {s.check}</span>
              </span>
            </label>
          </li>
        ))}
      </ol>
      <div className="flex items-center gap-8">
        <Button variant="primary" size="sm" onClick={() => void start()} disabled={busy || picked.size === 0} iconLeft={<Flag size={12} aria-hidden />}>
          {t('Start from these')}{' '}{picked.size}
        </Button>
        <span className="text-11 text-tertiary">{t('Or write your own with New milestone.')}</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Readings of a step
// ---------------------------------------------------------------------------

/** done/total as a thin bar with the count beside it. */
export function StepProgress({ step, width = 120 }: { step: StepRead; width?: number }) {
  const total = step.tasks.length
  const pct = total ? Math.round((step.doneN / total) * 100) : 0
  return (
    <span className="inline-flex items-center gap-6" title={total ? t('{doneN} of {total} tasks done', { doneN: step.doneN, total }) : t('no tasks yet')}>
      <span className="inline-block h-4 rounded-pill bg-elevated overflow-hidden" style={{ width }}>
        <span className="block h-full rounded-pill" style={{ width: `${pct}%`, backgroundColor: step.reached ? 'var(--status-green)' : 'var(--brand)' }} />
      </span>
      <span className="text-10 font-mono text-tertiary tabular">{total ? `${step.doneN}/${total}` : '—'}</span>
    </span>
  )
}

/** "in 12 days" in the colour of its meaning: late is red, soon is amber. */
export function Distance({ step }: { step: StepRead }) {
  if (step.reached) return <span className="text-11 font-mono text-status-green">{t('reached')}{step.milestone.reached_date ? ` · ${step.milestone.reached_date}` : ''}</span>
  if (step.dropped) return <span className="text-11 font-mono text-tertiary line-through">{t('dropped')}</span>
  const d = step.daysLeft
  const tone = d === null ? 'text-tertiary' : d < 0 ? 'text-status-red' : d <= 7 ? 'text-status-amber' : 'text-secondary'
  return <span className={`text-11 font-mono tabular ${tone}`}>{distanceWord(d)}{step.milestone.target_date ? ` · ${step.milestone.target_date}` : ''}</span>
}

/**
 * One task under a step — the same line on the ladder, the road and the
 * board. A dot says its state (done, slipping, open), the marks say when
 * it is due or planned, in short dates or in words.
 */
export function TaskLine({ task, onOpen, today = isoToday(), draggable = false, dates = 'short' }: {
  task: CalTask
  onOpen: () => void
  today?: string
  /** The road drags a task onto a step; the others only open it. */
  draggable?: boolean
  /** "24 Sep" or "in 3 days". */
  dates?: 'short' | 'relative'
}) {
  const done = isDone(task) || !!task.archived
  const slip = !done && ((!!task.due && task.due < today) || (!!task.planned && task.planned < today))
  const when = (iso: string) => (dates === 'relative' ? relativeDay(iso, today) : shortDate(iso))
  return (
    <button
      type="button"
      draggable={draggable || undefined}
      onDragStart={draggable ? (e) => dragTask(e, task.id) : undefined}
      onClick={onOpen}
      title={`${task.title} · ${task.status}${slip ? ' · slipping' : ''}`}
      className={`w-full min-w-0 flex items-center gap-6 h-24 px-6 rounded-input text-left text-12 hover:bg-hover ${draggable ? 'cursor-grab' : ''} ${done ? 'text-tertiary' : 'text-primary'}`}
    >
      <span aria-hidden className="w-6 h-6 rounded-pill shrink-0" style={{ backgroundColor: done ? 'var(--status-green)' : slip ? 'var(--status-amber)' : 'var(--status-neutral)' }} />
      <span className={`truncate ${done ? 'line-through' : ''}`}>{task.title}</span>
      <span className="ml-auto inline-flex items-center gap-6 text-10 font-mono text-tertiary tabular shrink-0">
        {task.due && !done && <span title={t('due {due}', { due: task.due })} className={task.due < today ? 'text-status-amber' : ''}>⚑ {when(task.due)}</span>}
        {task.planned && !done && <span title={t('planned {planned}', { planned: task.planned })} className={task.planned < today ? 'text-status-amber' : ''}>☀ {when(task.planned)}</span>}
        <span>{task.status}</span>
      </span>
    </button>
  )
}

export function ProofLine({ proof }: { proof: string }) {
  if (!proof) return null
  const isUrl = /^https?:\/\//i.test(proof)
  return (
    <span className="inline-flex items-center gap-4 text-11 text-secondary min-w-0">
      <Link2 size={11} aria-hidden className="shrink-0 text-tertiary" />
      {isUrl ? <a href={proof} target="_blank" rel="noreferrer" className="truncate underline decoration-border-strong hover:text-primary">{proof}</a> : <span className="truncate">{proof}</span>}
    </span>
  )
}


