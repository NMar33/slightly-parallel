/**
 * A task's notes inside the task window — one compact form, shared by
 * every variant of the page. A section like the window's Links and Story:
 * open while it holds anything. Notes that wait on an answer first. Each
 * note: kind, title, when, version, the chat that wrote it, the first
 * paragraph, up to three pictures, whether it is this task's own note or
 * only names the task; then its open blocks, working, the same marks as on
 * the page. "Read here" unfolds the whole note in the window's own scroll;
 * "Open on the Notes page" goes to the note there.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '../../../components/primitives/Button'
import { LABEL } from '../../../components/ui'
import { t, tn } from '../../../i18n/scope/notes'
import { Checklist, Choice, CopyBlock, Gallery, NoteBody } from './blocks'
import { isTicked, openOf, useMarks, useNoteEnv } from './env'
import { allBlocks, type Block, type Note } from './model'
import { KindMark, OpenWords, Outline, goTo, stampOf, useOpen } from './parts'

function Entry({ note, own, taskId, others }: { note: Note; own: boolean; taskId: string; others: number }) {
  const m = useMarks()
  const env = useNoteEnv()
  const open = useOpen(note)
  const [read, setRead] = useState(false)
  const flat = allBlocks(note).map((x) => x.block)
  const gallery = flat.find((b): b is Extract<Block, { type: 'gallery' }> => b.type === 'gallery')
  const choices = flat.filter((b): b is Extract<Block, { type: 'choice' }> => b.type === 'choice' && m.answers[b.id] == null)
  const check = flat.find((b): b is Extract<Block, { type: 'check' }> => b.type === 'check' && b.items.some((it) => !isTicked(m, it.id, it.done)))
  const paste = note.kind === 'paste' ? flat.find((b): b is Extract<Block, { type: 'copy' }> => b.type === 'copy') : undefined
  return (
    <li data-note={note.id} className="flex flex-col gap-6 rounded-input border border-border-subtle bg-surface px-10 py-8 min-w-0">
      <div className="flex items-start gap-8 min-w-0">
        <KindMark kind={note.kind} />
        <span className="text-13 text-primary font-medium leading-snug flex-1 min-w-0">{note.title}</span>
        <OpenWords open={open} done={false} />
      </div>
      <div className="flex items-center gap-x-8 gap-y-2 flex-wrap text-10 font-mono text-tertiary">
        <span>{stampOf(note.updated, env.now())}</span><span>v{note.versions}</span><span>{note.chat}</span>
        <span className={own ? 'text-brand' : ''}>{own ? t('this task\'s note') : t('names this task')}</span>
        {others > 0 && <span>{tn(others, 'also in {n} other task', 'also in {n} other tasks')}</span>}
      </div>
      <p className="m-0 text-12 text-secondary leading-relaxed line-clamp-3">{note.lead}</p>
      {gallery && <Gallery block={gallery} size="strip" />}
      {!read && choices.map((c) => <Choice key={c.id} block={c} />)}
      {!read && check && <Checklist block={check} limit={3} />}
      {!read && paste && <CopyBlock block={paste} density="compact" lines={4} />}
      <div className="flex items-center gap-12 flex-wrap">
        <Button variant="link" size="bare" className="text-12" onClick={() => setRead((r) => !r)}>
          {read ? t('Fold') : t('Read here · {n}', { n: tn(note.words, '{n} word', '{n} words') })}
        </Button>
        <Link to={env.noteHref(note.id)} className="text-12 text-tertiary hover:text-brand">{t('Open on the Notes page')}</Link>
        <span className="ml-auto text-10 font-mono text-tertiary">{taskId === note.task ? '' : note.task}</span>
      </div>
      {read && (
        <div className="flex flex-col gap-10 border-t border-border-subtle pt-8 min-w-0">
          <details className="rounded-input border border-border-subtle px-8 py-4"><summary className={`${LABEL} cursor-pointer`}>{t('Outline')}</summary><Outline note={note} onGo={goTo} /></details>
          <NoteBody note={note} density="compact" />
        </div>
      )}
    </li>
  )
}

export function TaskNotes({ taskId, notes }: { taskId: string; notes: Note[] }) {
  const m = useMarks()
  const mine = notes.filter((n) => n.task === taskId || n.refs.includes(taskId))
  const [order] = useState(() => [...mine].sort((a, b) => {
    const oa = openOf(a, m); const ob = openOf(b, m)
    return (ob.toAnswer - oa.toAnswer) || (ob.toTick + ob.toCopy - oa.toTick - oa.toCopy) || b.updated.localeCompare(a.updated)
  }).map((n) => n.id))
  const list = order.map((id) => mine.find((n) => n.id === id)!).filter(Boolean)
  const waiting = list.filter((n) => openOf(n, m).toAnswer > 0).length
  return (
    <details className="border-t border-border-subtle pt-8" open={list.length > 0} data-testid="task-notes">
      <summary className={`${LABEL} cursor-pointer hover:text-brand`}>
        {t('Notes')} <span className="text-tertiary/70">— {list.length ? `${list.length}` : t('none')}{waiting ? ` · ${tn(waiting, '{n} waits on an answer', '{n} wait on an answer')}` : ''}</span>
      </summary>
      <ul className="mt-6 flex flex-col gap-6 m-0 p-0 list-none">
        {list.map((n) => (
          <Entry key={n.id} note={n} own={n.task === taskId} taskId={taskId}
            others={new Set(n.refs.filter((r) => r.startsWith('tk_') && r !== taskId)).size} />
        ))}
      </ul>
    </details>
  )
}
