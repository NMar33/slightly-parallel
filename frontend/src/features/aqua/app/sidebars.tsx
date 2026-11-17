/**
 * SP Aqua's two sidebars.
 *
 * Left: the workspaces (a project each, and the operator's groups), the
 * chats of the open one, sleep and wake per chat and per workspace, the
 * servers apart, and "new chat / new server".
 *
 * Right: the chat in front, read from what Slightly Parallel captured —
 * Messages (with pin, carry and fork-later on each, the marks API),
 * Pins (its pinned and carried messages, the first pin on top), Branches
 * (the tasks it handed, the chats linked to it, the runs it started, its
 * fork-later queue) and Stats (terminals by state, per workspace).
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Bot, ChevronDown, ChevronRight, GitBranch, GitFork, Link2, Menu, MessageSquare, Moon, Pin, Play, Plus, Server, Sun, X } from 'lucide-react'

import { getJson } from '../../../lib/getJson'
import { useMsgMarkActions, useMsgMarks, type MsgMark } from '../../../lib/pins'
import { MsgMarkButtons } from '../../../components/MsgMarkButtons'
import { MarkGlyph } from '../../chats/ChatPins'
import { useSessionTurns, type SessionTurn } from '../../agents/sessionTurns'
import { isAsleep, isLive, roleOf, shownOf, type AquaSession, type Shown, type Workspace } from './model'
import { Dot, SHOWN_WORD, Swatch } from './parts'
import { t, tn } from '../../../i18n/scope/aqua'

/* ================================================================ left */

export function LeftSidebar({ workspaces, ws, active, canSleep, onChat, onWs, onSleep, onSleepWs, onNew, onGroupMenu }: {
  workspaces: Workspace[]; ws: string; active: string; canSleep: boolean
  onChat: (id: string) => void; onWs: (id: string) => void
  onSleep: (s: AquaSession, asleep: boolean) => void; onSleepWs: (w: Workspace, asleep: boolean) => void
  onNew: (role: 'chat' | 'server') => void; onGroupMenu: (w: Workspace) => void
}) {
  const [others, setOthers] = useState(false)
  const live = workspaces.filter(isLive)
  const quiet = workspaces.filter((w) => !isLive(w) && w.kind === 'project')
  const open = workspaces.find((w) => w.id === ws)
  const servers = (open?.sessions ?? []).filter((s) => roleOf(s) === 'server')
  const chatRow = (s: AquaSession) => (
    <div key={s.id} className="group flex items-center">
      <button type="button" data-nodrag className="aq-row h-[24px] pl-20 pr-6 min-w-0 flex-1" aria-current={s.id === active} onClick={() => onChat(s.id)}
        style={{ opacity: isAsleep(s) ? 0.65 : 1 }}>
        <Dot s={s} /><span className="truncate flex-1">{s.label}</span>
      </button>
      {canSleep && s.state !== 'ended' && (
        <button type="button" data-nodrag className="aq-btn icon shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100"
          aria-label={isAsleep(s) ? t('Wake {name}', { name: s.label }) : t('Put {name} to sleep', { name: s.label })}
          title={isAsleep(s) ? t('Wake') : t('Sleep: the agent stops, the chat stays')} onClick={() => onSleep(s, !isAsleep(s))}>
          {isAsleep(s) ? <Sun size={11} /> : <Moon size={11} />}
        </button>
      )}
    </div>
  )
  return (
    <nav className="h-full flex flex-col min-h-0 text-12" aria-label={t('Workspaces')}>
      <div className="flex-1 min-h-0 aq-scroll p-6">
        {live.map((w) => {
          const here = w.id === ws
          const chats = w.sessions.filter((s) => roleOf(s) !== 'server')
          const asleep = chats.length > 0 && chats.every(isAsleep)
          const waiting = w.sessions.filter((s) => shownOf(s) === 'waiting').length
          return (
            <section key={w.id} className="mb-4">
              <div className="group flex items-center">
                <button type="button" data-nodrag className="aq-row h-[26px] px-6 min-w-0 flex-1" aria-current={here} aria-expanded={here} onClick={() => onWs(w.id)}>
                  <Swatch w={w} />
                  <b className="truncate flex-1" style={{ color: 'var(--text-primary)' }}>{w.name}</b>
                  {w.kind === 'group' && <span className="aq-chip">{t('group')}</span>}
                  {waiting > 0 && <span className="w-[6px] h-[6px] rounded-full shrink-0" style={{ background: 'var(--status-amber)' }} aria-label={t('your turn')} />}
                  <span className="font-mono text-10 aq-ink3">{chats.length}</span>
                </button>
                {w.kind === 'group' && (
                  <button type="button" data-nodrag className="aq-btn icon shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100" aria-label={`${t('Group')} ${w.name}`} onClick={() => onGroupMenu(w)}><Menu size={11} /></button>
                )}
                {canSleep && chats.length > 0 && (
                  <button type="button" data-nodrag className="aq-btn icon shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100"
                    aria-label={asleep ? t('Wake the workspace') : t('Sleep the workspace')} title={asleep ? t('Wake the workspace') : t('Sleep the workspace')} onClick={() => onSleepWs(w, !asleep)}>
                    {asleep ? <Sun size={11} /> : <Moon size={11} />}
                  </button>
                )}
              </div>
              {here && chats.map(chatRow)}
            </section>
          )
        })}
        {quiet.length > 0 && (
          <section className="mt-6">
            <button type="button" data-nodrag className="aq-row h-[24px] px-6" aria-expanded={others} onClick={() => setOthers(!others)}>
              {others ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
              <span className="aq-label">{tn(quiet.length, '{n} project without terminals', '{n} projects without terminals')}</span>
            </button>
            {others && quiet.map((w) => (
              <button key={w.id} type="button" data-nodrag className="aq-row h-[24px] pl-20 pr-6" onClick={() => onWs(w.id)}>
                <Swatch w={w} /><span className="truncate flex-1">{w.name}</span>
              </button>
            ))}
          </section>
        )}
      </div>
      <div className="p-8 flex flex-col gap-2" style={{ borderTop: '1px solid var(--border-default)' }}>
        <span className="aq-label pb-2">{t('servers')}{open ? ` · ${open.name}` : ''}</span>
        {servers.map((s) => (
          <button key={s.id} type="button" data-nodrag className="aq-row h-[24px] px-6" aria-current={s.id === active} onClick={() => onChat(s.id)}>
            <Dot s={s} /><span className="truncate flex-1">{s.label}</span>
            <span className="text-10 aq-ink3">{s.project}</span>
          </button>
        ))}
        {!servers.length && <span className="text-11 aq-ink3 px-6">{t('none')}</span>}
        <div className="flex gap-4 pt-6">
          <button type="button" data-nodrag className="aq-btn line" onClick={() => onNew('chat')}><Plus size={12} />{t('New chat')}</button>
          <button type="button" data-nodrag className="aq-btn line" onClick={() => onNew('server')}><Server size={12} />{t('New server')}</button>
        </div>
      </div>
    </nav>
  )
}

/* =============================================================== right */

export type RightTab = 'messages' | 'pins' | 'branches' | 'stats'

export function RightSidebar({ s, tab, setTab, workspaces, onChat, onResume, onFork }: {
  s: AquaSession | undefined; tab: RightTab; setTab: (t: RightTab) => void; workspaces: Workspace[]
  onChat: (id: string) => void
  /** Bring a chat back in a terminal (a link to a chat with no terminal open). */
  onResume: (agentId: string) => void
  /** Start a fork-later message in a new terminal with its command. */
  onFork: (m: MsgMark) => void
}) {
  const TABS: Array<[RightTab, string, typeof Pin]> = [['messages', t('Messages'), MessageSquare], ['pins', t('Pins'), Pin], ['branches', t('Branches'), GitBranch], ['stats', t('Stats'), Activity]]
  const agent = s?.agent_id ?? ''
  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="h-[30px] shrink-0 flex items-center gap-1 px-4" role="tablist" aria-label={t('Inspector')} style={{ borderBottom: '1px solid var(--border-default)' }}>
        {TABS.map(([k, w, Icon]) => (
          <button key={k} type="button" data-nodrag role="tab" aria-selected={tab === k} aria-label={w} title={w} className="aq-btn" data-on={tab === k} onClick={() => setTab(k)}>
            <Icon size={12} />{tab === k && w}</button>
        ))}
      </div>
      <div className="flex-1 min-h-0 flex flex-col" role="tabpanel">
        {tab === 'stats'
          ? <Stats workspaces={workspaces} />
          : !agent
            ? <p className="m-0 p-12 text-12 aq-ink3">{s ? t('This terminal has no chat that Slightly Parallel recorded: no messages, pins or branches.') : t('No terminal is open.')}</p>
            : tab === 'messages' ? <Messages agentId={agent} project={s!.project} />
              : tab === 'pins' ? <Pins agentId={agent} />
                : <Branches agentId={agent} workspaces={workspaces} onChat={onChat} onResume={onResume} onFork={onFork} />}
      </div>
    </div>
  )
}

interface ChatSession { id: string; agent_id: string; project?: string; turns_n?: number; end_time?: string; chat_end_line?: number; start_time?: string }

/** The chat's recorded sessions, oldest first. */
function useChatSessions(agentId: string) {
  return useQuery({
    queryKey: ['aqua', 'chat-sessions', agentId],
    queryFn: ({ signal }) => getJson<{ sessions: ChatSession[] }>(`/api/sessions?agent_id=${encodeURIComponent(agentId)}`, signal),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    staleTime: 10_000,
  })
}

const SHOW_TURNS = 40
const firstLine = (s: string) => s.split('\n').find((l) => l.trim())?.trim() ?? ''

function Messages({ agentId, project }: { agentId: string; project: string }) {
  const q = useChatSessions(agentId)
  const sessions = useMemo(() => [...(q.data?.sessions ?? [])].reverse().slice(-3), [q.data])
  const turns = useSessionTurns(sessions)
  const marks = useMsgMarks()
  const list = useMemo(() => {
    const out: Array<{ sid: string; t: SessionTurn }> = []
    for (const s of sessions) for (const x of turns.data?.[s.id] ?? []) out.push({ sid: s.id, t: x })
    return out.slice(-SHOW_TURNS)
  }, [sessions, turns.data])
  const box = useRef<HTMLDivElement>(null)
  // The newest message at the bottom, in view, as in a chat.
  useEffect(() => { box.current?.scrollTo?.({ top: box.current.scrollHeight }) }, [list.length, agentId])
  if (q.isLoading || turns.isLoading) return <p className="m-0 p-12 text-12 aq-ink3">{t('Reading the chat…')}</p>
  if (!list.length) return <p className="m-0 p-12 text-12 aq-ink3">{t('No messages recorded in this chat yet.')}</p>
  const light = (target: string) => (marks.of('carry', target) ? 'red' : marks.of('carry-brief', target) ? 'yellow' : undefined)
  const msg = (sid: string, n: number, who: 'user' | 'agent', text: string) => {
    const side = who === 'agent' ? 'reply' as const : '' as const
    const target = `${agentId}#${n}${side ? '/reply' : ''}`
    return (
      <div className="group flex gap-6 px-8 py-4 rounded-[6px] hover:bg-[var(--bg-hover)]">
        <span className="aq-light" data-m={light(target)} aria-hidden />
        <div className="min-w-0 flex-1 flex flex-col gap-2">
          <div className="flex items-center gap-6">
            <span className="aq-label">{who === 'user' ? t('you') : t('agent')} · {n}</span>
            <span className="ml-auto"><MsgMarkButtons msg={{ agent_id: agentId, turn: n, side, project, session_id: sid, excerpt: firstLine(text).slice(0, 160) }} /></span>
          </div>
          <p className="m-0 text-12 leading-snug whitespace-pre-wrap break-words line-clamp-6" style={{ color: who === 'user' ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{text.trim()}</p>
        </div>
      </div>
    )
  }
  return (
    <div ref={box} className="flex-1 min-h-0 aq-scroll p-4 flex flex-col gap-2" aria-label={t('Messages')}>
      {list.map(({ sid, t: x }) => (
        <div key={`${sid}:${x.n}`} className="flex flex-col">
          {x.user && msg(sid, x.n, 'user', x.user)}
          {x.agent && msg(sid, x.n, 'agent', x.agent)}
        </div>
      ))}
    </div>
  )
}

function Pins({ agentId }: { agentId: string }) {
  const { all } = useMsgMarks()
  const act = useMsgMarkActions()
  const mine = all.filter((m) => m.agent_id === agentId && m.kind !== 'fork').sort((a, b) => a.turn - b.turn)
  const master = mine.find((m) => m.kind === 'pin')
  if (!mine.length) return <p className="m-0 p-12 text-12 aq-ink3">{t('Nothing pinned or carried in this chat. Pin a message from Messages, or type #pin in the chat.')}</p>
  const row = (m: MsgMark) => (
    <li key={`${m.kind}:${m.target}`} className="group flex items-start gap-6 px-8 py-6 rounded-[6px] hover:bg-[var(--bg-hover)]">
      <span className="pt-4"><MarkGlyph m={m} /></span>
      <span className="min-w-0 flex-1 flex flex-col gap-2">
        <span className="aq-label">{m.kind === 'pin' ? t('pinned') : m.kind === 'carry' ? t('carried whole') : t('carried as a brief')} · {m.turn}{m.side ? '↩' : ''}</span>
        <span className="text-12 leading-snug line-clamp-4" style={{ color: 'var(--text-primary)' }}>{(m.text || m.excerpt).trim()}</span>
      </span>
      <button type="button" data-nodrag className="aq-btn icon shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100" aria-label={t('Remove the mark')}
        onClick={() => act.remove(m.kind === 'pin' ? 'pin' : 'carry', m.target)}><X size={11} /></button>
    </li>
  )
  return (
    <div className="flex-1 min-h-0 aq-scroll flex flex-col">
      {master && (
        <div className="m-8 p-10 rounded-[8px] flex flex-col gap-4" style={{ background: 'var(--brand-glow)' }}>
          <span className="aq-label flex items-center gap-6" style={{ color: 'var(--brand)' }}><Pin size={11} />{t('master message')} · {master.turn}</span>
          <span className="text-13 leading-snug line-clamp-6" style={{ color: 'var(--text-primary)' }}>{(master.text || master.excerpt).trim()}</span>
        </div>
      )}
      <ul className="m-0 p-4 list-none flex flex-col">{mine.map(row)}</ul>
    </div>
  )
}

interface Brief { agent_id: string; agent_name?: string; chat_title?: string }
interface Profile {
  tasks: Array<{ id: string; title: string; status: string }>
  links: Array<{ id: string; kind: string; from_id: string; to_id: string; from: Brief; to: Brief }>
  parent: Brief | null
  children: Brief[]
  helpers: Array<Brief & { first?: string; tool?: string }>
}
const nameOf = (b: Brief) => b.agent_name || b.chat_title || b.agent_id

function Branches({ agentId, workspaces, onChat, onResume, onFork }: {
  agentId: string; workspaces: Workspace[]; onChat: (id: string) => void; onResume: (agentId: string) => void; onFork: (m: MsgMark) => void
}) {
  const q = useQuery({
    queryKey: ['aqua', 'profile', agentId],
    queryFn: ({ signal }) => getJson<Profile>(`/api/agents/${encodeURIComponent(agentId)}/profile`, signal),
    staleTime: 30_000,
  })
  const { all } = useMsgMarks()
  const forks = all.filter((m) => m.agent_id === agentId && m.kind === 'fork' && (m.state ?? '') === '')
  const terminalOf = (aid: string) => workspaces.flatMap((w) => w.sessions).find((s) => s.agent_id === aid && s.state !== 'ended')
  const chat = (b: Brief, how: string) => {
    const term = terminalOf(b.agent_id)
    return (
      <li key={`${how}:${b.agent_id}`} className="flex items-center gap-6 h-[24px] text-12 min-w-0 pl-14">
        <Link2 size={11} className="aq-ink3 shrink-0" aria-hidden />
        <span className="truncate" style={{ color: 'var(--text-primary)' }} title={b.agent_id}>{nameOf(b)}</span>
        <span className="text-10 aq-ink3 shrink-0">{how}</span>
        {term
          ? <button type="button" data-nodrag className="aq-btn !h-[20px] ml-auto shrink-0" onClick={() => onChat(term.id)}><Dot s={term} />{t('Open')}</button>
          : <button type="button" data-nodrag className="aq-btn !h-[20px] ml-auto shrink-0" onClick={() => onResume(b.agent_id)}><Play size={10} />{t('Resume')}</button>}
      </li>
    )
  }
  if (q.isLoading) return <p className="m-0 p-12 text-12 aq-ink3">{t('Reading the chat…')}</p>
  const p = q.data
  const links = (p?.links ?? []).map((l) => (l.from_id === agentId ? { b: l.to, how: l.kind } : { b: l.from, how: l.kind }))
  const empty = !p || (!p.tasks.length && !links.length && !p.parent && !p.children.length && !p.helpers.length && !forks.length)
  return (
    <div className="flex-1 min-h-0 aq-scroll p-8 flex flex-col gap-10" aria-label={t('Branches')}>
      {q.isError && <p className="m-0 text-12 aq-ink3">{t('The chat\'s branches could not be read.')}</p>}
      {empty && !q.isError && <p className="m-0 text-12 aq-ink3">{t('No branches: this chat handed no task, has no linked chat and started no helper.')}</p>}
      {p && p.tasks.length > 0 && (
        <section><span className="aq-label">{t('tasks it worked on')}</span>
          <ul className="m-0 p-0 list-none">
            {p.tasks.map((x) => (
              <li key={x.id} className="flex items-center gap-6 h-[24px] text-12 min-w-0">
                <span className="w-[8px] h-[8px] rounded-[2px] shrink-0" style={{ background: x.status === 'done' ? 'var(--status-green)' : x.status === 'doing' ? 'var(--brand)' : 'var(--text-tertiary)' }} />
                <span className="truncate" style={{ color: 'var(--text-primary)' }} title={x.title}>{x.title || x.id}</span>
                <span className="ml-auto text-10 font-mono aq-ink3 shrink-0">{x.id}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {p && (p.parent || p.children.length > 0 || links.length > 0) && (
        <section><span className="aq-label">{t('linked chats')}</span>
          <ul className="m-0 p-0 list-none">
            {p.parent && chat(p.parent, t('started this one'))}
            {p.children.map((c) => chat(c, t('started from this one')))}
            {links.map((l) => chat(l.b, l.how))}
          </ul>
        </section>
      )}
      {p && p.helpers.length > 0 && (
        <section><span className="aq-label">{t('runs it started')}</span>
          <ul className="m-0 p-0 list-none">
            {p.helpers.map((h) => (
              <li key={h.agent_id} className="flex items-center gap-6 h-[24px] text-12 min-w-0 aq-ink2"><Bot size={11} className="shrink-0" /><span className="truncate" title={h.first}>{h.first || nameOf(h)}</span></li>
            ))}
          </ul>
        </section>
      )}
      {forks.length > 0 && (
        <section><span className="aq-label">{t('fork later')}</span>
          <ul className="m-0 p-0 list-none flex flex-col gap-4 pt-2">
            {forks.map((m) => (
              <li key={m.target} className="flex items-center gap-6 px-6 py-4 rounded-[6px] text-12" style={{ border: '1.5px dashed var(--status-purple)' }}>
                <GitFork size={11} style={{ color: 'var(--status-purple)' }} className="shrink-0" aria-hidden />
                <span className="truncate flex-1" style={{ color: 'var(--text-secondary)' }} title={m.text}>{firstLine(m.excerpt || m.text)}</span>
                {m.command && <button type="button" data-nodrag className="aq-btn line shrink-0" onClick={() => onFork(m)}><Play size={11} />{t('Hand to an agent')}</button>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

const STATS: Shown[] = ['working', 'waiting', 'idle', 'asleep', 'ended']

function Stats({ workspaces }: { workspaces: Workspace[] }) {
  const live = workspaces.filter((w) => w.sessions.length > 0)
  const all = live.flatMap((w) => w.sessions)
  const chips = (list: AquaSession[]) => STATS.map((k) => [k, list.filter((s) => shownOf(s) === k).length] as const).filter(([, n]) => n > 0)
  const row = (key: string, name: ReactNode, list: AquaSession[], bold = false) => (
    <li key={key} className="flex items-start gap-8 py-6" style={{ borderTop: '1px solid var(--border-default)' }}>
      <span className={`w-[110px] shrink-0 inline-flex items-center gap-6 min-w-0 text-12 ${bold ? 'font-semibold' : ''}`} style={{ color: 'var(--text-primary)' }}>{name}</span>
      <span className="flex flex-wrap gap-4 min-w-0">
        {chips(list).map(([k, n]) => (
          <span key={k} className="aq-chip" style={k === 'waiting' ? { color: 'var(--status-amber)' } : undefined}><b className="tabular-nums">{n}</b> {SHOWN_WORD[k]}</span>
        ))}
      </span>
    </li>
  )
  return (
    <div className="flex-1 min-h-0 aq-scroll p-8">
      <ul className="m-0 p-0 list-none" aria-label={t('Terminals by state')}>
        {live.map((w) => row(w.id, <><Swatch w={w} /><span className="truncate">{w.name}</span></>, w.sessions))}
        {row('all', t('all'), all, true)}
      </ul>
      <p className="m-0 pt-8 text-11 aq-ink3">{tn(all.filter((s) => roleOf(s) === 'server').length, '{n} server', '{n} servers')}</p>
    </div>
  )
}
