/**
 * The parts the Entry points page is built from: the words for dates and
 * states, the state mark and the up mark, a way in (with its start command,
 * its edit form and remove), the "where it stopped" feed with the
 * operator's own line, and the open tasks with the picker that sets a
 * task's topic.
 */

import { useState, type ReactNode } from 'react'
import { ExternalLink, Pencil, Plus, Send, X } from 'lucide-react'
import { toast } from 'sonner'

import { CopyButton } from '../../../components/CopyButton'
import { ProjectDot } from '../../../components/ProjectDot'
import { LABEL } from '../../../components/ui'
import { fail } from '../../../lib/getJson'
import { locale, t, tn } from '../../../i18n/scope/entrypoints'
import {
  newestFirst, useEntryWrites, useProjectTasks, WAY_KINDS,
  type OpenTask, type PortState, type Stop, type Topic, type TopicState, type Way,
} from './data'

/* ------------------------------------------------------------------ words */

export const STATE_WORD: Record<TopicState, string> = { active: t('active'), paused: t('paused'), dead: t('dead') }

/** "8 Nov" (this year) or "3 Aug 2025". */
export function dayOf(at: string): string {
  const d = new Date(at)
  if (Number.isNaN(d.getTime())) return ''
  const same = d.getFullYear() === new Date().getFullYear()
  return d.toLocaleDateString(locale(), same ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' })
}

export const hmOf = (at: string) => at.slice(11, 16)

/** "today", "yesterday", "6 days ago", "3 months ago". */
export function agoOf(at: string, now = new Date()): string {
  if (!at) return ''
  const days = Math.floor((startOf(now) - startOf(new Date(at))) / 86_400_000)
  if (Number.isNaN(days)) return ''
  if (days <= 0) return t('today')
  if (days === 1) return t('yesterday')
  if (days < 45) return tn(days, '{n} day ago', '{n} days ago')
  return tn(Math.round(days / 30), '{n} month ago', '{n} months ago')
}
const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()

/** "you" for the operator, else the chat's id. */
export const authorWord = (author: string) => (!author || author === 'operator' ? t('you') : author)

/** A folder as shown: without the home part every path starts with (kept in the tooltip and the copy). */
export const shortFolder = (f: string) => f.replace(/^(~|\/home\/[^/]+|\/Users\/[^/]+|[A-Z]:\\Users\\[^\\]+)[/\\]/, '~/')

/* ------------------------------------------------------------------ marks */

export function StateMark({ state }: { state: TopicState }) {
  const tone = state === 'active' ? 'text-brand' : state === 'paused' ? 'text-status-amber' : 'text-tertiary'
  return <span className={`text-10 font-mono uppercase tracking-wide shrink-0 ${tone}`}>{STATE_WORD[state] ?? state}</span>
}

/** Up / down from the port check; nothing for a way that is not on this computer. */
export function UpMark({ port, word = true }: { port?: PortState; word?: boolean }) {
  if (!port || port.up === null) return null
  const up = port.up
  return (
    <span className="inline-flex items-center gap-4 shrink-0" title={up ? t('Up now') : t('Down now')}>
      <span aria-hidden className={`h-6 w-6 rounded-pill ${up ? 'bg-status-green' : 'bg-border-strong'}`} />
      {word ? <span className={`text-10 font-mono ${up ? 'text-status-green' : 'text-tertiary'}`}>{up ? t('up') : t('down')}</span>
        : <span className="sr-only">{up ? t('up') : t('down')}</span>}
    </span>
  )
}

export function ProjectHeading({ code, count }: { code: string; count?: number }) {
  return (
    <div className="flex items-center gap-8 min-w-0">
      <ProjectDot code={code} />
      <span className="text-13 font-semibold text-primary truncate">{code}</span>
      {count != null && <span className="text-11 font-mono text-tertiary tabular">{count}</span>}
      <span className="flex-1 border-t border-border-subtle" />
    </div>
  )
}

/** A mono label on a rule line. */
export function Rule({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center gap-8 min-w-0">
      <span className={LABEL}>{children}</span>
      <span className="flex-1 border-t border-border-subtle" />
      {aside}
    </div>
  )
}

const ICON_BTN = 'h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover shrink-0 disabled:opacity-40'

/* ---------------------------------------------------------------- way in */

const KIND_WORD: Record<string, string> = {
  page: t('page'), site: t('site'), app: t('app'), file: t('file'), folder: t('folder'), script: t('script'), artifact: t('artifact'),
}

/** A start command in a mono box with its copy (the folder goes with it). */
export function CommandLine({ way }: { way: Way }) {
  if (!way.command) return null
  const full = way.folder ? `cd "${way.folder}" && ${way.command}` : way.command
  return (
    <div className="flex items-center gap-6 min-w-0 rounded-input bg-elevated px-8 py-4">
      <code className="text-11 font-mono text-primary truncate flex-1 min-w-0" title={full}>{way.command}</code>
      <CopyButton text={full} title={t('Copy the start command with its folder')} label={t('copy')}
        className="shrink-0 inline-flex items-center gap-4 text-10 font-mono text-tertiary hover:text-brand" />
    </div>
  )
}

/** Where the way in opens: a link for a URL, a path otherwise. */
export function WayTarget({ way }: { way: Way }) {
  if (way.url) {
    return (
      <a href={way.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-4 text-12 font-mono text-brand hover:underline min-w-0">
        <span className="truncate">{way.url.replace(/^https?:\/\//, '')}</span>
        <ExternalLink size={11} className="shrink-0" aria-hidden />
      </a>
    )
  }
  if (way.path) return <span className="text-12 font-mono text-secondary truncate" title={way.path}>{way.path}</span>
  return null
}

/** One way in, whole, with the operator's edit and remove. */
export function WayCard({ topic, way, port }: { topic: Topic; way: Way; port?: PortState }) {
  const [editing, setEditing] = useState(false)
  const writes = useEntryWrites(topic.id)
  if (editing) return <WayForm topic={topic} way={way} onDone={() => setEditing(false)} />
  const down = port?.up === false
  return (
    <div data-testid="ep-way" className="flex flex-col gap-4 min-w-0 rounded-input border border-border-subtle px-10 py-8">
      <div className="flex items-center gap-8 min-w-0">
        <span className="text-13 text-primary font-medium truncate">{way.name}</span>
        <span className="text-10 font-mono text-tertiary shrink-0">{KIND_WORD[way.kind] ?? way.kind}</span>
        <UpMark port={port} />
        {way.port && <span className="ml-auto text-11 font-mono text-tertiary tabular shrink-0">:{way.port}</span>}
        <span className={`${way.port ? '' : 'ml-auto'} flex items-center`}>
          <button type="button" className={ICON_BTN} title={t('Edit the way in')} aria-label={t('Edit the way in')} onClick={() => setEditing(true)}>
            <Pencil size={11} aria-hidden />
          </button>
          <button type="button" className={ICON_BTN} title={t('Remove the way in')} aria-label={t('Remove the way in')} disabled={writes.removeWay.isPending}
            onClick={() => {
              if (!window.confirm(t('Remove the way in «{name}»? Its screenshots stay in the history.', { name: way.name }))) return
              writes.removeWay.mutate(way.id, { onSuccess: () => toast.success(t('Removed the way in.')), onError: fail })
            }}>
            <X size={11} aria-hidden />
          </button>
        </span>
      </div>
      <WayTarget way={way} />
      {(down || !port) && <CommandLine way={way} />}
      {port?.up && way.command && <span className="text-10 font-mono text-tertiary truncate" title={way.command}>{t('started with')} {way.command}</span>}
      {(way.folder || way.note) && (
        <div className="flex items-center gap-8 min-w-0 text-10 font-mono text-tertiary flex-wrap">
          {way.folder && <span className="truncate max-w-full" title={way.folder}>{t('folder')} {shortFolder(way.folder)}</span>}
          {way.note && <span className="truncate max-w-full">{way.note}</span>}
        </div>
      )}
    </div>
  )
}

const FIELD = 'h-24 w-full min-w-0 rounded-input border border-border-default bg-surface px-6 text-12 text-primary font-mono placeholder:text-tertiary focus:outline-none focus:border-brand'

/** Add a way in, or change one: labelled mono fields, as the task window edits. */
export function WayForm({ topic, way, onDone }: { topic: Topic; way?: Way; onDone: () => void }) {
  const writes = useEntryWrites(topic.id)
  const [v, setV] = useState({
    name: way?.name ?? '', kind: way?.kind ?? 'page', url: way?.url ?? '', path: way?.path ?? '',
    command: way?.command ?? '', folder: way?.folder ?? '', port: way?.port ? String(way.port) : '', note: way?.note ?? '',
  })
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV((o) => ({ ...o, [k]: e.target.value }))
  const save = () => {
    const body: Partial<Way> & { port?: number | null } = {
      name: v.name.trim(), kind: v.kind, url: v.url.trim(), path: v.path.trim(), command: v.command.trim(),
      folder: v.folder.trim(), note: v.note.trim(), port: v.port.trim() ? Number(v.port.trim()) : null,
    }
    writes.putWay.mutate({ way: body, id: way?.id }, {
      onSuccess: () => { toast.success(way ? t('Saved the way in.') : t('Added a way in.')); onDone() },
      onError: fail,
    })
  }
  const row = (label: string, el: ReactNode) => (
    <label className="grid grid-cols-[72px_minmax(0,1fr)] items-center gap-6 min-w-0">
      <span className="text-10 font-mono text-tertiary">{label}</span>{el}
    </label>
  )
  return (
    <form data-testid="ep-way-form" className="flex flex-col gap-6 min-w-0 rounded-input border border-brand/40 bg-brand/5 px-10 py-8"
      onSubmit={(e) => { e.preventDefault(); save() }}>
      {row(t('name'), <input className={FIELD} value={v.name} onChange={set('name')} placeholder={t('What you call it')} required />)}
      {row(t('kind'), (
        <select className={FIELD} value={v.kind} onChange={set('kind')}>
          {WAY_KINDS.map((k) => <option key={k} value={k}>{KIND_WORD[k]}</option>)}
        </select>
      ))}
      {row(t('url'), <input className={FIELD} value={v.url} onChange={set('url')} placeholder="http://localhost:8120" />)}
      {row(t('path'), <input className={FIELD} value={v.path} onChange={set('path')} placeholder={t('A file or folder')} />)}
      {row(t('command'), <input className={FIELD} value={v.command} onChange={set('command')} placeholder="npm run dev" />)}
      {row(t('folder'), <input className={FIELD} value={v.folder} onChange={set('folder')} placeholder={t('Where the command runs')} />)}
      {row(t('port'), <input className={FIELD} value={v.port} onChange={set('port')} inputMode="numeric" placeholder="8120" />)}
      {row(t('note'), <input className={FIELD} value={v.note} onChange={set('note')} placeholder={t('One line the reader needs')} />)}
      <div className="flex items-center gap-8 justify-end">
        <button type="button" onClick={onDone} className="h-24 px-8 rounded-input text-12 text-secondary hover:bg-hover">{t('Cancel')}</button>
        <button type="submit" disabled={!v.name.trim() || writes.putWay.isPending}
          className="h-24 px-10 rounded-input bg-brand text-on-brand text-12 font-medium disabled:opacity-40">{way ? t('Save') : t('Add the way in')}</button>
      </div>
    </form>
  )
}

/** The ways in, with the form to add one. */
export function Ways({ topic, ports }: { topic: Topic; ports: Record<string, PortState> }) {
  const [adding, setAdding] = useState(false)
  return (
    <section className="flex flex-col gap-8 min-w-0">
      <Rule aside={!adding && (
        <button type="button" onClick={() => setAdding(true)} className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand shrink-0">
          <Plus size={11} aria-hidden />{t('Add a way in')}
        </button>
      )}>{t('Ways in')}</Rule>
      {!topic.ways.length && !adding && <p className="text-12 text-tertiary">{t('No ways in yet. Add what you open to look at the work: a page, a site, a file.')}</p>}
      <div className="grid gap-8 min-w-0 lg:grid-cols-2">
        {topic.ways.map((w) => <WayCard key={w.id} topic={topic} way={w} port={ports[w.id]} />)}
        {adding && <WayForm topic={topic} onDone={() => setAdding(false)} />}
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------- feed */

/**
 * "Where it stopped": the last five messages, newest first; the rest behind
 * a click; the operator's own line. `onChat` opens an agent's chat in the thread.
 */
export function Feed({ topic, all: allStops, onChat }: { topic: Topic; all?: Stop[]; onChat?: (id: string) => void }) {
  const [all, setAll] = useState(false)
  const writes = useEntryWrites(topic.id)
  const list = newestFirst(allStops ?? topic.stops)
  const shown = all ? list : list.slice(0, 5)
  return (
    <div className="flex flex-col gap-8 min-w-0">
      {!list.length && <p className="text-12 text-tertiary">{t('Nothing written yet. An agent adds a line at #done; you can add one here.')}</p>}
      <ul className="m-0 p-0 list-none flex flex-col gap-8 min-w-0">
        {shown.map((m) => (
          <li key={m.id} className="group flex flex-col gap-2 min-w-0">
            <div className="flex items-center gap-6 text-10 font-mono text-tertiary min-w-0">
              <span className="tabular shrink-0" title={new Date(m.at).toLocaleString(locale())}>{dayOf(m.at)}</span>
              {m.author === 'operator' || !m.author
                ? <span className="text-brand">{t('you')}</span>
                : onChat
                  ? <button type="button" onClick={() => onChat(m.author)} title={t('Open this chat in the thread')} className="truncate hover:text-brand hover:underline underline-offset-2">{m.author}</button>
                  : <span className="truncate">{m.author}</span>}
              {m.task_id && <span className="truncate">{m.task_id}</span>}
              <button type="button" className={`${ICON_BTN} ml-auto opacity-0 group-hover:opacity-100 focus:opacity-100`} title={t('Remove the message')} aria-label={t('Remove the message')}
                onClick={() => writes.removeStop.mutate(m.id, { onSuccess: () => toast.success(t('Removed the message.')), onError: fail })}>
                <X size={10} aria-hidden />
              </button>
            </div>
            <p className="m-0 text-13 text-primary leading-snug break-words">{m.text}</p>
          </li>
        ))}
      </ul>
      {topic.stops_n > 5 && (
        <button type="button" onClick={() => setAll((x) => !x)} className="self-start text-11 font-mono text-tertiary hover:text-brand">
          {all ? t('Show the last {n}', { n: 5 }) : t('All history · {n}', { n: topic.stops_n })}
        </button>
      )}
      <AddStop topic={topic} />
    </div>
  )
}

export function AddStop({ topic }: { topic: Topic }) {
  const [text, setText] = useState('')
  const writes = useEntryWrites(topic.id)
  const send = () => {
    if (!text.trim()) return
    writes.addStop.mutate(text.trim(), { onSuccess: () => { setText(''); toast.success(t('Added to where it stopped.')) }, onError: fail })
  }
  return (
    <form className="flex items-center gap-6 min-w-0" onSubmit={(e) => { e.preventDefault(); send() }}>
      <input value={text} onChange={(e) => setText(e.target.value)} maxLength={1000}
        aria-label={t('Where it stopped, in your words')} placeholder={t('Where it stopped, in your words')}
        className="flex-1 min-w-0 h-24 rounded-input border border-border-default bg-surface px-8 text-12 text-primary placeholder:text-tertiary focus:outline-none focus:border-brand" />
      <button type="submit" disabled={!text.trim() || writes.addStop.isPending} title={t('Add to the feed')} aria-label={t('Add to the feed')}
        className="h-24 w-24 inline-flex items-center justify-center rounded-input text-tertiary hover:text-brand hover:bg-hover disabled:opacity-40 shrink-0">
        <Send size={12} aria-hidden />
      </button>
    </form>
  )
}

/* ------------------------------------------------------------------- tasks */

const COLUMN_WORD: Record<string, string> = { doing: t('doing'), todo: t('to do'), agent: t('agent'), review: t('review'), backlog: t('backlog') }

/** What is next: the topic's open tasks; a task of the project can be added, one taken off. */
export function Tasks({ topic, open }: { topic: Topic; open: OpenTask[] }) {
  const [picking, setPicking] = useState(false)
  const writes = useEntryWrites(topic.id)
  return (
    <div className="flex flex-col gap-6 min-w-0">
      {!open.length && <p className="text-12 text-tertiary">{t('No open tasks.')}</p>}
      <ul className="m-0 p-0 list-none flex flex-col gap-4 min-w-0">
        {open.map((k) => (
          <li key={k.id} className="group flex items-baseline gap-8 min-w-0">
            <span className={`text-10 font-mono shrink-0 ${k.status === 'doing' ? 'text-brand' : 'text-tertiary'}`}>{COLUMN_WORD[k.status] ?? k.status}</span>
            <span className="text-12 text-primary min-w-0 break-words">{k.title}</span>
            <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{k.id}</span>
            <button type="button" className={`${ICON_BTN} opacity-0 group-hover:opacity-100 focus:opacity-100 self-center`}
              title={t('Take the task off this topic')} aria-label={t('Take the task off this topic')}
              onClick={() => writes.setTaskTopic.mutate({ task: k.id, topic: '' }, { onError: fail })}>
              <X size={10} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      {picking ? <TaskPicker topic={topic} taken={open.map((k) => k.id)} onDone={() => setPicking(false)} /> : (
        <button type="button" onClick={() => setPicking(true)} className="self-start inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand">
          <Plus size={11} aria-hidden />{t('Add a task of {project}', { project: topic.project })}
        </button>
      )}
    </div>
  )
}

function TaskPicker({ topic, taken, onDone }: { topic: Topic; taken: string[]; onDone: () => void }) {
  const tasks = useProjectTasks(topic.project, true)
  const writes = useEntryWrites(topic.id)
  const [pick, setPick] = useState('')
  const open = (tasks.data?.tasks ?? []).filter((k) => !taken.includes(k.id) && !/^done/i.test(k.status) && !k.archived_at)
  return (
    <form className="flex items-center gap-6 min-w-0" onSubmit={(e) => {
      e.preventDefault()
      if (!pick) return
      writes.setTaskTopic.mutate({ task: pick, topic: topic.id }, { onSuccess: () => { toast.success(t('Added the task to this topic.')); onDone() }, onError: fail })
    }}>
      <select aria-label={t('A task of the project')} value={pick} onChange={(e) => setPick(e.target.value)} className={`${FIELD} flex-1`}>
        <option value="">{tasks.isLoading ? t('Loading…') : tn(open.length, '{n} open task', '{n} open tasks')}</option>
        {open.map((k) => <option key={k.id} value={k.id}>{k.title} · {k.id}</option>)}
      </select>
      <button type="submit" disabled={!pick} className="h-24 px-8 rounded-input bg-brand text-on-brand text-12 disabled:opacity-40 shrink-0">{t('Add')}</button>
      <button type="button" onClick={onDone} className={ICON_BTN} title={t('Cancel')} aria-label={t('Cancel')}><X size={11} aria-hidden /></button>
    </form>
  )
}
