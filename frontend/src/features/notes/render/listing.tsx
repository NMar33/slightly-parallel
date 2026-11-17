/**
 * The list beside the feed and what the shelves group by (design round 2,
 * kept by K): notes grouped under their tasks, what the operator does with
 * a note, a row of the list, and the rail's box of the note's task.
 */

import { useEffect, useRef } from 'react'

import { t, tn } from '../../../i18n/scope/notes'
import { IdChip } from './blocks'
import { openOf, useMarks, useNoteEnv, type Marks, type Open } from './env'
import type { Note } from './model'
import { agoOf, KindMark, newestFirst, OpenWords, ProjectMark, useOpen } from './parts'

const waits = (o: Open) => o.toAnswer + o.toTick + o.toCopy > 0

/** Notes grouped by their task, the group with something waiting first, then the newest; notes without a task last. */
export function byTask(notes: Note[], marks: Marks): Array<{ task: string; notes: Note[]; waiting: number }> {
  const groups = new Map<string, Note[]>()
  for (const n of [...notes].sort(newestFirst)) groups.set(n.task, [...(groups.get(n.task) ?? []), n])
  return [...groups.entries()].map(([task, ns]) => ({
    task,
    notes: [...ns].sort((a, b) => Number(waits(openOf(b, marks))) - Number(waits(openOf(a, marks))) || newestFirst(a, b)),
    waiting: ns.filter((n) => openOf(n, marks).toAnswer > 0).length,
  })).sort((a, b) => Number(!a.task) - Number(!b.task) || Number(b.waiting > 0) - Number(a.waiting > 0) || newestFirst(a.notes[0]!, b.notes[0]!))
}

/** What the operator does with a note: its shelf in G's tile view. */
export type Act = 'answer' | 'hands' | 'paste' | 'read' | 'replaced'
export function actOf(n: Note, o: Open): Act {
  if (n.replacedBy) return 'replaced'
  if (o.toAnswer) return 'answer'
  if (o.toTick) return 'hands'
  if (o.toCopy) return 'paste'
  return 'read'
}
export const ACT_WORD: Record<Act, string> = {
  answer: t('To answer'), hands: t('To do by hand'), paste: t('To paste into a chat'), read: t('To read'), replaced: t('Replaced by a newer note'),
}
export const ACT_TONE: Record<Act, string> = { answer: 'text-status-amber', hands: 'text-status-amber', paste: 'text-brand', read: '', replaced: 'text-tertiary' }

/* ------------------------------------------------------------------- list */

/** Keep the current row in sight inside the list's own scroller (never scrolls the page). */
function useKeepInSight(on: boolean) {
  const ref = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const el = ref.current
    const nav = el?.closest('nav')
    if (!on || !el || !nav) return
    const r = el.getBoundingClientRect(); const b = nav.getBoundingClientRect()
    if (nav.scrollHeight > nav.clientHeight) {
      if (r.top < b.top) nav.scrollTop -= b.top - r.top + 8
      else if (r.bottom > b.bottom) nav.scrollTop += r.bottom - b.bottom + 8
    }
    if (nav.scrollWidth > nav.clientWidth) {
      if (r.left < b.left) nav.scrollLeft -= b.left - r.left + 8
      else if (r.right > b.right) nav.scrollLeft += r.right - b.right + 8
    }
  }, [on])
  return ref
}

export function ListRow({ note, current, onPick }: { note: Note; current: boolean; onPick: () => void }) {
  const open = useOpen(note)
  const now = useNoteEnv().now()
  const ref = useKeepInSight(current)
  return (
    <button ref={ref} type="button" onClick={onPick} aria-current={current ? 'true' : undefined} data-row={note.id}
      className={`text-left flex flex-col gap-4 rounded-card border px-10 py-8 min-w-0 shrink-0 w-[240px] lg:w-auto transition-colors ${current ? 'border-brand bg-brand-glow/50' : 'border-border-subtle bg-surface hover:bg-hover'} ${note.replacedBy ? 'opacity-70' : ''}`}>
      <span className="flex items-center gap-8 min-w-0">
        <KindMark kind={note.kind} />
        <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{agoOf(note.updated, now)}</span>
      </span>
      <span className="text-13 text-primary font-medium leading-snug">{note.title}</span>
      <span className="text-12 text-secondary leading-snug line-clamp-2">{note.lead}</span>
      <span className="flex items-center gap-8 flex-wrap min-w-0">
        <ProjectMark code={note.project} />
        <OpenWords open={open} done={false} />
      </span>
    </button>
  )
}

/* ------------------------------------------------------------------- rail */

/** The task of the note in view, as the task window lists its notes: each with what is open, this one marked. */
export function TaskBox({ note, notes, onGo, chip = true }: { note: Note; notes: Note[]; onGo: (id: string) => void; chip?: boolean }) {
  const marks = useMarks()
  if (!note.task) return <p className="m-0 text-12 text-tertiary">{t('This note has no task.')}</p>
  const mine = notes.filter((n) => n.task === note.task || n.refs.includes(note.task)).sort(newestFirst)
  return (
    <div className="flex flex-col gap-6 min-w-0">
      {chip && <IdChip id={note.task} full />}
      <ul className="m-0 p-0 list-none flex flex-col gap-2">
        {mine.map((n) => {
          const o = openOf(n, marks)
          return (
            <li key={n.id}>
              <button type="button" onClick={() => onGo(n.id)} aria-current={n.id === note.id ? 'true' : undefined}
                className={`w-full text-left flex flex-col gap-1 rounded-input px-6 py-4 text-12 hover:bg-hover ${n.id === note.id ? 'bg-brand-glow text-primary' : 'text-secondary'}`}>
                <span className="leading-snug">{n.title}</span>
                <span className="flex items-center gap-6 text-10 font-mono text-tertiary flex-wrap">
                  <span>{n.task === note.task ? t('this task\'s note') : t('names this task')}</span>
                  {o.toAnswer > 0 && <span className="text-status-amber">{tn(o.toAnswer, '{n} choice waits', '{n} choices wait')}</span>}
                  {o.toTick > 0 && <span className="text-status-amber">{t('{n} to tick', { n: o.toTick })}</span>}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
