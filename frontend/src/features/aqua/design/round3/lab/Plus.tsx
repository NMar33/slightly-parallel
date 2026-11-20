/**
 * Round 3 lab, tk_c50ff865: the "+" at the end of J's tab strip.
 *
 * A plain click opens a new terminal tab at once: the current chat's agent
 * in the current project. Ctrl+click, or the small ▾ beside it, opens the
 * choice. Keys 1–9 pick an item while the choice is open.
 *
 * Three looks, each taken from a terminal people already know:
 *   a · split button — Windows Terminal: "+" and a "⌄" side by side right
 *       after the last tab, flat, one hairline between them; the ⌄ holds
 *       the profiles. Its hover fills like a tab.
 *   b · ghost tab — Ghostty and iTerm2 (the macOS tab bar): the "+" is shaped
 *       like an empty tab, same height and corners as a tab, so it reads as
 *       "one more of these"; the ▾ sits inside it, faint.
 *   c · labelled pill — Warp and WezTerm: Warp's "+" carries its launch
 *       configurations, WezTerm draws the "+" as text in the bar. Here the
 *       pill says which agent a plain click opens ("+ cc"), so the plain
 *       click is never a guess.
 *
 * Two menus:
 *   a · list — rows with a line of hint and a key, the way Windows
 *       Terminal's profile list reads; sub-choices open in place.
 *   b · cards — a grid of cards with a key each, the way Warp shows launch
 *       configurations; sub-choices open under the grid.
 *
 * The two proposed items ("killer"): a new chat from a board task (most
 * chats here start from a task, so its text and briefing go in without a
 * copy) and a new chat in its own git worktree (two agents in one folder
 * edit the same files; a worktree gives the new one its own copy).
 */

import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { Bot, ChevronDown, ClipboardList, FolderGit2, GitBranch, Moon, Plus, Server, SquareTerminal, Terminal } from 'lucide-react'

import { t } from '../../../../../i18n/scope/aqua'
import { SERVERS, SESSIONS, TASKS, projectOf, type Session } from '../../mock'
import { flash, useAqua, wake } from '../../store'
import { newChat, openTab, tabTitle, useLab, type LabPick, type NewKind } from './live'

const AGENT = { claude: 'Claude Code', codex: 'Codex' } as const

interface Item { id: string; icon: ReactNode; label: string; hint: string; proposed?: boolean; sub?: Array<{ id: string; label: string; run: () => void }>; run?: () => void }

export function PlusButton({ look, menu, chat, onOpen, onServer, shown = false }: {
  look: LabPick['plus']
  menu: LabPick['plusmenu']
  /** The current chat: its agent and project are what a plain click opens. */
  chat: Session
  onOpen: (id: string) => void
  onServer: (id: string) => void
  /** Held open, the choice under the button in the page's flow: K's compare view. */
  shown?: boolean
}) {
  const [opened, setOpen] = useState(false)
  const open = shown || opened
  const [sub, setSub] = useState<string | null>(null)
  const st = useAqua()
  const lab = useLab()
  const box = useRef<HTMLSpanElement>(null)
  const p = projectOf(chat.project)
  const agent = AGENT[chat.tool]

  const close = () => { setOpen(false); setSub(null) }
  // the choice is fixed to the screen, under the button: the window's rounded frame would cut it off
  const [at, setAt] = useState({ x: 0, y: 0 })
  const toggle = () => {
    const r = box.current?.getBoundingClientRect()
    const w = menu === 'a' ? 340 : 560
    // clear of the Variants panel in the desktop's top-right corner
    if (r) setAt({ x: Math.max(8, Math.min(r.left, window.innerWidth - w - 324)), y: r.bottom + 4 })
    setOpen(!open)
  }
  const start = (kind: NewKind, from?: Session, extra?: string, word?: string) => {
    const s = newChat(chat.project, kind, from, extra)
    onOpen(s.id)
    flash(`${word ?? t('New terminal')}: ${tabTitle(s)}`)
    close()
  }
  const plain = () => start(chat.tool === 'codex' ? 'codex' : 'claude', undefined, undefined, `${t('New terminal')} · ${agent} · ${p.name}`)

  const sleeping = SESSIONS.filter((s) => s.project === chat.project && (st.asleep[s.id] || lab.closed[s.id]))
  const servers = SERVERS.filter((s) => s.project === chat.project)
  const tasks = TASKS.filter((x) => x.status !== 'done' && !x.chat && SESSIONS.find((s) => s.id === x.from)?.project === chat.project)

  const items: Item[] = [
    { id: 'same', icon: <Bot size={14} />, label: `${t('New chat')}: ${agent}`, hint: `${t('The current agent in')} ${p.path}. ${t('A plain click on + does the same.')}`, run: plain },
    { id: 'other', icon: <Bot size={14} />, label: t('Another agent'), hint: t('Claude Code, Codex or OpenCode in the same folder'), sub: [
      { id: 'claude', label: 'Claude Code', run: () => start('claude') },
      { id: 'codex', label: 'Codex', run: () => start('codex') },
      { id: 'opencode', label: 'OpenCode', run: () => start('opencode') },
    ] },
    { id: 'shell', icon: <Terminal size={14} />, label: t('Plain terminal'), hint: `${t('A shell in')} ${p.path}, ${t('no agent')}`, run: () => start('shell', undefined, undefined, t('Plain terminal')) },
    { id: 'server', icon: <Server size={14} />, label: t('Dev server'), hint: t('Starts one of the project\'s servers beside the terminal'), sub: servers.map((sv) => ({
      id: sv.id, label: `${sv.name} · ${sv.command}`, run: () => { onServer(sv.id); flash(`${t('Dev server')}: ${sv.name}`); close() },
    })) },
    { id: 'branch', icon: <GitBranch size={14} />, label: t('Branch the current chat'), hint: `${t('A new chat that starts with the conversation of')} ${tabTitle(chat)}; ${t('this one goes on')}`, run: () => start('branch', chat, undefined, t('Branched')) },
    { id: 'resume', icon: <Moon size={14} />, label: t('Resume a sleeping chat'), hint: sleeping.length ? t('A sleeping chat or a closed tab of this project, by its session id') : t('No sleeping chats in this project'), sub: sleeping.map((s) => ({
      id: s.id, label: `${tabTitle(s)}${lab.closed[s.id] ? ` · ${t('closed tab')}` : ''}`, run: () => { if (st.asleep[s.id]) wake(s.id); openTab(s.id); onOpen(s.id); flash(`${t('Resumed')}: ${tabTitle(s)}`); close() },
    })) },
    { id: 'task', icon: <ClipboardList size={14} />, label: t('New chat from a board task'), proposed: true, hint: t('Most chats start from a task: its text and briefing become the first message, and the task links to the chat'), sub: tasks.map((x) => ({
      id: x.id, label: `${x.id} · ${x.title}`, run: () => start('task', undefined, x.id, `${t('New chat for')} ${x.id}`),
    })) },
    { id: 'worktree', icon: <FolderGit2 size={14} />, label: t('New chat in its own worktree'), proposed: true, hint: t('Two agents in one folder edit the same files; a worktree gives the new one its own copy and branch'), run: () => start('worktree', undefined, undefined, t('New worktree')) },
  ]

  const choose = (it: Item) => {
    if (it.run) { it.run(); return }
    if (it.sub?.length) setSub(sub === it.id ? null : it.id)
  }

  // keys 1–9 pick an item; Escape and a click elsewhere close the choice
  useEffect(() => {
    if (!open || shown) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { close(); return }
      const n = Number(e.key)
      if (n >= 1 && n <= items.length && !e.altKey && !e.ctrlKey) { e.preventDefault(); choose(items[n - 1]!) }
    }
    const onDown = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) close() }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onDown)
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('pointerdown', onDown) }
  })

  const click = (e: MouseEvent) => { if (e.ctrlKey || e.metaKey) { toggle(); return } plain() }
  const plusTip = `${t('New terminal')}: ${agent} · ${p.name}. ${t('Ctrl+click: choose')}`
  const caret = (cls: string) => (
    <button type="button" data-nodrag className={cls} aria-label={t('Choose what to open')} title={t('Choose what to open')} aria-haspopup="menu" aria-expanded={open} onClick={toggle}>
      <ChevronDown size={11} />
    </button>
  )

  let button: ReactNode
  if (look === 'a') {
    button = (
      <span className="inline-flex items-center h-[24px] rounded-[6px]" data-plus="a">
        <button type="button" data-nodrag className="h-full w-[26px] inline-flex items-center justify-center rounded-l-[6px] hover:bg-[var(--aq-hover)]" style={{ color: 'var(--aq-ink2)' }} aria-label={t('New terminal')} title={plusTip} onClick={click}><Plus size={14} /></button>
        <span className="w-px h-[12px]" style={{ background: 'var(--aq-line)' }} />
        {caret('h-full w-[18px] inline-flex items-center justify-center rounded-r-[6px] hover:bg-[var(--aq-hover)] aq-ink3')}
      </span>
    )
  } else if (look === 'b') {
    button = (
      <span className="self-end inline-flex items-center h-[26px] rounded-t-[6px] hover:bg-[var(--aq-hover)]" style={{ border: '1px solid var(--aq-line)', borderBottom: 'none' }} data-plus="b">
        <button type="button" data-nodrag className="h-full w-[30px] inline-flex items-center justify-center" style={{ color: 'var(--aq-ink2)' }} aria-label={t('New terminal')} title={plusTip} onClick={click}><Plus size={14} /></button>
        {caret('h-full w-[14px] mr-[2px] inline-flex items-center justify-center aq-ink3 opacity-70 hover:opacity-100')}
      </span>
    )
  } else {
    button = (
      <span className="inline-flex items-center gap-2" data-plus="c">
        <button type="button" data-nodrag className="h-[22px] pl-6 pr-8 inline-flex items-center gap-4 rounded-full text-11 font-medium"
          style={{ background: 'var(--brand-glow)', color: 'var(--brand)', border: '1px solid color-mix(in srgb, var(--brand) 35%, transparent)' }} aria-label={t('New terminal')} title={plusTip} onClick={click}>
          <Plus size={12} />{chat.tool === 'codex' ? 'cx' : 'cc'}
        </button>
        {caret('h-[22px] w-[16px] inline-flex items-center justify-center rounded-full aq-ink3 hover:bg-[var(--aq-hover)]')}
      </span>
    )
  }

  const subOf = items.find((x) => x.id === sub)
  const subList = subOf && (
    <div className="flex flex-col py-2" role="group" aria-label={subOf.label}>
      {subOf.sub!.map((x) => (
        <button key={x.id} type="button" role="menuitem" className="aq-row h-[24px] px-8 text-12 truncate" onClick={x.run}><span className="truncate">{x.label}</span></button>
      ))}
    </div>
  )

  return (
    <span ref={box} className="relative self-center shrink-0 inline-flex" style={look === 'b' ? { alignSelf: 'flex-end' } : undefined}>
      {button}
      {open && (menu === 'a' ? (
        <div className={`${shown ? 'absolute' : 'fixed'} z-[220] w-[340px] rounded-[8px] p-4 aq-fade`} role="menu" aria-label={t('Open a new terminal')} data-plusmenu="a"
          style={{ ...(shown ? { left: 0, top: 30 } : { left: at.x, top: at.y }), background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)' }}>
          {items.map((it, i) => (
            <div key={it.id}>
              {it.proposed && !items[i - 1]?.proposed && <div className="mx-8 my-4" style={{ borderTop: '1px solid var(--aq-line)' }} />}
              <button type="button" role="menuitem" className="aq-row w-full px-8 py-4 text-12 items-start text-left" aria-expanded={it.sub ? sub === it.id : undefined}
                disabled={!it.run && !it.sub?.length} onClick={() => choose(it)}>
                <span className="mt-[1px] shrink-0 aq-ink3">{it.icon}</span>
                <span className="flex flex-col min-w-0 flex-1">
                  <span style={{ color: 'var(--aq-ink)' }}>{it.label}{it.sub && <ChevronDown size={10} className="inline ml-4 aq-ink3" />}</span>
                  <span className="text-11 aq-ink3 leading-[1.35]">{it.hint}</span>
                </span>
                <kbd className="aq-kbd shrink-0">{i + 1}</kbd>
              </button>
              {sub === it.id && <div className="ml-[30px]">{subList}</div>}
            </div>
          ))}
        </div>
      ) : (
        <div className={`${shown ? 'absolute' : 'fixed'} z-[220] w-[560px] rounded-[10px] p-8 aq-fade`} role="menu" aria-label={t('Open a new terminal')} data-plusmenu="b"
          style={{ ...(shown ? { left: 0, top: 30 } : { left: at.x, top: at.y }), background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)' }}>
          <div className="grid grid-cols-4 gap-6">
            {items.map((it, i) => (
              <button key={it.id} type="button" role="menuitem" className="relative flex flex-col items-start gap-4 p-8 rounded-[8px] text-left text-12 hover:bg-[var(--aq-hover)] disabled:opacity-50"
                style={{ border: `1px solid ${sub === it.id ? 'var(--brand)' : 'var(--aq-line)'}`, minHeight: 104 }} aria-expanded={it.sub ? sub === it.id : undefined}
                disabled={!it.run && !it.sub?.length} onClick={() => choose(it)}>
                <span className="flex items-center w-full">
                  <span className="aq-ink3" style={it.proposed ? { color: 'var(--brand)' } : undefined}>{it.icon}</span>
                  <kbd className="aq-kbd ml-auto">{i + 1}</kbd>
                </span>
                <span className="font-medium leading-[1.25]" style={{ color: 'var(--aq-ink)' }}>{it.label}</span>
                <span className="text-10 aq-ink3 leading-[1.3]">{it.hint}</span>
              </button>
            ))}
          </div>
          {subList && <div className="mt-6 pt-4" style={{ borderTop: '1px solid var(--aq-line)' }}>{subList}</div>}
          <div className="mt-6 flex items-center gap-6 text-10 aq-ink3"><SquareTerminal size={11} />{t('A plain click on + opens the first card. Keys 1–9 pick, Esc closes.')}</div>
        </div>
      ))}
    </span>
  )
}
