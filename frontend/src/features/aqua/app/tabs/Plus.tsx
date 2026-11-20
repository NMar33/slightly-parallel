/**
 * The "+" after the last tab (tk_c50ff865 in tk_a9306fb1): button a «split»
 * and menu a «list» from the round 3 lab (`design/round3/lab/Plus.tsx`).
 *
 * "+" and "⌄" side by side, flat, one hairline between them, as in Windows
 * Terminal. A plain click on "+" opens a plain terminal at once: the
 * operator's shell in the project's folder, as any terminal does
 * (tk_e7649e7c). Ctrl+click on "+", a click on "⌄" or alt+N opens the
 * list: a chat with each agent this computer has, a dev server, a branch
 * of the current chat, resume, a chat from a board task. Rows carry a line
 * of hint and a key; keys 1–9 pick, Esc closes; sub-choices open in place.
 * The left sidebar draws the same split as «New terminal ⌄» (look "side").
 */

import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bot, ChevronDown, ClipboardList, FolderGit2, GitBranch, Moon, Plus, Server, Terminal } from 'lucide-react'

import { getJson } from '../../../../lib/getJson'
import { t } from '../../../../i18n/scope/aqua'

export type AgentCmd = 'claude' | 'codex' | 'opencode'
export const AGENT_NAME: Record<AgentCmd, string> = { claude: 'Claude Code', codex: 'Codex', opencode: 'OpenCode' }

/** The agent a chat runs: its recorded tool, else the program in front, else the command it started with, else the default. */
export function agentOf(tool: string | undefined, program: string | undefined, command: string | undefined, fallback: AgentCmd): AgentCmd {
  if (tool === 'claude-code' || tool === 'claude') return 'claude'
  if (tool === 'codex' || tool === 'opencode') return tool
  for (const raw of [program, (command ?? '').trim().split(/\s+/)[0]]) {
    const name = (raw ?? '').split('/').pop()?.replace(/^-/, '') ?? ''
    if (name === 'claude' || name === 'codex' || name === 'opencode') return name
  }
  return fallback
}

export interface PlusActions {
  /** A new chat with this agent in the project. */
  agent: (a: AgentCmd) => void
  shell: () => void
  server: () => void
  /** Branch the current chat; absent when it cannot be branched. */
  branch?: () => void
  wake: (sid: string) => void
  resume: (agentId: string) => void
  task: (taskId: string) => void
}

interface Sub { id: string; label: string; run: () => void }
interface Item { id: string; icon: ReactNode; label: string; hint: string; soon?: boolean; sub?: Sub[]; run?: () => void }

interface TaskRow { id: string; title?: string; status?: string }
interface Resumable { agent_id: string; name: string; tool: string }

const DONE = new Set(['done', 'done-archived', 'cancelled', 'canceled', 'archived'])

/** The rows of the list. Pure: tested on its own. */
export function plusItems(o: {
  /** The agent to offer while the installed ones are not known yet. */
  agent: AgentCmd; project: string; path: string; chatTitle: string
  installed: Record<AgentCmd, boolean> | null
  asleep: Array<{ id: string; title: string }>
  resumable: Resumable[]
  tasks: TaskRow[]
  act: PlusActions
}): Item[] {
  const { act } = o
  const where = o.path || o.project
  const agents = (Object.keys(AGENT_NAME) as AgentCmd[]).filter((a) => (o.installed ? o.installed[a] : a === o.agent))
  const open = o.tasks.filter((x) => !DONE.has(String(x.status ?? '').toLowerCase())).slice(0, 30)
  return [
    { id: 'shell', icon: <Terminal size={14} />, label: t('Plain terminal'), hint: `${t('A shell in')} ${where}, ${t('no agent')}. ${t('A plain click on + does the same.')}`, run: act.shell },
    ...agents.map((a): Item => ({ id: `agent:${a}`, icon: <Bot size={14} />, label: `${t('New chat')}: ${AGENT_NAME[a]}`, hint: t('A new {agent} chat in {where}', { agent: AGENT_NAME[a], where }), run: () => act.agent(a) })),
    { id: 'server', icon: <Server size={14} />, label: t('Dev server'), hint: t('A terminal for the project\'s server: it sits after the chats and keeps running while they sleep'), run: act.server },
    { id: 'branch', icon: <GitBranch size={14} />, label: t('Branch the current chat'),
      hint: act.branch ? `${t('A new chat that starts with the conversation of')} ${o.chatTitle}; ${t('this one goes on')}` : t('Only a Claude Code or Codex chat that Slightly Parallel recorded can be branched'),
      run: act.branch },
    { id: 'resume', icon: <Moon size={14} />, label: t('Resume a sleeping chat'),
      hint: o.asleep.length || o.resumable.length ? t('A sleeping chat or a closed tab of this project, by its session id') : t('No sleeping chats in this project'),
      sub: [
        ...o.asleep.map((s) => ({ id: `s:${s.id}`, label: `${s.title} · ${t('asleep')}`, run: () => act.wake(s.id) })),
        ...o.resumable.map((c) => ({ id: `r:${c.agent_id}`, label: `${c.name} · ${t('closed tab')}`, run: () => act.resume(c.agent_id) })),
      ] },
    { id: 'task', icon: <ClipboardList size={14} />, label: t('New chat from a board task'), hint: t('The task\'s text is the first message; the chat starts with the agent of Settings › Terminal'),
      sub: open.map((x) => ({ id: x.id, label: `${x.id} · ${x.title ?? ''}`, run: () => act.task(x.id) })) },
    { id: 'worktree', icon: <FolderGit2 size={14} />, label: t('New chat in its own worktree'), soon: true, hint: t('Two agents in one folder edit the same files; a worktree gives the new one its own copy and branch') },
  ]
}

export type PlusProps = {
  agent: AgentCmd
  project: string
  path: string
  chatTitle: string
  asleep: Array<{ id: string; title: string }>
  act: PlusActions
}

export function PlusButton({ agent, project, path, chatTitle, asleep, act, open: openProp, setOpen: setOpenProp, look = 'strip' }: PlusProps & {
  /** Held by the window (alt+N opens the strip's list); left out, the button holds its own. */
  open?: boolean
  setOpen?: (v: boolean) => void
  /** "strip": "+" and "⌄" after the tabs; "side": «New terminal» and "⌄" in the left sidebar. */
  look?: 'strip' | 'side'
}) {
  const [own, setOwn] = useState(false)
  const open = openProp ?? own
  const setOpen = setOpenProp ?? setOwn
  const [sub, setSub] = useState<string | null>(null)
  const box = useRef<HTMLSpanElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const [at, setAt] = useState({ x: 8, y: 66 })
  const installed = useQuery({
    queryKey: ['terminal', 'agents-installed'],
    queryFn: ({ signal }) => getJson<{ agents: Record<AgentCmd, boolean> }>('/api/terminal/agents', signal).then((d) => d.agents),
    // Read before the list opens, so its rows and their keys do not move under the operator.
    staleTime: 5 * 60_000, retry: false,
  })
  const resumable = useQuery({
    queryKey: ['terminal', 'resumable', project],
    queryFn: ({ signal }) => getJson<{ chats: Resumable[] }>(`/api/terminal/resumable?project=${encodeURIComponent(project)}`, signal).then((d) => d.chats ?? []),
    staleTime: 10_000, retry: false, enabled: open && !!project,
  })
  const tasks = useQuery({
    queryKey: ['terminal', 'plus-tasks', project],
    queryFn: ({ signal }) => getJson<{ tasks?: TaskRow[] }>(`/api/tasks?project=${encodeURIComponent(project)}`, signal).then((d) => d.tasks ?? []),
    staleTime: 10_000, retry: false, enabled: open && !!project,
  })
  const close = () => { setOpen(false); setSub(null) }
  const wrap = (f: () => void) => () => { close(); f() }
  const items = plusItems({
    agent, project, path, chatTitle, installed: installed.data ?? null, asleep,
    resumable: resumable.data ?? [], tasks: tasks.data ?? [],
    act: {
      agent: (a) => wrap(() => act.agent(a))(), shell: wrap(act.shell), server: wrap(act.server),
      branch: act.branch ? wrap(act.branch) : undefined,
      wake: (id) => wrap(() => act.wake(id))(), resume: (id) => wrap(() => act.resume(id))(), task: (id) => wrap(() => act.task(id))(),
    },
  })
  const choose = (it: Item) => {
    if (it.soon) return
    if (it.run) { it.run(); return }
    if (it.sub?.length) setSub(sub === it.id ? null : it.id)
  }
  // Under the button; above it when the window has no room below (the left sidebar's foot).
  const place = () => {
    const r = box.current?.getBoundingClientRect()
    if (!r) return
    const h = list.current?.offsetHeight ?? 0
    const below = r.bottom + 4
    const y = below + h > window.innerHeight - 8 && r.top - 4 - h >= 8 ? r.top - 4 - h : below
    setAt((p) => (p.x === Math.max(8, Math.min(r.left, window.innerWidth - 348)) && p.y === y ? p : { x: Math.max(8, Math.min(r.left, window.innerWidth - 348)), y }))
  }
  useLayoutEffect(() => { if (open) place() })
  useEffect(() => { if (!open) setSub(null) }, [open])

  // keys 1–9 pick an item; Escape and a click elsewhere close the choice
  const itemsRef = useRef(items)
  itemsRef.current = items
  const chooseRef = useRef(choose)
  chooseRef.current = choose
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); return }
      const n = Number(e.key)
      if (Number.isInteger(n) && n >= 1 && n <= itemsRef.current.length && !e.altKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault(); e.stopPropagation(); chooseRef.current(itemsRef.current[n - 1]!)
      }
    }
    const onDown = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) close() }
    window.addEventListener('keydown', onKey, true)
    window.addEventListener('pointerdown', onDown)
    return () => { window.removeEventListener('keydown', onKey, true); window.removeEventListener('pointerdown', onDown) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const click = (e: MouseEvent) => { if (e.ctrlKey || e.metaKey) { setOpen(!open); return } act.shell() }
  // Chromium sends a contextmenu event for Control-click on macOS.
  const contextMenu = (e: MouseEvent) => {
    if (!e.ctrlKey) return
    e.preventDefault()
    setOpen(true)
  }
  const plusTip = `${t('New terminal')}: ${t('a shell in')} ${path || project}. ${t('Ctrl+click: choose')} (Ctrl+Shift+T)`
  const chevron = (
    <button type="button" data-nodrag className={`h-full ${look === 'side' ? 'w-[22px]' : 'w-[18px]'} inline-flex items-center justify-center rounded-r-[6px] hover:bg-[var(--aq-hover)] aq-ink3`}
      aria-label={t('Choose what to open')} title={`${t('Choose what to open')} (alt+N)`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
      <ChevronDown size={11} />
    </button>
  )
  return (
    <span ref={box} className={look === 'side' ? 'relative inline-flex' : 'self-center relative shrink-0 inline-flex ml-2'}>
      {look === 'side' ? (
        <span className="inline-flex items-center h-[24px] rounded-[6px]" data-plus="side" style={{ border: '1px solid var(--border-default)' }}>
          <button type="button" data-nodrag className="h-full px-6 inline-flex items-center gap-4 rounded-l-[6px] text-12 hover:bg-[var(--aq-hover)]" style={{ color: 'var(--aq-ink2)' }}
            title={plusTip} onClick={click} onContextMenu={contextMenu}><Plus size={12} />{t('New terminal')}</button>
          <span className="w-px h-[12px]" style={{ background: 'var(--aq-line)' }} />
          {chevron}
        </span>
      ) : (
        <span className="inline-flex items-center h-[24px] rounded-[6px]" data-plus="a">
          <button type="button" data-nodrag className="h-full w-[26px] inline-flex items-center justify-center rounded-l-[6px] hover:bg-[var(--aq-hover)]" style={{ color: 'var(--aq-ink2)' }}
            aria-label={t('New terminal')} title={plusTip} onClick={click} onContextMenu={contextMenu}><Plus size={14} /></button>
          <span className="w-px h-[12px]" style={{ background: 'var(--aq-line)' }} />
          {chevron}
        </span>
      )}
      {open && (
        <div ref={list} className="fixed z-[220] w-[340px] rounded-[8px] p-4 aq-fade" role="menu" aria-label={t('Open a new terminal')} data-plusmenu="a"
          style={{ left: at.x, top: at.y, background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)' }}>
          {items.map((it, i) => (
            <div key={it.id}>
              {(it.id === 'task' || (it.id.startsWith('agent:') && i > 0 && !items[i - 1]!.id.startsWith('agent:'))) && <div className="mx-8 my-4" style={{ borderTop: '1px solid var(--aq-line)' }} />}
              <button type="button" role="menuitem" data-item={it.id} className="aq-row w-full px-8 py-4 text-12 items-start text-left disabled:opacity-50" aria-expanded={it.sub ? sub === it.id : undefined}
                disabled={it.soon || (!it.run && !it.sub?.length)} onClick={() => choose(it)}>
                <span className="mt-[1px] shrink-0 aq-ink3">{it.icon}</span>
                <span className="flex flex-col min-w-0 flex-1">
                  <span style={{ color: 'var(--aq-ink)' }}>
                    {it.label}{it.sub && <ChevronDown size={10} className="inline ml-4 aq-ink3" />}
                    {it.soon && <span className="aq-chip ml-6">{t('soon')}</span>}
                  </span>
                  <span className="text-11 aq-ink3 leading-[1.35]">{it.hint}</span>
                </span>
                <kbd className="aq-kbd shrink-0">{i + 1}</kbd>
              </button>
              {sub === it.id && it.sub && (
                <div className="ml-[30px] flex flex-col py-2 max-h-[220px] overflow-y-auto" role="group" aria-label={it.label}>
                  {it.sub.map((x) => (
                    <button key={x.id} type="button" role="menuitem" className="aq-row h-[24px] px-8 text-12 truncate" onClick={x.run}><span className="truncate">{x.label}</span></button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </span>
  )
}
