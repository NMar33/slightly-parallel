/*
 * The calendar's windows — an entry, a milestone — in the task window's
 * idiom: labelled mono fields, pill radiogroups, one frame.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Check, Flag, Trash2, X } from 'lucide-react'

import { toast } from '../../components/primitives'
import { Button } from '../../components/primitives/Button'
import { Modal } from '../../components/Modal'
import { FIELD, LABEL, PillGroup } from '../promptlib/taskstyle'
import { lastProject, useCalendarWrites, type EntryInput, type MilestoneInput } from './data'
import {
  ENTRY_KINDS, KIND_COLOR, KIND_GLYPH, MILESTONE_STATUSES, isDone, shortDate,
  type CalEntry, type CalTask, type EntryKind, type Milestone, type Quick,
} from './model'

import { t } from '../../i18n/scope/views'
function Frame({ title, icon, onClose, children, width = 560, labelId }: { title: string; icon?: ReactNode; onClose: () => void; children: ReactNode; width?: number; labelId: string }) {
  return createPortal(
    <Modal tone="window" labelledBy={labelId} onClose={onClose} isolateKeys
      width="w-full" maxWidth={width} padding="p-14" className="flex flex-col gap-10">
        <div className="flex items-baseline gap-8 min-w-0">
          <span id={labelId} className="text-16 font-semibold text-primary inline-flex items-center gap-6">{icon} {title}</span>
          <button type="button" onClick={onClose} aria-label={t('Close')} className="ml-auto text-tertiary hover:text-primary"><X size={14} aria-hidden /></button>
        </div>
        {children}
    </Modal>,
    document.body,
  )
}

function Labelled({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-3">
      <span className={LABEL} title={hint}>{label}</span>
      {children}
    </div>
  )
}

const KIND_OPTIONS: Array<[string, string]> = ENTRY_KINDS.map((k) => [k, `${KIND_GLYPH[k]} ${k}`])

function ProjectPick({ value, onChange, projects, disabled }: { value: string; onChange: (c: string) => void; projects: string[]; disabled?: boolean }) {
  return (
    <Labelled label={t('project')}>
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} aria-label={t('project')} className={FIELD}>
        {!projects.includes(value) && value && <option value={value}>{value}</option>}
        {projects.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    </Labelled>
  )
}

export function EntryWindow({ project, date, entry, tasks, milestones, seed, onClose, projects }: {
  project: string
  /** The projects in view; more than one → the window asks which. */
  projects?: string[]
  /** The day the window opened on, for a new entry. */
  date: string
  entry?: CalEntry | null
  tasks: CalTask[]
  milestones: Milestone[]
  /** A parsed quick-add line to start from. */
  seed?: Quick | null
  onClose: () => void
}) {
  const w = useCalendarWrites(project)
  const isEdit = !!entry
  const [kind, setKind] = useState<string>(entry?.kind ?? seed?.kind ?? 'note')
  const [title, setTitle] = useState(entry?.title ?? seed?.title ?? '')
  const [day, setDay] = useState(entry?.date ?? seed?.date ?? date)
  const [time, setTime] = useState(entry?.time ?? seed?.time ?? '')
  const [endDate, setEndDate] = useState(entry?.end_date ?? '')
  const [endTime, setEndTime] = useState(entry?.end_time ?? seed?.end_time ?? '')
  const [body, setBody] = useState(entry?.body ?? '')
  const [people, setPeople] = useState(entry?.people ?? '')
  const [link, setLink] = useState(entry?.link ?? '')
  const [taskId, setTaskId] = useState(entry?.task_id ?? '')
  const [milestoneId, setMilestoneId] = useState(entry?.milestone_id ?? '')
  const [status, setStatus] = useState<string>(entry?.status ?? 'open')
  const choices = projects && projects.length > 0 ? projects : [project]
  const [proj, setProj] = useState(entry?.project || lastProject(choices, project))
  const titleRef = useRef<HTMLInputElement>(null)
  useEffect(() => { titleRef.current?.focus() }, [])
  const busy = w.createEntry.isPending || w.updateEntry.isPending || w.deleteEntry.isPending
  const openTasks = useMemo(() => tasks.filter((it) => !isDone(it) && !it.archived && (choices.length < 2 || it.project === proj)).sort((a, b) => a.title.localeCompare(b.title)), [tasks, choices.length, proj])

  const save = async () => {
    if (!title.trim()) { titleRef.current?.focus(); return }
    const input: EntryInput = { project: proj, kind, title: title.trim(), date: day, time, end_date: endDate, end_time: endTime, body, people, link, task_id: taskId, milestone_id: milestoneId, status }
    try {
      if (isEdit && entry) await w.updateEntry.mutateAsync({ id: entry.id, ...input })
      else await w.createEntry.mutateAsync(input)
      toast.success(isEdit ? t('Saved') : t('Added: {kind} · {when}', { kind: t(kind), when: shortDate(day) }))
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("Couldn't save"))
    }
  }
  const remove = async () => {
    if (!entry) return
    try {
      await w.deleteEntry.mutateAsync(entry.id)
      toast.success(t('Removed'))
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("Couldn't remove"))
    }
  }

  return (
    <Frame title={isEdit ? t('Edit entry') : t('New entry')} labelId="entry-window-title" onClose={onClose}
      icon={<span aria-hidden style={{ color: KIND_COLOR[kind as EntryKind] }}>{KIND_GLYPH[kind as EntryKind]}</span>}>
      <PillGroup label={t('kind')} value={kind} onChange={(v) => v && setKind(v)} options={KIND_OPTIONS} />
      {choices.length > 1 && !isEdit && <ProjectPick value={proj} onChange={setProj} projects={choices} />}
      <Labelled label={t('title')}>
        <input ref={titleRef} value={title} onChange={(e) => setTitle(e.target.value)} aria-label={t('title')} placeholder={t('Short title')}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void save() } }}
          className={`${FIELD} font-sans text-13`} />
      </Labelled>
      <div className="grid gap-8" style={{ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' }}>
        <Labelled label={t('date')}><input type="date" value={day} onChange={(e) => setDay(e.target.value)} aria-label={t('date')} className={FIELD} /></Labelled>
        <Labelled label={t('time')}><input type="time" value={time} onChange={(e) => setTime(e.target.value)} aria-label={t('time')} className={FIELD} /></Labelled>
        <Labelled label={t('until')} hint={t('Last day, for an entry that spans several days')}><input type="date" value={endDate} min={day} onChange={(e) => setEndDate(e.target.value)} aria-label={t('until date')} className={FIELD} /></Labelled>
        <Labelled label={t('end time')}><input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} aria-label={t('end time')} className={FIELD} /></Labelled>
      </div>
      <Labelled label={t('notes')}>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} aria-label={t('notes')} rows={4} placeholder={t('Notes, agreements, things to bring')}
          className={`${FIELD} font-sans text-13 resize-y`} />
      </Labelled>
      <div className="grid gap-8" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
        <Labelled label={t('people')} hint="comma-separated"><input value={people} onChange={(e) => setPeople(e.target.value)} aria-label={t('people')} placeholder={t('Anna, Tom')} className={FIELD} /></Labelled>
        <Labelled label={t('link')}><input value={link} onChange={(e) => setLink(e.target.value)} aria-label={t('link')} placeholder="https://…" className={FIELD} /></Labelled>
        <Labelled label={t('task')}>
          <select value={taskId} onChange={(e) => setTaskId(e.target.value)} aria-label={t('task')} className={FIELD}>
            <option value="">—</option>
            {openTasks.map((it) => <option key={it.id} value={it.id}>{it.title}</option>)}
          </select>
        </Labelled>
        <Labelled label={t('milestone')}>
          <select value={milestoneId} onChange={(e) => setMilestoneId(e.target.value)} aria-label={t('milestone')} className={FIELD}>
            <option value="">—</option>
            {milestones.map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
          </select>
        </Labelled>
      </div>
      {isEdit && <PillGroup label={t('status')} value={status} onChange={(v) => v && setStatus(v)} options={[['open', 'open'], ['done', 'done'], ['cancelled', 'cancelled']]} />}
      <WindowFooter add={t('Add')} isEdit={isEdit} busy={busy} onSave={save} onClose={onClose} onRemove={remove} removeTitle={t('Remove this entry')} />
    </Frame>
  )
}

/** The two windows' last line: save (or add), cancel, and — editing — remove. */
function WindowFooter({ add, isEdit, busy, onSave, onClose, onRemove, removeTitle }: {
  add: string
  isEdit: boolean
  busy: boolean
  onSave: () => Promise<void> | void
  onClose: () => void
  onRemove: () => Promise<void> | void
  removeTitle: string
}) {
  return (
    <div className="flex items-center gap-8 pt-4 border-t border-border-subtle">
      <Button variant="primary" size="sm" onClick={() => void onSave()} disabled={busy} iconLeft={<Check size={12} aria-hidden />}>
        {isEdit ? 'Save' : add}
      </Button>
      <Button size="sm" onClick={onClose}>{t('Cancel')}</Button>
      {isEdit && (
        <button type="button" onClick={() => void onRemove()} disabled={busy} title={removeTitle}
          className="ml-auto h-24 px-8 rounded-input text-tertiary hover:text-status-red inline-flex items-center gap-4 text-11">
          <Trash2 size={12} aria-hidden /> {t('remove')}
        </button>
      )}
    </div>
  )
}

export function MilestoneWindow({ project, milestone, tasks, date, onClose, projects }: {
  project: string
  projects?: string[]
  milestone?: Milestone | null
  tasks: CalTask[]
  /** The day the window opened on: the target date of a new milestone. */
  date?: string
  onClose: () => void
}) {
  const w = useCalendarWrites(project)
  const isEdit = !!milestone
  const [title, setTitle] = useState(milestone?.title ?? '')
  const [outcome, setOutcome] = useState(milestone?.outcome ?? '')
  const [check, setCheck] = useState(milestone?.check ?? '')
  const [target, setTarget] = useState(milestone?.target_date ?? date ?? '')
  const [status, setStatus] = useState<string>(milestone?.status ?? 'planned')
  const [proof, setProof] = useState(milestone?.proof ?? '')
  const [picked, setPicked] = useState<Set<string>>(() => new Set(milestone?.tasks ?? []))
  const choices = projects && projects.length > 0 ? projects : [project]
  const [proj, setProj] = useState(milestone?.project || lastProject(choices, project))
  const [q, setQ] = useState('')
  const titleRef = useRef<HTMLInputElement>(null)
  useEffect(() => { titleRef.current?.focus() }, [])
  const busy = w.createMilestone.isPending || w.updateMilestone.isPending || w.linkTasks.isPending || w.deleteMilestone.isPending
  const candidates = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return tasks
      .filter((it) => !it.archived && (choices.length < 2 || it.project === proj) && (!needle || it.title.toLowerCase().includes(needle)))
      .filter((it) => picked.has(it.id) || !it.milestone_id || it.milestone_id === milestone?.id)
      .sort((a, b) => Number(picked.has(b.id)) - Number(picked.has(a.id)) || Number(isDone(a)) - Number(isDone(b)) || a.title.localeCompare(b.title))
  }, [tasks, q, picked, milestone?.id, choices.length, proj])
  const flip = (id: string) => setPicked((cur) => { const n = new Set(cur); if (n.has(id)) n.delete(id); else n.add(id); return n })

  const save = async () => {
    if (!title.trim()) { titleRef.current?.focus(); return }
    const input: MilestoneInput = { project: proj, title: title.trim(), outcome, check, target_date: target, status, proof }
    try {
      if (isEdit && milestone) {
        await w.updateMilestone.mutateAsync({ id: milestone.id, ...input })
        const before = new Set(milestone.tasks)
        const add = [...picked].filter((id) => !before.has(id))
        const remove = [...before].filter((id) => !picked.has(id))
        if (add.length || remove.length) await w.linkTasks.mutateAsync({ id: milestone.id, add, remove })
      } else {
        await w.createMilestone.mutateAsync({ ...input, tasks: [...picked] })
      }
      toast.success(isEdit ? t('Saved') : t('Milestone set'))
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("Couldn't save"))
    }
  }
  const remove = async () => {
    if (!milestone) return
    try {
      await w.deleteMilestone.mutateAsync(milestone.id)
      toast.success(t('Milestone removed. Its tasks were kept.'))
      onClose()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("Couldn't remove"))
    }
  }
  const doneN = [...picked].filter((id) => { const tv = tasks.find((x) => x.id === id); return tv && isDone(tv) }).length

  return (
    <Frame title={isEdit ? t('Milestone') : t('New milestone')} labelId="milestone-window-title" onClose={onClose} width={640}
      icon={<Flag size={15} aria-hidden style={{ color: status === 'reached' ? 'var(--status-green)' : 'var(--status-red)' }} />}>
      <p className="text-12 text-secondary leading-snug">{t('Describe a result that can be checked.')}</p>
      {choices.length > 1 && !isEdit && <ProjectPick value={proj} onChange={setProj} projects={choices} />}
      <Labelled label={t('milestone')}>
        <input ref={titleRef} value={title} onChange={(e) => setTitle(e.target.value)} aria-label={t('milestone')} placeholder={t('Article out · MVP a stranger can use · 30 stars')} className={`${FIELD} font-sans text-13`} />
      </Labelled>
      <Labelled label={t('outcome')} hint={t('Why it matters: attention, money, time saved')}>
        <input value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label={t('outcome')} placeholder={t('New readers learn why the project exists')} className={`${FIELD} font-sans text-13`} />
      </Labelled>
      <Labelled label={t('done when')} hint={t('How to check that the milestone is reached')}>
        <input value={check} onChange={(e) => setCheck(e.target.value)} aria-label={t('done when')} placeholder={t('the article is published and linked from the README')} className={`${FIELD} font-sans text-13`} />
      </Labelled>
      <div className="flex items-end gap-12 flex-wrap">
        <Labelled label={t('target')}><input type="date" value={target} onChange={(e) => setTarget(e.target.value)} aria-label={t('target date')} className={FIELD} /></Labelled>
        <PillGroup label={t('status')} value={status} onChange={(v) => v && setStatus(v)} options={MILESTONE_STATUSES.map((s) => [s, s])} />
      </div>
      {(status === 'reached' || proof) && (
        <Labelled label={t('proof')} hint={t('Evidence that it is reached: a link, a number or a sentence')}>
          <input value={proof} onChange={(e) => setProof(e.target.value)} aria-label={t('proof')} placeholder="https://… · 31 stars on 2026-09-30 · the client's mail" className={`${FIELD} font-sans text-13`} />
        </Labelled>
      )}
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-8">
          <span className={LABEL}>{t('tasks for this milestone')}</span>
          <span className="text-11 font-mono text-tertiary tabular">{doneN}/{picked.size} {t('done')}</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} aria-label={t('find task')} placeholder={t('find…')} className={`${FIELD} ml-auto h-20 py-0 w-[160px]`} />
        </div>
        <div className="max-h-[220px] overflow-y-auto rounded-input border border-border-subtle">
          {candidates.length === 0 && <p className="text-11 text-tertiary px-8 py-6">{t('No tasks match.')}</p>}
          {candidates.map((it) => (
            <label key={it.id} className={`flex items-center gap-8 px-8 h-32 cursor-pointer ${picked.has(it.id) ? 'bg-hover' : 'hover:bg-hover'}`}>
              <input type="checkbox" checked={picked.has(it.id)} onChange={() => flip(it.id)} className="accent-[var(--brand)]" aria-label={it.title} />
              <span className={`truncate text-12 ${isDone(it) ? 'text-tertiary line-through' : 'text-primary'}`}>{it.title}</span>
              <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{it.status}</span>
            </label>
          ))}
        </div>
      </div>
      <WindowFooter add={t('Set milestone')} isEdit={isEdit} busy={busy} onSave={save} onClose={onClose} onRemove={remove} removeTitle={t('Remove this milestone')} />
    </Frame>
  )
}
