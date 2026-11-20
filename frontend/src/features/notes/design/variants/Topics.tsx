/**
 * Variant C — Topics. A note belongs to a subject the operator comes back
 * to, and the subjects are the entry points. Left: the topics (with how
 * many notes, what is open, when last written). Right: the topic's dossier
 * — its picture, the tasks its notes name, the newest note read in full,
 * and the older ones under it, each saying when a newer note replaces it.
 * Notes with no entry point sit under their project.
 */

import { useState } from 'react'

import { Button } from '../../../../components/primitives/Button'
import { EmptyState } from '../../../../components/states'
import { LABEL } from '../../../../components/ui'
import { projectColor } from '../../../../utils/projectColor'
import { t, tn } from '../../../../i18n/scope/notes'
import { IdChip, MockShot, NoteBody } from '../blocks'
import { ENTITIES, SUPERSEDED_BY } from '../mock'
import type { Note } from '../model'
import { agoOf, FindBox, KindMark, matches, MetaLine, newestFirst, OpenWords, Outline, Rule, stampOf, useOpen, goTo } from '../parts'
import { NoteHead } from '../reader'
import { openOf, useMarks } from '../store'

interface Topic { key: string; name: string; project: string; ep?: string; notes: Note[] }

const SHOT_OF: Record<string, string> = { ep_7a31c0de: 'shot:list', ep_1b5e9d40: 'shot:single', ep_c40a7e22: 'shot:table', ep_5e81b3f6: 'shot:board' }

function topicsOf(notes: Note[]): Topic[] {
  const by = new Map<string, Topic>()
  for (const n of notes) {
    const key = n.entrypoint ?? `none:${n.project}`
    const e = n.entrypoint ? ENTITIES[n.entrypoint] : undefined
    if (!by.has(key)) by.set(key, { key, name: e?.title ?? t('No topic · {project}', { project: n.project }), project: n.project, ep: n.entrypoint, notes: [] })
    by.get(key)!.notes.push(n)
  }
  const list = [...by.values()]
  for (const tp of list) tp.notes.sort(newestFirst)
  return list.sort((a, b) => (a.ep ? 0 : 1) - (b.ep ? 0 : 1) || newestFirst(a.notes[0]!, b.notes[0]!))
}

function TopicItem({ topic, on, onPick }: { topic: Topic; on: boolean; onPick: () => void }) {
  const marks = useMarks()
  const open = topic.notes.reduce((s, n) => { const o = openOf(n, marks); return s + o.toAnswer + o.toTick + o.toCopy }, 0)
  return (
    <button type="button" onClick={onPick} aria-current={on}
      className={`text-left w-full shrink-0 md:shrink flex flex-col gap-2 rounded-input px-8 py-6 min-w-[200px] md:min-w-0 border ${on ? 'border-brand bg-brand-glow/50' : 'border-transparent hover:bg-hover'}`}>
      <span className="flex items-center gap-6 min-w-0">
        <span aria-hidden className="w-8 h-8 rounded-pill shrink-0" style={{ backgroundColor: projectColor(topic.project) }} />
        <span className={`text-13 truncate ${topic.ep ? 'text-primary' : 'text-secondary italic'}`}>{topic.name}</span>
      </span>
      <span className="flex items-center gap-8 text-10 font-mono text-tertiary pl-14">
        <span>{tn(topic.notes.length, '{n} note', '{n} notes')}</span>
        <span>{agoOf(topic.notes[0]!.updated)}</span>
        {open > 0 && <span className="text-status-amber">{tn(open, '{n} open', '{n} open')}</span>}
      </span>
    </button>
  )
}

function OlderNote({ note, read, onRead }: { note: Note; read: boolean; onRead: () => void }) {
  const open = useOpen(note)
  const by = SUPERSEDED_BY[note.id]
  return (
    <article data-note={note.id} className={`rounded-card border border-border-subtle bg-surface px-16 py-12 flex flex-col gap-8 min-w-0 ${by ? 'opacity-80' : ''}`}>
      {by && (
        <p className="m-0 text-12 text-status-amber">
          {t('Replaced by a newer note:')} <button type="button" className="text-brand hover:underline" onClick={() => goTo(by)}>{by}</button>. {t('Read that one first.')}
        </p>
      )}
      <div className="flex items-start gap-12 min-w-0">
        <h3 className="m-0 text-14 font-semibold text-primary flex-1 min-w-0">{note.title}</h3>
        <OpenWords open={open} />
      </div>
      <MetaLine note={note} />
      {read ? <NoteBody note={note} /> : (
        <div className="grid gap-12 md:grid-cols-[minmax(0,1fr)_240px] min-w-0">
          <p className="m-0 text-13 text-secondary leading-relaxed">{note.lead}</p>
          <div className="min-w-0"><Outline note={note} onGo={() => onRead()} /></div>
        </div>
      )}
      <Button variant="link" size="bare" className="self-start text-12" onClick={onRead}>{read ? t('Fold') : t('Read here')}</Button>
    </article>
  )
}

export function Topics({ notes }: { notes: Note[] }) {
  const [q, setQ] = useState('')
  const found = notes.filter((n) => matches(n, q))
  const topics = topicsOf(found)
  const [pick, setPick] = useState<string>(() => topicsOf(notes)[0]?.key ?? '')
  const [read, setRead] = useState<string | null>(null)
  const topic = topics.find((tp) => tp.key === pick) ?? topics[0]
  const newest = topic?.notes[0]
  const tasks = topic ? [...new Set(topic.notes.flatMap((n) => [n.task, ...n.refs.filter((r) => r.startsWith('tk_'))]).filter(Boolean))] : []
  return (
    <div className="grid gap-16 min-w-0 md:grid-cols-[240px_minmax(0,1fr)] items-start">
      <nav aria-label={t('Topics')} className="flex flex-col gap-8 min-w-0 md:sticky md:top-0">
        <FindBox value={q} onChange={setQ} found={found.length} of={notes.length} />
        <div className="flex md:flex-col gap-2 overflow-x-auto md:overflow-visible min-w-0 pb-2">
          {topics.map((tp) => <TopicItem key={tp.key} topic={tp} on={tp.key === topic?.key} onPick={() => { setPick(tp.key); setRead(null) }} />)}
        </div>
        {!topics.length && <EmptyState compact title={t('Nothing matches.')} />}
      </nav>
      {topic && newest ? (
        <div className="flex flex-col gap-16 min-w-0">
          <header className="grid gap-16 min-w-0 sm:grid-cols-[minmax(0,1fr)_240px] items-start">
            <div className="flex flex-col gap-8 min-w-0">
              <div className="flex items-center gap-8 flex-wrap">
                <h2 className="m-0 text-20 font-semibold text-primary">{topic.name}</h2>
                {topic.ep && <IdChip id={topic.ep} />}
              </div>
              <p className="m-0 text-12 text-secondary">
                {tn(topic.notes.length, '{n} note', '{n} notes')} · {t('the newest {when}, the first {first}', { when: stampOf(newest.updated), first: stampOf(topic.notes[topic.notes.length - 1]!.created) })}
              </p>
              {tasks.length > 0 && (
                <div className="flex flex-col gap-4 min-w-0">
                  <span className={LABEL}>{tn(tasks.length, 'The notes name {n} task', 'The notes name {n} tasks')}</span>
                  <div className="flex flex-wrap gap-4">{tasks.slice(0, 8).map((id) => <IdChip key={id} id={id} />)}
                    {tasks.length > 8 && <span className="text-11 font-mono text-tertiary self-center">{t('+{n} more', { n: tasks.length - 8 })}</span>}</div>
                </div>
              )}
            </div>
            {topic.ep && <MockShot src={SHOT_OF[topic.ep] ?? 'shot:feed'} />}
          </header>
          <Rule aside={<span className="text-10 font-mono text-tertiary">{agoOf(newest.updated)}</span>}>{t('The newest note')}</Rule>
          <article id={newest.id} data-note={newest.id} className="rounded-card border border-border-default bg-surface px-24 py-20 max-sm:px-12 flex flex-col gap-16 min-w-0">
            <NoteHead note={newest} size="mid" />
            <NoteBody note={newest} />
          </article>
          {topic.notes.length > 1 && (
            <>
              <Rule>{t('Earlier in this topic')}</Rule>
              {topic.notes.slice(1).map((n) => <div key={n.id} id={n.id}><OlderNote note={n} read={read === n.id} onRead={() => setRead((r) => (r === n.id ? null : n.id))} /></div>)}
            </>
          )}
          <p className="m-0 text-11 font-mono text-tertiary flex items-center gap-8 flex-wrap">
            {topic.notes.map((n) => <span key={n.id} className="inline-flex items-center gap-4"><KindMark kind={n.kind} />{n.id}</span>)}
          </p>
        </div>
      ) : <EmptyState compact title={t('Pick a topic.')} />}
    </div>
  )
}
