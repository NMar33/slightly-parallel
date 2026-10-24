import { useState, type ReactNode } from 'react'
import { LoadingSkeleton } from '../../components/states'
import { TerminalSquare } from 'lucide-react'
import { showTerminal, terminalOfAgent, useTerminalActions, useTerminals } from '../../lib/terminal'
import { StateDot } from '../terminal/parts'
import { IconButton } from '../../components/primitives'
import { useQuery } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'

import { ChatReader } from '../agents/dossier'
import type { ProfileSession } from '../agents/profile'
import { LensDrawer } from '../../lenses/LensDrawer'
import { LENSES } from '../../lenses/config'
import { CopyButton } from '../../components/CopyButton'
import { useCopy } from '../../lib/useCopy'
import { agentLabel } from '../../utils/agentLabel'
import { formatStamp } from '../../utils/dateUtils'
import { resumeCommand } from './AgentDrill'
import { Modal } from '../../components/Modal'
import { getJson, refused } from '../../lib/getJson'
import { persistPref, readPref } from '../../lib/uiPrefs'
import { Segmented } from '../../components/Segmented'
import { Markdown } from '../../components/Markdown'
import { LABEL } from '../promptlib/taskstyle'
import { t } from '../../i18n/scope/project'

/**
 * Chat mentions of a task — one component for every place that draws them.
 *
 * A mention is a captured turn that named a task id: the operator handing
 * the task to an agent (◆), or the agent answering about it (◇). The row
 * says who in words, not only the raw id, carries both to the clipboard,
 * and offers the command that picks that chat back up in a terminal.
 * Clicking it opens the chat on the very turn that named the task.
 *
 * The task window, the task timeline and the card chip all read from here,
 * so the way a mention reads cannot drift apart between them again.
 */

/** What the server knows about the agent behind a mention. */
export type MentionAgent = {
  agent_id: string
  agent_name?: string | null
  chat_title?: string | null
  created_date?: string | null
  /** Origin the capture hook recorded — enough to resume the chat. */
  tool?: string | null
  cwd?: string | null
  session_ref?: string | null
  /** The operator's group for this lane, when it has one. */
  agent_group?: string | null
}

export type Mention = {
  at: string
  role: 'user' | 'agent'
  agent_id: string
  session_id: string
  turn: number
  excerpt?: string
  project?: string
  /** Absent on older payloads; the label then falls back to the id. */
  agent?: MentionAgent | null
}

/** One turn that named the task, whole: the task window's full view. */
export type MentionTurn = {
  at: string
  agent_id: string
  session_id: string
  turn: number
  project?: string
  /** Which sides of the turn named the task; empty on a turn a switch added. */
  roles: Array<'user' | 'agent'>
  /** Why the turn is in the thread: it names the task, it is inside the
   *  stretch a #done closed, or it comes before the next task named. */
  why?: 'mention' | 'done' | 'next' 
  /** The operator's message and the agent's reply, whole. */
  said: string
  reply: string
  agent?: MentionAgent | null
}

/** The agent's name in words. Falls back to the tool and the id. */
export function mentionLabel(m: { agent_id: string; agent?: MentionAgent | null }): string {
  return agentLabel(m.agent ?? { agent_id: m.agent_id })
}

/** "Name · id" for a tooltip; the id alone when the name is the id. */
export function mentionWho(m: { agent_id: string; agent?: MentionAgent | null }): string {
  const label = mentionLabel(m)
  return label === m.agent_id ? m.agent_id : `${label} · ${m.agent_id}`
}

/** The command that resumes this agent's chat; '' when it cannot be built. */
export function mentionResume(agent?: MentionAgent | null): string {
  if (!agent) return ''
  return resumeCommand(agent.tool ?? '', agent.cwd ?? '', agent.session_ref ?? '')
}

function mentionTime(at: string): string {
  return formatStamp(at)
}

/** A word that copies itself. */
function CopyWord({ text, title, className = '' }: { text: string; title: string; className?: string }) {
  const { copied, copy } = useCopy()
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={(e) => { e.stopPropagation(); void copy(text) }}
      className={`inline-flex items-baseline gap-3 min-w-0 rounded-input px-3 -mx-3 hover:bg-hover hover:text-primary ${className}`}
    >
      <span className="truncate">{text}</span>
      {copied && <Check size={10} className="text-status-green shrink-0" aria-hidden />}
    </button>
  )
}

/**
 * Resume: the agent comes back in a Slightly Parallel terminal, in its own folder —
 * or its open terminal comes forward. The small copy button beside it
 * keeps the command for a terminal of your own. Absent when the chat
 * cannot be resumed.
 */
export function ResumeButton({ agent, className = '' }: { agent?: MentionAgent | null; className?: string }) {
  const cmd = mentionResume(agent)
  const act = useTerminalActions()
  const list = useTerminals().data
  if (!cmd || !agent) return null
  const live = terminalOfAgent(list?.sessions, agent.agent_id)
  return (
    <span className={`shrink-0 inline-flex items-center h-20 rounded-input border border-border-subtle overflow-hidden text-10 font-mono ${className}`}>
      <button type="button" onClick={() => live ? showTerminal(live.id) : act.open({ kind: 'resume', agent_id: agent.agent_id })}
        title={live ? t('Show its terminal ({state})', { state: live.state === 'waiting' ? t('waiting for you') : live.state }) : t('Resume in a terminal: {cmd}', { cmd })}
        className="inline-flex items-center gap-3 h-full px-6 text-tertiary hover:text-primary hover:bg-hover">
        {live ? <><StateDot state={live.state} size={6} /> {t('terminal')}</> : <><TerminalSquare size={10} aria-hidden /> {t('Resume')}</>}
      </button>
      <CopyButton text={cmd} title={cmd} ariaLabel={t('Copy the resume command')} size={10}
        className="inline-flex items-center h-full px-4 border-l border-border-subtle text-tertiary hover:text-primary hover:bg-hover" />
    </span>
  )
}

export function MentionRow({ m, onOpen }: { m: Mention; onOpen: () => void }) {
  const user = m.role === 'user'
  const label = mentionLabel(m)
  return (
    <div className="flex items-baseline gap-8 px-6 py-3 rounded-input text-11 font-mono min-w-0 hover:bg-hover">
      <span className={`shrink-0 ${user ? 'text-status-amber' : 'text-brand'}`}>
        {user ? t('◆ sent to') : t('◇ reply from')}
      </span>
      <CopyWord text={label} title={`Copy ${label}`} className="text-secondary shrink-0 max-w-[160px]" />
      {label !== m.agent_id && (
        <CopyWord text={m.agent_id} title={`Copy ${m.agent_id}`} className="text-tertiary shrink-0" />
      )}
      <button
        type="button"
        onClick={onOpen}
        title={t('Open this chat')}
        className="flex-1 min-w-0 text-left flex items-baseline gap-8"
      >
        <span className="text-tertiary shrink-0">{mentionTime(m.at)} {t('· turn')} {m.turn}</span>
        {m.excerpt && <span className="text-tertiary truncate">“{m.excerpt}”</span>}
      </button>
      <ResumeButton agent={m.agent} />
    </div>
  )
}

/**
 * The chat behind a mention, opened on the turn that named the task.
 *
 * The grown-up reader from the agent page — markdown, find, both orders,
 * a size — with the agent and the way to resume it in the header.
 */
export function MentionChat({
  mention, onClose, onOpenTask,
}: {
  mention: Mention
  onClose: () => void
  onOpenTask?: (id: string) => void
}) {
  const [lens, setLens] = useState<{ lens: string; id: string } | null>(null)
  const { data, isLoading, isError } = useQuery({
    queryKey: ['mention-session', mention.session_id],
    queryFn: ({ signal }) => getJson<{ metadata: ProfileSession }>(`/api/sessions/${encodeURIComponent(mention.session_id)}`, signal),
    enabled: !!mention.session_id,
    staleTime: 60_000,
  })
  const session = data?.metadata
  const label = mentionLabel(mention)
  const cmd = mentionResume(mention.agent)
  const folder = mention.agent?.cwd ?? ''

  return (
    <Modal label={t('Chat')} onClose={onClose} width="w-[900px]" padding="p-0" top>
      <aside className="h-[80vh] min-h-0 outline-none flex flex-col">
        <div className="flex items-center gap-8 px-16 py-10 border-b border-border-subtle">
          <span className="text-11 font-mono text-tertiary truncate">{mention.session_id}</span>
          <IconButton label={t('Close the chat')} onClick={onClose} className="ml-auto">
            <X size={14} aria-hidden />
          </IconButton>
        </div>
        <div className="flex-1 min-h-0 p-12">
          {isLoading && <LoadingSkeleton variant="text" count={3} label={t('Loading')} />}
          {isError && <div className="text-12 text-tertiary">{t('This chat could not be read.')}</div>}
          {session && (
            <ChatReader
              sessions={[session]}
              onOpenLens={(l, id) => setLens({ lens: l, id })}
              onOpenTask={onOpenTask}
              markTurn={mention.turn}
              fill
              extra={
                <span className="inline-flex items-center gap-6 text-10 font-mono shrink-0 min-w-0">
                  <span className="text-secondary truncate max-w-[160px]" title={mention.agent_id}>{label}</span>
                  {folder && (
                    <span className="text-tertiary truncate max-w-[220px]" title={folder}>{folder}</span>
                  )}
                  {cmd
                    ? <ResumeButton agent={mention.agent} />
                    : <span className="text-tertiary">{t('No chat id recorded.')}</span>}
                </span>
              }
            />
          )}
        </div>
      </aside>
      {lens && LENSES[lens.lens] && (
        <LensDrawer lens={LENSES[lens.lens]!} id={lens.id} presentation="reading" onClose={() => setLens(null)} />
      )}
    </Modal>
  )
}

/** Past this many characters a message shows its start and opens on a click: a paste of hundreds of lines would make the section a long scroll. */
const FOLD_AT = 1500

/** A message whole, or its start with a way to open the rest. */
function Message({ text }: { text: string }) {
  const [whole, setWhole] = useState(false)
  const long = text.length > FOLD_AT
  const shown = long && !whole ? text.slice(0, FOLD_AT).trimEnd() + '…' : text
  return (
    <div className="min-w-0 text-13">
      <Markdown text={shown} />
      {long && (
        <button type="button" onClick={() => setWhole(!whole)}
          className="mt-2 text-11 font-mono text-tertiary rounded-input px-4 -mx-4 hover:bg-hover hover:text-primary">
          {whole ? t('less') : t('whole message ({n} characters)', { n: text.length.toLocaleString() })}
        </button>
      )}
    </div>
  )
}

/**
 * One turn in the full view: who and when on a few lines, the operator's
 * message (a very long one folded to its start), and the agent's reply
 * folded under it.
 */
function MentionTurnCard({ m, onOpen }: { m: MentionTurn; onOpen: () => void }) {
  const label = mentionLabel(m)
  const chat = m.agent?.chat_title ?? ''
  const where = [
    m.roles.includes('user') ? t('◆ in the message') : '',
    m.roles.includes('agent') ? t('◇ in the reply') : '',
  ].filter(Boolean).join(' · ') || whyWords(m.why)
  return (
    <article className="rounded-input border border-border-subtle bg-base px-12 py-8 flex flex-col gap-6 min-w-0">
      <header className="flex flex-col gap-2 text-11 font-mono min-w-0">
        <div className="flex items-baseline gap-8 min-w-0">
          <CopyWord text={label} title={`Copy ${label}`} className="text-secondary shrink-0 max-w-[200px]" />
          {label !== m.agent_id && (
            <CopyWord text={m.agent_id} title={`Copy ${m.agent_id}`} className="text-tertiary shrink-0" />
          )}
          <span className="ml-auto shrink-0"><ResumeButton agent={m.agent} /></span>
        </div>
        <div className="flex items-baseline gap-8 min-w-0 text-tertiary">
          <span className="shrink-0">{mentionTime(m.at)} {t('· turn')} {m.turn}</span>
          {chat && <span className="truncate" title={chat}>· {chat}</span>}
          <button type="button" onClick={onOpen} disabled={!m.session_id}
            title={m.session_id ? t('Open this chat at this turn') : t('This turn is in no recorded session')}
            className="ml-auto shrink-0 rounded-input px-4 hover:bg-hover hover:text-primary disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-tertiary">
            {t('open in chat')}
          </button>
        </div>
        {where && <div className="text-tertiary">{where}</div>}
      </header>
      {m.said ? <Message text={m.said} /> : <p className="text-13 text-tertiary">{t('(no message)')}</p>}
      {m.reply && (
        <details className="min-w-0">
          <summary className="text-11 text-tertiary cursor-pointer select-none hover:text-secondary">
            {t('agent reply ({n} characters)', { n: m.reply.length.toLocaleString() })}
          </summary>
          <div className="mt-4 min-w-0 text-13"><Markdown text={m.reply} /></div>
        </details>
      )}
    </article>
  )
}

const VIEW_KEY = 'sp-task-chat-view'
const ORDER_KEY = 'sp-task-chat-order'
const DONE_KEY = 'sp-task-chat-to-done'
const NEXT_KEY = 'sp-task-chat-to-next'

/** The answer of the mentions read with full=1: the mention rows and the task's thread. */
type Thread = {
  total?: number
  mentions?: Mention[]
  turns?: MentionTurn[]
  /** How many turns each switch adds, and whether a #done closed the task. */
  done_turns?: number
  next_turns?: number
  has_done?: boolean
}

/** What a turn the switches added says about itself. */
function whyWords(why: MentionTurn['why']): string {
  return why === 'done' ? t('in the stretch up to #done') : why === 'next' ? t('before the next task') : ''
}

/** A collapsed line for a turn that does not name the task: its place and its start. */
function ThreadLine({ m, onOpen }: { m: MentionTurn; onOpen: () => void }) {
  const head = m.said.replace(/\s+/g, ' ').trim()
  return (
    <button type="button" onClick={onOpen} disabled={!m.session_id}
      title={m.session_id ? t('Open this chat at this turn') : t('This turn is in no recorded session')}
      className="w-full flex items-baseline gap-8 px-6 py-3 rounded-input text-11 font-mono min-w-0 text-left hover:bg-hover disabled:hover:bg-transparent">
      <span className="shrink-0 text-tertiary">·</span>
      <span className="shrink-0 text-tertiary">{mentionTime(m.at)} {t('· turn')} {m.turn}</span>
      <span className="shrink-0 text-tertiary/70">{whyWords(m.why)}</span>
      {head && <span className="text-tertiary truncate">“{head}”</span>}
    </button>
  )
}
type View = 'collapsed' | 'full'
type Order = 'oldest' | 'newest'

/** A remembered choice of one of a few words; the first is the default. */
function usePick<T extends string>(key: string, choices: readonly T[]): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const raw = readPref(key) as T | null
    return raw && choices.includes(raw) ? raw : choices[0]!
  })
  return [value, (v: T) => {
    setValue(v)
    try { persistPref(key, v) } catch { /* the choice still holds for this window */ }
  }]
}

/** Earliest first or latest first, by the turn's time. */
function ordered<T extends { at: string }>(items: T[], order: Order): T[] {
  const sorted = [...items].sort((a, b) => a.at.localeCompare(b.at))
  return order === 'oldest' ? sorted : sorted.reverse()
}

/**
 * Every captured turn that named this task. Collapsed: a line each, opened
 * one at a time. Full: each turn once, whole, read top to bottom without a
 * click. Both remember the choice, and the order — oldest first by default,
 * so the task reads as it happened.
 */
export function MentionsPanel({ taskId }: { taskId: string }) {
  const [open, setOpen] = useState<Mention | null>(null)
  const [view, setView] = usePick<View>(VIEW_KEY, ['collapsed', 'full'])
  const [order, setOrder] = usePick<Order>(ORDER_KEY, ['oldest', 'newest'])
  const [toDone, setToDone] = usePick<'yes' | 'no'>(DONE_KEY, ['yes', 'no'])
  const [toNext, setToNext] = usePick<'no' | 'yes'>(NEXT_KEY, ['no', 'yes'])
  // A refused read (the task is gone) is no mentions; a failed one says so.
  const read = useQuery({
    queryKey: ['tasks', taskId, 'mentions', 'full'],
    queryFn: ({ signal }) =>
      getJson<Thread>(`/api/tasks/${encodeURIComponent(taskId)}/mentions?full=1`, signal)
        .catch(refused({ mentions: [], turns: [] } as Thread)),
  })
  if (read.isLoading) return null
  const rows = Array.isArray(read.data?.mentions) ? read.data.mentions : []
  const all = Array.isArray(read.data?.turns) ? read.data.turns : []
  const doneN = read.data?.has_done ? read.data?.done_turns ?? 0 : 0
  const nextN = read.data?.next_turns ?? 0
  const shown = (m: MentionTurn) =>
    m.why === 'done' ? doneN > 0 && toDone === 'yes' : m.why === 'next' ? nextN > 0 && toNext === 'yes' : true
  const turns = all.filter(shown)
  const extra = turns.filter((m) => m.why !== 'mention')
  // A turn in no recorded session has no chat to open.
  const openTurn = (m: MentionTurn) => { if (m.session_id) setOpen({ ...m, role: m.roles[0] ?? 'user' }) }
  const any = rows.length > 0 || all.length > 0
  const said = read.isError ? t('The mentions could not be read.')
    : !any ? t('No chats mention this task.')
    : [`${rows.length} mention${rows.length === 1 ? '' : 's'}`,
       extra.length ? t('{n} more turns of its work', { n: extra.length }) : ''].filter(Boolean).join(' · ')
  // Collapsed: the mention lines as before, and a line for each turn a switch adds.
  const lines: Array<{ at: string; key: string; node: ReactNode }> = [
    ...rows.map((m, i) => ({ at: m.at, key: `m-${m.session_id}-${m.turn}-${i}`,
      node: <MentionRow m={m} onOpen={() => setOpen(m)} /> })),
    ...extra.map((m) => ({ at: m.at, key: `x-${m.agent_id}-${m.turn}`,
      node: <ThreadLine m={m} onOpen={() => openTurn(m)} /> })),
  ]
  return (
    <details className="border-t border-border-subtle pt-8" open={any && (rows.length <= 3 || view === 'full')}>
      <summary className={`${LABEL} cursor-pointer hover:text-brand`}>
        {t('Chat')} <span className="text-tertiary/70">— {said}</span>
      </summary>
      {any && (
        <div className="mt-6 flex items-center gap-x-12 gap-y-6 flex-wrap">
          <Segmented<View> label={t('How the chat reads')} shape="pill" value={view} onChange={setView}
            options={[['collapsed', t('collapsed')], ['full', t('full')]]} />
          <Segmented<Order> label={t('Order')} shape="pill" value={order} onChange={setOrder}
            options={[['oldest', t('oldest first')], ['newest', t('newest first')]]} />
          {doneN > 0 && (
            <label className="inline-flex items-center gap-4 text-11 text-secondary cursor-pointer"
              title={t('Every turn from the start of the task to its #done, also those that do not name it')}>
              <input type="checkbox" checked={toDone === 'yes'} onChange={() => setToDone(toDone === 'yes' ? 'no' : 'yes')}
                className="accent-[var(--brand)]" />
              {t('up to #done ({n} turns)', { n: doneN })}
            </label>
          )}
          {nextN > 0 && (
            <label className="inline-flex items-center gap-4 text-11 text-secondary cursor-pointer"
              title={t('The turns after a mention no #done closed, until you name another task in that chat')}>
              <input type="checkbox" checked={toNext === 'yes'} onChange={() => setToNext(toNext === 'yes' ? 'no' : 'yes')}
                className="accent-[var(--brand)]" />
              {t('up to the next task ({n} turns)', { n: nextN })}
            </label>
          )}
        </div>
      )}
      {any && view === 'collapsed' && (
        <div className="mt-6 flex flex-col gap-2 max-h-[200px] overflow-y-auto">
          {ordered(lines, order).map((l) => <div key={l.key}>{l.node}</div>)}
        </div>
      )}
      {any && view === 'full' && (
        <div className="mt-6 flex flex-col gap-8">
          {ordered(turns, order).map((m) => (
            <MentionTurnCard key={`${m.agent_id}-${m.turn}`} m={m} onOpen={() => openTurn(m)} />
          ))}
        </div>
      )}
      {!any && !read.isError && (
        <p className="mt-4 text-11 text-tertiary">{t('Copy the task with copy on and paste it to an agent. The task id goes with the text, and the chat appears here.')}</p>
      )}
      {open && <MentionChat mention={open} onClose={() => setOpen(null)} />}
    </details>
  )
}

/** Shared by hosts that render their own trigger and just need the chat. */
export function useMentionChat(): {
  open: (m: Mention) => void
  chat: ReactNode
} {
  const [mention, setMention] = useState<Mention | null>(null)
  return {
    open: (m: Mention) => setMention(m),
    chat: mention ? <MentionChat mention={mention} onClose={() => setMention(null)} /> : null,
  }
}
