/**
 * Entry points — the outside of a project: the topics the operator opens
 * and comes back to (tk_51b87348, the design round's variant L "Desk").
 *
 * Left: the topic list (the newest screenshot small, the name, the state or
 * how long ago, by project; a find box over names, ways in, stops and
 * captions). On a phone it is a row to swipe above the card. A click on the
 * small picture opens the topic on its Shots.
 *
 * Right: the topic's card. Its head stays in view: name (the operator edits
 * it), state, Copy to agent (the briefing the server builds), and where the
 * topic was last worked with the resume command. Under it the switch:
 * Briefing (as page or as the exact text), Record, Shots. Then the linked
 * chips, and at the bottom the chats before and after.
 *
 * A two-icon switch over the list lays the topics out as shelves instead:
 * projects as rows of tiles whose picture steps through the screenshots; a
 * tile opens the same card under its row. The layout is kept in this
 * browser; `?layout=shelves` or `?layout=list` in the address wins.
 */

import { Fragment, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DoorOpen, LayoutGrid, PanelLeft, Pencil, Search, X } from 'lucide-react'
import { toast } from 'sonner'

import { CopyButton } from '../../../components/CopyButton'
import { PageHeader } from '../../../components/PageHeader'
import { ProjectDot } from '../../../components/ProjectDot'
import { Segmented } from '../../../components/Segmented'
import { fail } from '../../../lib/getJson'
import type { Guide } from '../../visions/guides'
import { PageGuide } from '../../visions/parts'
import { t, tn } from '../../../i18n/scope/entrypoints'
import {
  byStateThenRecent, displayName, matches, newestFirst, serversByPort, STATES, useDesk, useEntryWrites, usePorts, useTopicContext,
  type PortState, type Topic, type TopicState,
} from './data'
import { agoOf, authorWord, ProjectHeading, Rule, STATE_WORD, StateMark } from './parts'
import { BriefingPage, FaceSwitch, RecordView, ShotPicture, ShotsFace, ShotStepper, type Face } from './faces'
import { LastWorked, Linked, Thread, ThreadSummary } from './context'

const GUIDE: Guide = {
  intro: [
    t('One entry point per topic: what you open to look at the work, and where it stopped.'),
    t('Pick a topic on the left, or lay the topics out as shelves with the switch over the list. Copy to agent gives a new chat the topic with where to resume.'),
  ],
  parts: [
    [t('Ways in'), t('what you open: a page, a site, a file. Each with its start command, folder and port.')],
    [t('Where it stopped'), t('the last five messages from you and the agents. All history opens with a click.')],
    [t('What is next'), t('the topic\'s open tasks.')],
  ],
  steps: [
    t('You type #entrypoint about a topic; the agent writes its record and its ways in.'),
    t('At #done the agent adds a message to where the topic stopped. You can add one by hand.'),
    t('When the page opens it checks each port. A way in that is down shows its start command and folder; copy it into a terminal.'),
    t('Copy to agent copies the topic for a new chat: the folder, the ways in, the last five messages, the open tasks, the chat to resume.'),
  ],
}

const KEY = 'ep-desk-topic'
const FACE_KEY = 'ep-desk-face'
export const LAYOUT_KEY = 'ep-desk-layout'

export type Layout = 'list' | 'shelves'
const isLayout = (v: string | null): v is Layout => v === 'list' || v === 'shelves'

function read(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function keep(key: string, v: string) {
  try { localStorage.setItem(key, v) } catch { /* private mode */ }
}

export function EntryPointsDesk({ project }: { project?: string } = {}) {
  const desk = useDesk(project)
  const topics = useMemo(() => desk.data?.topics ?? [], [desk.data])
  const [params, setParams] = useSearchParams()
  const fromUrl = params.get('layout')
  const [layout, setLayout] = useState<Layout>(() => {
    if (isLayout(fromUrl)) return fromUrl
    const kept = read(LAYOUT_KEY)
    return isLayout(kept) ? kept : 'list'
  })
  useEffect(() => { if (isLayout(fromUrl) && fromUrl !== layout) setLayout(fromUrl) }, [fromUrl, layout])
  useEffect(() => { keep(LAYOUT_KEY, layout) }, [layout])
  useEffect(() => { if (!project) document.title = `${t('Entry points')} — Slightly Parallel` }, [project])
  const pickLayout = (l: Layout) => {
    setLayout(l)
    if (params.has('layout')) {
      const next = new URLSearchParams(params)
      next.set('layout', l)
      setParams(next, { replace: true })
    }
  }
  const fromTopic = params.get('topic')
  const [pick, setPick] = useState<string | null>(() => fromTopic ?? read(KEY))
  const [open, setOpen] = useState<string | null>(null)
  const [face, setFace] = useState<Face>(() => { const f = read(FACE_KEY); return f === 'record' || f === 'shots' ? f : 'briefing' })
  const [query, setQuery] = useState('')
  const ordered = byStateThenRecent(topics)
  const topic = topics.find((tp) => tp.id === pick) ?? ordered[0]
  const found = topics.filter((tp) => matches(tp, query))
  const projects = [...new Set(byStateThenRecent(found).map((tp) => tp.project))]
  const choose = (id: string, f?: Face) => {
    setPick(id); keep(KEY, id)
    if (f) { setFace(f); keep(FACE_KEY, f) }
  }
  const onFace = (f: Face) => { setFace(f); keep(FACE_KEY, f) }

  const head = (
    <>
      <PageHeader variant="lens" icon={DoorOpen} title={t('Entry points')}
        count={desk.data ? tn(topics.length, '{n} topic', '{n} topics') : undefined} />
      {!project && <PageGuide id="entrypoints" guide={GUIDE} examples={0} />}
    </>
  )
  if (desk.isLoading) return <div className="flex flex-col gap-16 min-w-0">{head}<p className="text-13 text-tertiary">{t('Loading…')}</p></div>
  if (desk.error) return <div className="flex flex-col gap-16 min-w-0">{head}<p className="text-13 text-status-red">{String((desk.error as Error).message)}</p></div>
  if (!topics.length) {
    return (
      <div className="flex flex-col gap-16 min-w-0">
        {head}
        <p className="text-13 text-tertiary">{t('No entry points yet. Add #entrypoint to a message about a topic to keep one.')}</p>
      </div>
    )
  }
  const tools = (
    <div className="flex items-center gap-8 min-w-0">
      <LayoutToggle value={layout} onChange={pickLayout} />
      <FindBox value={query} onChange={setQuery} found={found.length} of={topics.length} className={layout === 'list' ? 'flex-1 min-w-0' : 'w-full max-w-[320px] min-w-0'} />
    </div>
  )
  if (layout === 'shelves') {
    return (
      <div className="flex flex-col gap-16 min-w-0">
        {head}
        {tools}
        {!found.length && <p className="text-13 text-tertiary">{t('Nothing matches.')}</p>}
        {projects.map((code) => {
          const list = byStateThenRecent(found.filter((tp) => tp.project === code))
          return (
            <section key={code} aria-label={code} className="flex flex-col gap-10 min-w-0">
              <ProjectHeading code={code} count={list.length} />
              <div data-testid="ep-shelf" className="grid gap-12 min-w-0 grid-cols-1 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))]" style={{ gridAutoFlow: 'dense' }}>
                {list.map((tp) => (
                  <Fragment key={tp.id}>
                    <Tile topic={tp} picked={open === tp.id} onPick={() => {
                      if (open === tp.id) setOpen(null)
                      else { setOpen(tp.id); choose(tp.id) }
                    }} />
                    {open === tp.id && (
                      <div className="min-w-0" style={{ gridColumn: '1 / -1' }}>
                        <Card key={tp.id} topic={tp} face={face} onFace={onFace} onClose={() => setOpen(null)} />
                      </div>
                    )}
                  </Fragment>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-16 min-w-0">
      {head}
      <div className="grid gap-16 min-w-0 md:grid-cols-[240px_minmax(0,1fr)] items-start">
        <nav aria-label={t('Topics')} className="flex flex-col gap-12 min-w-0 md:sticky md:top-0">
          {tools}
          {projects.map((code) => {
            const list = byStateThenRecent(found.filter((tp) => tp.project === code))
            return (
              <div key={code} className="flex flex-col gap-2 min-w-0">
                <ProjectHeading code={code} />
                <div className="flex md:flex-col gap-4 overflow-x-auto md:overflow-visible min-w-0 pt-4 pb-2">
                  {list.map((tp) => <ListItem key={tp.id} topic={tp} current={tp.id === topic?.id} onPick={(f) => choose(tp.id, f)} />)}
                </div>
              </div>
            )
          })}
          {!found.length && <p className="text-12 text-tertiary">{t('Nothing matches.')}</p>}
        </nav>
        {topic && <Card key={topic.id} topic={topic} face={face} onFace={onFace} />}
      </div>
    </div>
  )
}

/** A small find box over names, ways in, stops and captions. */
function FindBox({ value, onChange, found, of, className }: { value: string; onChange: (v: string) => void; found: number; of: number; className: string }) {
  return (
    <label className={`self-center flex items-center gap-6 h-[28px] ${className} rounded-input border border-border-default bg-surface px-8 focus-within:border-brand`}>
      <Search size={13} className="text-tertiary shrink-0" aria-hidden />
      <input value={value} onChange={(e) => onChange(e.target.value)} aria-label={t('Find in topics')} placeholder={t('Find: a word, a port, a path')}
        className="flex-1 min-w-0 bg-transparent text-12 text-primary placeholder:text-tertiary focus:outline-none focus-visible:outline-none" />
      {value && <span className="text-10 font-mono text-tertiary tabular shrink-0">{found} / {of}</span>}
    </label>
  )
}

/** The two-icon switch between the list beside the card and the shelves of tiles. */
function LayoutToggle({ value, onChange }: { value: Layout; onChange: (l: Layout) => void }) {
  const items: Array<[Layout, typeof PanelLeft, string]> = [
    ['list', PanelLeft, t('List beside the card')],
    ['shelves', LayoutGrid, t('Shelves of tiles')],
  ]
  return (
    <div role="group" aria-label={t('Layout')} className="inline-flex items-center gap-2 rounded-pill border border-border-subtle bg-elevated p-2 shrink-0">
      {items.map(([key, Icon, label]) => {
        const on = value === key
        return (
          <button key={key} type="button" aria-pressed={on} aria-label={label} title={label} onClick={() => onChange(key)}
            className={`h-24 w-[28px] inline-flex items-center justify-center rounded-pill transition-colors ${on ? 'bg-brand text-on-brand' : 'text-tertiary hover:text-primary hover:bg-hover'}`}>
            <Icon size={13} aria-hidden />
          </button>
        )
      })}
    </div>
  )
}

/** A tile on a shelf: the picture steps through the series; the last message, the chats, the servers. */
function Tile({ topic, picked, onPick }: { topic: Topic; picked: boolean; onPick: () => void }) {
  const last = newestFirst(topic.stops)[0]
  const local = serversByPort(topic)
  return (
    <div data-testid="ep-tile" className={`rounded-input bg-elevated p-10 flex flex-col gap-8 min-w-0 ${picked ? 'ring-1 ring-brand' : ''} ${topic.state === 'dead' ? 'opacity-60' : ''}`}>
      <ShotStepper topic={topic} onOpen={picked ? undefined : onPick} />
      <button type="button" onClick={onPick} aria-expanded={picked} className="flex flex-col gap-6 text-left min-w-0">
        <span className="flex items-start justify-between gap-8 min-w-0">
          <span className="text-13 font-semibold text-primary leading-snug break-words min-w-0">{displayName(topic)}</span>
          <StateMark state={topic.state} />
        </span>
        {last
          ? (
            <span className="flex flex-col gap-2 min-w-0">
              <span className="text-12 text-secondary leading-snug line-clamp-2">{last.text}</span>
              <span className="text-10 font-mono text-tertiary truncate">{authorWord(last.author)} · {agoOf(last.at)}</span>
            </span>
          )
          : topic.what && <span className="text-12 text-secondary leading-snug line-clamp-2">{topic.what}</span>}
        <span className="text-10 font-mono text-tertiary">
          {tn(topic.chats, '{n} chat', '{n} chats')} · {tn(topic.shots.length, '{n} shot', '{n} shots')}
        </span>
      </button>
      <div className="mt-auto flex items-center gap-8 min-w-0 text-10 font-mono text-tertiary">
        {local.length ? local.map((w) => <span key={w.id} title={`${w.name} :${w.port ?? ''}`}>:{w.port ?? '—'}</span>) : <span>{t('no server')}</span>}
      </div>
    </div>
  )
}

function ListItem({ topic, current, onPick }: { topic: Topic; current: boolean; onPick: (f?: Face) => void }) {
  const newest = topic.shots.at(-1)
  return (
    <div data-testid="ep-list-item" className={`flex items-center gap-8 rounded-input px-6 py-4 shrink-0 md:shrink min-w-0 w-[220px] md:w-auto ${current ? 'bg-brand/10' : 'hover:bg-hover'} ${topic.state === 'dead' ? 'opacity-60' : ''}`}>
      {newest && (
        <button type="button" onClick={() => onPick('shots')} title={t('Open on its screenshots')} aria-label={t('{name}: screenshots', { name: displayName(topic) })}
          className="block w-[44px] shrink-0 rounded-[3px] overflow-hidden border border-border-subtle hover:border-brand" style={{ aspectRatio: '16 / 10' }}>
          <ShotPicture shot={newest} label={displayName(topic)} />
        </button>
      )}
      <button type="button" onClick={() => onPick()} aria-current={current || undefined} className="flex flex-col min-w-0 text-left flex-1">
        <span className={`text-12 truncate ${current ? 'text-primary' : 'text-secondary'} ${topic.name ? '' : 'italic'}`}>{displayName(topic)}</span>
        <span className="text-10 font-mono text-tertiary truncate">
          {topic.state !== 'active' ? <StateMark state={topic.state} /> : agoOf(topic.last_at)}
          {topic.chats > 0 && ` · ${tn(topic.chats, '{n} chat', '{n} chats')}`}
        </span>
      </button>
    </div>
  )
}

/** The topic's name: the operator's words, edited in place. */
function NameEdit({ topic }: { topic: Topic }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(topic.name)
  const writes = useEntryWrites(topic.id)
  if (editing) {
    return (
      <form className="flex items-center gap-6 min-w-0 flex-1" onSubmit={(e) => {
        e.preventDefault()
        if (!value.trim()) return
        writes.setName.mutate(value.trim(), { onSuccess: () => { setEditing(false); toast.success(t('Renamed the topic.')) }, onError: fail })
      }}>
        <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} maxLength={80} aria-label={t('The topic\'s name')} placeholder={t('The topic in a few words')}
          className="flex-1 min-w-0 h-28 rounded-input border border-brand bg-surface px-8 text-16 text-primary focus:outline-none" />
        <button type="submit" className="h-24 px-8 rounded-input bg-brand text-on-brand text-12" disabled={!value.trim()}>{t('Save')}</button>
        <button type="button" onClick={() => { setEditing(false); setValue(topic.name) }} aria-label={t('Cancel')} title={t('Cancel')}
          className="p-4 rounded-input text-tertiary hover:text-primary hover:bg-hover"><X size={13} aria-hidden /></button>
      </form>
    )
  }
  return (
    <span className="inline-flex items-center gap-6 min-w-0">
      <h2 className={`text-20 font-semibold leading-tight min-w-0 break-words ${topic.name ? 'text-primary' : 'text-secondary italic'}`}>{displayName(topic)}</h2>
      {!topic.name && <span className="text-10 font-mono text-status-amber shrink-0">{t('no name yet')}</span>}
      <button type="button" onClick={() => setEditing(true)} aria-label={t('Rename the topic')} title={t('Rename the topic')}
        className="p-4 rounded-input text-tertiary hover:text-primary hover:bg-hover shrink-0"><Pencil size={12} aria-hidden /></button>
    </span>
  )
}

function StatePicker({ topic }: { topic: Topic }) {
  const writes = useEntryWrites(topic.id)
  return (
    <Segmented label={t('State')} shape="pill" height={20} value={topic.state}
      onChange={(s: TopicState) => writes.setState.mutate(s, { onSuccess: () => toast.success(t('The topic is {state} now.', { state: STATE_WORD[s] })), onError: fail })}
      options={STATES.map((s) => [s, STATE_WORD[s]] as const)} />
  )
}

/**
 * The topic's card, the same in both layouts: the head (kept in view), what
 * the topic is, the switch and its face, the linked chips, and at the bottom
 * the chats before and after. In the shelves it closes.
 */
export function Card({ topic, face, onFace, onClose }: { topic: Topic; face: Face; onFace: (f: Face) => void; onClose?: () => void }) {
  const cx = useTopicContext(topic.id)
  const ports = usePorts(topic.id, topic.ways.length > 0)
  const portsBy = useMemo(() => Object.fromEntries((ports.data?.ways ?? []).map((p) => [p.id, p])) as Record<string, PortState>, [ports.data])
  const [as, setAs] = useState<'page' | 'text'>('page')
  const [chat, setChat] = useState<string | null>(null)
  const [jump, setJump] = useState(0)
  useEffect(() => {
    if (jump && chat) document.getElementById(`ep-chat-${chat}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  }, [jump, chat])
  const toChat = (id: string) => { setChat(id); setJump((n) => n + 1) }
  const briefing = cx.data?.briefing ?? ''
  const home = /^Start in: `cd "(.*)"`$/m.exec(briefing)?.[1] ?? topic.home
  const checked = Object.values(portsBy).filter((p) => p.up !== null)
  const up = checked.filter((p) => p.up).length
  return (
    <article aria-label={displayName(topic)} data-testid="ep-card" className={`rounded-card border bg-surface min-w-0 ${onClose ? 'border-brand/40' : 'border-border-subtle'}`}>
      <header data-testid="ep-card-head" className="sticky top-0 z-10 flex flex-col gap-6 px-16 py-10 border-b border-border-subtle bg-surface rounded-t-card min-w-0">
        <div className="flex items-center gap-8 flex-wrap min-w-0">
          <ProjectDot code={topic.project} />
          <NameEdit topic={topic} />
          <span className="ml-auto flex items-center gap-8 flex-wrap">
            <StatePicker topic={topic} />
            <CopyButton text={() => briefing} title={t('Copy the briefing for a new agent')}
              className="inline-flex items-center justify-center gap-6 h-32 px-12 rounded-input bg-brand text-on-brand border border-brand hover:bg-brand-hover text-13 font-medium whitespace-nowrap shrink-0 disabled:opacity-40"
              size={13} label={t('Copy to agent')} copiedLabel={t('Copied')}
              onCopied={() => toast.success(t('Copied the briefing for {name}.', { name: displayName(topic) }))} />
            {onClose && (
              <button type="button" onClick={onClose} aria-label={t('Close')} title={t('Close')} className="p-4 rounded-input text-tertiary hover:text-primary hover:bg-hover">
                <X size={14} aria-hidden />
              </button>
            )}
          </span>
        </div>
        <LastWorked cx={cx.data} home={home} />
      </header>

      <div data-testid="ep-card-what" className="flex flex-col gap-4 px-16 pt-12 min-w-0">
        <span className="text-11 font-mono text-tertiary">
          {topic.project}{topic.no_project ? ` · ${t('no project')}` : ''} · {topic.id}
          {checked.length > 0 && ` · ${tn(up, '{n} server up', '{n} servers up')}`}
        </span>
        {topic.what
          ? <p className="m-0 text-14 text-primary leading-relaxed">{topic.what}</p>
          : <p className="m-0 text-13 text-tertiary">{t('No record written yet.')}</p>}
      </div>

      <div data-testid="ep-card-faces" className="min-w-0 border-b border-border-subtle">
        <div className="flex items-center gap-8 flex-wrap px-16 pt-12 min-w-0">
          <FaceSwitch value={face} onChange={onFace} />
          {face === 'briefing' && (
            <span className="ml-auto">
              <Segmented label={t('Show')} shape="pill" value={as} onChange={setAs} options={[['page', t('as page')], ['text', t('as text')]]} />
            </span>
          )}
        </div>
        <div className="px-16 py-12 min-w-0">
          {face === 'briefing' && (as === 'text'
            ? <pre data-testid="ep-briefing-text" className="m-0 text-12 font-mono text-primary whitespace-pre-wrap break-words leading-relaxed">{briefing || t('Loading…')}</pre>
            : <BriefingPage topic={topic} cx={cx.data} ports={portsBy} onChat={toChat} />)}
          {face === 'record' && <RecordView topic={topic} />}
          {face === 'shots' && <ShotsFace topic={topic} onChat={toChat} />}
        </div>
      </div>

      <div data-testid="ep-card-linked" className="flex flex-col gap-10 px-16 py-12 border-b border-border-subtle min-w-0">
        {cx.error ? <p className="text-12 text-status-red">{String((cx.error as Error).message)}</p> : <Linked cx={cx.data} />}
      </div>

      <section aria-label={t('Context')} data-testid="ep-card-chats" className="flex flex-col gap-10 px-16 py-12 min-w-0">
        <Rule>{t('Chats, before and after')}</Rule>
        <ThreadSummary cx={cx.data} />
        <Thread cx={cx.data} home={home} open={chat} onOpen={setChat} />
      </section>
    </article>
  )
}

