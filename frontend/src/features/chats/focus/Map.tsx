/**
 * Focus mode's map: one chat, full screen. The chats list on the left
 * (find, filter, resize), one reading column as wide as you set it, the
 * whole chat drawn small down the right edge — click or drag it — one chat
 * or all of them read as one, and the agent's terminal beside it (T).
 */

import { IconButton } from '../../../components/primitives'
import { persistPref, readPref } from '../../../lib/uiPrefs'
import { STATE_WORD, terminalOfAgent, useTerminalActions, useTerminalStatus, useTerminals } from '../../../lib/terminal'
import { Screen, TERMINAL_GROUND } from '../../terminal/Screen'
import { StateDot, TurnOn } from '../../terminal/parts'
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, Menu, Minimize2, RotateCcw, Search, Settings2, SquareTerminal } from 'lucide-react'

import { Segmented } from '../../../components/Segmented'
import { useSessionTurns, WorkLine, type SessionTurn } from '../../agents/dossier'
import { fmtDay } from '../../agents/parts'
import { fmtMinutes } from '../../agents/profile'
import { mentionLabel } from '../../project/mentions'
import type { Row } from '../data'
import { applyFilter, FilterButton, FilterPanel, readFilter, storeFilter, type FocusFilter } from './filter'
import {
  Answer, Column, EdgeHandle, FocusSettings, Frame, WorkMark, YourMessage, firstLine, readFocusPrefs, storeFocusPrefs, words, type FocusPrefs, useFocusKeys,
} from './shared'

import { t } from '../../../i18n/scope/views'
import { isTypingTarget } from '../../../lib/typing'
interface Props {
  session: Row
  sessions: Row[]
  /** Every chat of the project, for the map's own filter; `sessions` if absent. */
  pool?: Row[]
  /** The agent the page has picked: the filter starts with it. */
  agent?: string
  onPick: (id: string) => void
  onClose: () => void
  onOpenTask?: (id: string) => void
  star?: (turn: number, text: string) => ReactNode
}

/** The chats to pick from, newest first, found by any word of their title. */
function ChatList({ sessions, current, onPick, autoFocus, size = 13, tools, below }: {
  sessions: Row[]; current: string; onPick: (id: string) => void; autoFocus?: boolean
  /** Beside the find box (the filter's button), and under it (its panel). */
  tools?: ReactNode
  below?: ReactNode
  /** The title's text size in px; the line under it follows. */
  size?: number
}) {
  const [find, setFind] = useState('')
  const shown = useMemo(() => {
    const n = find.trim().toLowerCase()
    return n ? sessions.filter((s) => `${s.l1} ${mentionLabel(s)}`.toLowerCase().includes(n)) : sessions
  }, [sessions, find])
  const list = useRef<HTMLOListElement>(null)
  // The chat in view stays in sight in the list, also as "all" scrolls on.
  useEffect(() => { list.current?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: 'nearest' }) }, [current])
  return (
    <div className="flex flex-col min-h-0 h-full">
      <div className="shrink-0 flex items-center gap-6 mx-12 my-8">
        <label className="flex-1 min-w-0 flex items-center gap-6 h-[28px] px-8 rounded-input border border-border-default bg-surface">
          <Search size={12} className="text-tertiary" aria-hidden />
          <input autoFocus={autoFocus} value={find} onChange={(e) => setFind(e.target.value)} placeholder={t('Find a chat')}
            className="flex-1 min-w-0 bg-transparent text-12 text-primary outline-none" />
        </label>
        {tools}
      </div>
      {below}
      <ol ref={list} className="flex-1 min-h-0 overflow-y-auto">
        {shown.map((s) => (
          <li key={s.id}>
            <button type="button" aria-current={s.id === current} onClick={() => onPick(s.id)}
              className={`w-full text-left px-12 py-6 flex flex-col gap-2 border-l-2 ${s.id === current ? 'border-brand bg-brand-glow' : 'border-transparent hover:bg-hover'}`}>
              <span className="font-mono text-tertiary tabular-nums" style={{ fontSize: Math.max(10, size - 2) }}>{fmtDay(s.created_date)} {s.start_time} · {s.turns_n}{t('t ·')}{' '}{mentionLabel(s)}</span>
              <span className="text-primary leading-snug" style={{ fontSize: size, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{s.l1 || '—'}</span>
            </button>
          </li>
        ))}
        {shown.length === 0 && <li className="px-12 py-8 text-12 text-tertiary">{find.trim() ? t('No chat has that in its title.') : t('No chat is left by the filter.')}</li>}
      </ol>
    </div>
  )
}

/* =============================================================== E · Map */

interface Block { top: number; height: number; you: number; gi: number }

function Minimap({ scroller, turns, at, goTo, chats = false, version = 0 }: {
  scroller: React.RefObject<HTMLDivElement>; turns: SessionTurn[]; at: number; goTo: (i: number) => void
  /** Draw where each chat starts (the "all" read). */
  chats?: boolean
  /** Changes when more of the chat is drawn: measure again. */
  version?: number
}) {
  const box = useRef<HTMLDivElement>(null)
  const [blocks, setBlocks] = useState<Block[]>([])
  const [view, setView] = useState({ top: 0, height: 0, total: 1 })
  const [hover, setHover] = useState<number | null>(null)
  const [heads, setHeads] = useState<number[]>([])
  const measure = useCallback(() => {
    const root = scroller.current
    if (!root) return
    const total = Math.max(1, root.scrollHeight)
    const out: Block[] = []
    root.querySelectorAll<HTMLElement>('[data-turn-index]').forEach((el) => {
      const you = el.querySelector<HTMLElement>('[data-you]')
      // Measured against the scroller, whatever the element's offset parent is.
      const r = el.getBoundingClientRect(), base = root.getBoundingClientRect()
      const top = r.top - base.top + root.scrollTop
      out.push({ top: top / total, height: r.height / total, you: (you?.getBoundingClientRect().height ?? 0) / total, gi: Number(el.dataset.turnIndex) })
    })
    setBlocks(out)
    const base = root.getBoundingClientRect()
    setHeads(chats ? [...root.querySelectorAll<HTMLElement>('[data-chat-head]')].map((el) => (el.getBoundingClientRect().top - base.top + root.scrollTop) / total) : [])
    setView({ top: root.scrollTop / total, height: root.clientHeight / total, total })
  }, [scroller, chats])
  useLayoutEffect(() => {
    const root = scroller.current
    if (!root) return
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(root)
    root.querySelectorAll('[data-turn-index]').forEach((el) => ro.observe(el))
    // A scroll moves only the shaded view: measuring every turn on every
    // scroll frame thrashed the layout in "all".
    const onScroll = () => {
      const total = Math.max(1, root.scrollHeight)
      setView({ top: root.scrollTop / total, height: root.clientHeight / total, total })
    }
    root.addEventListener('scroll', onScroll, { passive: true })
    return () => { ro.disconnect(); root.removeEventListener('scroll', onScroll) }
  }, [scroller, measure, turns, version])
  const scrollTo = (clientY: number) => {
    const r = box.current?.getBoundingClientRect()
    const root = scroller.current
    if (!r || !root) return
    const f = (clientY - r.top) / r.height
    root.scrollTop = f * root.scrollHeight - root.clientHeight / 2
  }
  const drag = (e: React.PointerEvent) => {
    e.preventDefault()
    scrollTo(e.clientY)
    const move = (ev: PointerEvent) => scrollTo(ev.clientY)
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  // One keyboard path over the same DOM: the map takes focus, the arrows
  // walk the turns (the walked one previews, like a hover), Enter jumps.
  const keys = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Enter' && e.key !== ' ') return
    if (!blocks.length) return
    e.preventDefault()
    const cur = hover ?? blocks.findIndex((b) => b.gi === at)
    if (e.key === 'ArrowDown') setHover(Math.min(blocks.length - 1, cur + 1))
    else if (e.key === 'ArrowUp') setHover(Math.max(0, cur <= 0 ? 0 : cur - 1))
    else {
      const b = blocks[cur >= 0 ? cur : 0]
      if (b) goTo(b.gi)
    }
  }
  return (
    <div className="relative shrink-0 w-[88px] border-l border-border-subtle bg-surface">
      <div ref={box} className="absolute inset-x-8 top-8 bottom-8 cursor-pointer" onPointerDown={drag}
        role="button" tabIndex={0} onKeyDown={keys} onBlur={() => setHover(null)}
        aria-label={t('Chat map. Click or drag to move; arrow keys move between turns, Enter goes to the turn')}>
        {blocks.map((b, bi) => { const i = b.gi; return (
          <div key={i} className="absolute inset-x-0" style={{ top: `${b.top * 100}%`, height: `${Math.max(0.3, b.height * 100)}%` }}
            onMouseEnter={() => setHover(bi)} onMouseLeave={() => setHover((h) => (h === bi ? null : h))}
            onClick={(e) => { e.stopPropagation(); goTo(i) }}>
            <div className="absolute inset-x-0 top-0 rounded-[1px] bg-status-amber/70" style={{ height: `${Math.max(2, (b.you / Math.max(b.height, 1e-9)) * 100)}%`, maxHeight: '100%' }} />
            <div className="absolute inset-x-4 bottom-[1px] rounded-[1px]"
              style={{ top: `${Math.min(98, (b.you / Math.max(b.height, 1e-9)) * 100)}%`, background: i === at ? 'var(--text-secondary)' : 'var(--border-strong)', opacity: 0.55 }} />
            {(turns[i]?.work?.commits.length ?? 0) > 0 && <span className="absolute -left-6 top-0 w-4 h-4 rounded-pill bg-brand" />}
          </div>
        ) })}
        {heads.map((h, i) => <div key={i} className="absolute inset-x-[-6px] h-[2px] pointer-events-none" style={{ top: `${h * 100}%`, background: 'var(--text-tertiary)' }} />)}
        <div className="absolute inset-x-[-4px] rounded-input border border-brand bg-brand-glow pointer-events-none"
          style={{ top: `${view.top * 100}%`, height: `${Math.max(2, view.height * 100)}%` }} />
      </div>
      {hover != null && blocks[hover] && turns[blocks[hover]!.gi] && (
        <div className="absolute right-full mr-8 w-[280px] p-8 rounded-card border border-border-subtle bg-base shadow-lg text-12 text-primary pointer-events-none"
          style={{ top: `calc(${(blocks[hover]?.top ?? 0) * 100}% )` }}>
          <span className="block text-10 font-mono text-tertiary">{t('Turn')}{' '}{turns[blocks[hover]!.gi]!.n} · {turns[blocks[hover]!.gi]!.at} · {words(turns[blocks[hover]!.gi]!.agent)} {t('words of answer')}</span>
          {firstLine(turns[blocks[hover]!.gi]!.user)}
        </div>
      )}
    </div>
  )
}

interface Item { chat: Row; turn: SessionTurn; gi: number; first: boolean }

function MapLook(p: Props) {
  const [prefs, setPrefs] = useState<FocusPrefs>(readFocusPrefs)
  const set = (x: Partial<FocusPrefs>) => { const next = { ...prefs, ...x }; setPrefs(next); storeFocusPrefs(next) }
  const [gear, setGear] = useState(false)
  // The terminal beside the chat (T): the agent's own, or a way to open it.
  const [termOn, setTermOn] = useState(() => readPref('sp-focus-term') === '1')
  const flipTerm = () => setTermOn((v) => { persistPref('sp-focus-term', v ? '0' : '1'); return !v })
  // The list's own filter; it starts with the agent the page had picked.
  const [filter, setFilterState] = useState<FocusFilter>(() => {
    const f = readFilter()
    return p.agent && !f.agents.length ? { ...f, agents: [p.agent] } : f
  })
  const setFilter = (f: FocusFilter) => { setFilterState(f); storeFilter(f) }
  const [filtering, setFiltering] = useState(false)
  const pool = p.pool ?? p.sessions
  const listed = useMemo(() => applyFilter(pool, filter), [pool, filter])
  const all = prefs.scope === 'all'
  // One chat, or every chat in the list — oldest first, read as one.
  const chats = useMemo(() => (all ? listed.slice().reverse() : [p.session]), [all, listed, p.session])
  const q = useSessionTurns(chats)
  const items: Array<Item & { ci: number }> = useMemo(() => {
    const out: Array<Item & { ci: number }> = []
    chats.forEach((c, ci) => {
      const ts = q.data?.[c.id] ?? []
      ts.forEach((it, i) => out.push({ chat: c, turn: it, gi: out.length, first: i === 0, ci }))
    })
    return out
  }, [chats, q.data])

  // "All" draws the chats around the one being read and adds more as the
  // reader nears either end — 270 chats drawn at once took 13 s.
  const [range, setRange] = useState<[number, number]>([0, 1])
  const shown = useMemo(() => items.filter((x) => x.ci >= range[0] && x.ci < range[1]), [items, range])
  const pending = useRef<number | null>(null)
  const anchor = useRef<{ height: number; top: number } | null>(null)
  const turns = useMemo(() => items.map((x) => x.turn), [items])

  const scroller = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLElement>(null)
  const [at, setAt] = useState(0)
  const goTo = useCallback((i: number, smooth = true) => {
    const c = Math.max(0, Math.min(items.length - 1, i))
    setAt(c)
    const ci = items[c]?.ci ?? 0
    if (ci < range[0] || ci >= range[1]) {
      // Far off: draw the chats around it instead, then move there.
      pending.current = c
      setRange([Math.max(0, ci - 1), Math.min(chats.length, ci + 3)])
      return
    }
    scroller.current?.querySelector<HTMLElement>(`[data-turn-index="${c}"]`)?.scrollIntoView({ block: 'start', behavior: smooth ? 'smooth' : 'auto' })
  }, [items, range, chats.length])
  useLayoutEffect(() => {
    const root = scroller.current
    if (pending.current != null) {
      const c = pending.current
      pending.current = null
      root?.querySelector<HTMLElement>(`[data-turn-index="${c}"]`)?.scrollIntoView({ block: 'start' })
    } else if (anchor.current && root) {
      // Chats drawn above: keep the text under the eye where it was.
      root.scrollTop = anchor.current.top + (root.scrollHeight - anchor.current.height)
      anchor.current = null
    }
  }, [range])
  const more = useCallback((side: 'up' | 'down') => {
    const root = scroller.current
    if (side === 'up') {
      if (range[0] <= 0) return
      if (root) anchor.current = { height: root.scrollHeight, top: root.scrollTop }
      setRange(([a, b]) => [Math.max(0, a - 3), b])
    } else if (range[1] < chats.length) {
      setRange(([a, b]) => [a, Math.min(chats.length, b + 3)])
    }
  }, [range, chats.length])
  const topEdge = useRef<HTMLDivElement>(null)
  const bottomEdge = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const root = scroller.current
    if (!root || !all) return
    const io = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) more(e.target === topEdge.current ? 'up' : 'down')
    }, { root, rootMargin: '1200px 0px' })
    if (topEdge.current) io.observe(topEdge.current)
    if (bottomEdge.current) io.observe(bottomEdge.current)
    return () => io.disconnect()
  }, [all, more, shown.length])
  const here = items[at]?.chat ?? p.session

  // Opening "all" lands on the chat that was open; opening one chat, at its top.
  const landed = useRef('')
  useEffect(() => {
    if (!items.length) return
    // Once per chat and scope: a live chat growing a turn must not jump back.
    const key = `${prefs.scope}|${p.session.id}`
    if (landed.current === key) return
    landed.current = key
    const i = Math.max(0, all ? items.findIndex((x) => x.chat.id === p.session.id) : 0)
    const ci = items[i]?.ci ?? 0
    pending.current = i
    setAt(i)
    setRange(all ? [Math.max(0, ci - 1), Math.min(chats.length, ci + 3)] : [0, 1])
  }, [items, all, p.session.id, prefs.scope, chats.length])

  useEffect(() => {
    const root = scroller.current
    if (!root) return
    const io = new IntersectionObserver((entries) => {
      const seen = entries.filter((e) => e.isIntersecting).map((e) => Number((e.target as HTMLElement).dataset.turnIndex))
      if (seen.length) setAt(Math.min(...seen))
    }, { root, rootMargin: '0px 0px -75% 0px' })
    root.querySelectorAll('[data-turn-index]').forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [shown, p.session.id]) // the drawn turns themselves: another chat of the same length is new nodes

  /** The chat before or after the one in view: in "all", scroll to it; in one, open it. */
  const chatIdx = listed.findIndex((s) => s.id === here.id)
  const older = chatIdx >= 0 && chatIdx < listed.length - 1 ? listed[chatIdx + 1] : undefined
  const newer = chatIdx > 0 ? listed[chatIdx - 1] : undefined
  const openChat = (id: string) => {
    if (!all) { p.onPick(id); return }
    const i = items.findIndex((x) => x.chat.id === id)
    if (i >= 0) goTo(i)
  }

  useFocusKeys((e) => {
      if (isTypingTarget(e)) return
      // Keys typed into the agent's terminal beside the chat stay its own.
      if ((e.target as HTMLElement | null)?.closest?.('.xterm')) return
      if (e.key === 'Escape') { e.preventDefault(); if (gear) setGear(false); else leave() }
      else if (e.key === 'j') { e.preventDefault(); goTo(at + 1) }
      else if (e.key === 'k') { e.preventDefault(); goTo(at - 1) }
      else if (e.key === ']' && older) openChat(older.id)
      else if (e.key === '[' && newer) openChat(newer.id)
      else if (e.key === 'c') { e.preventDefault(); set({ drawer: !prefs.drawer }) }
      else if (e.key === 'a') { e.preventDefault(); set({ scope: all ? 'one' : 'all' }) }
      else if (e.key === 't') { e.preventDefault(); flipTerm() }
  })

  const chatN = all ? chats.findIndex((c) => c.id === here.id) + 1 : 0
  // Leaving "all" returns to the chat that was being read, not the one it opened on.
  const leave = () => { if (here.id !== p.session.id) p.onPick(here.id); p.onClose() }
  return (
    <Frame label={here.l1}>
      <header className="relative shrink-0 h-[40px] px-12 flex items-center gap-8 border-b border-border-subtle">
        <IconButton onClick={leave} label={t('Leave focus (Esc)')}><Minimize2 size={13} /></IconButton>
        <IconButton onClick={() => set({ drawer: !prefs.drawer })} label={t('The chats list (C)')} active={prefs.drawer}><Menu size={14} /></IconButton>
        <Segmented label={t('Show')} shape="pill" height={20} value={prefs.scope} onChange={(v) => set({ scope: v })}
          options={[['one', t('one chat'), t('This chat only')], ['all', 'all', t('Every chat in the list, oldest first, as one read (A)')]] as const} />
        <h1 className="min-w-0 flex-1 text-13 font-semibold text-primary truncate">{here.l1 || 'A chat'}</h1>
        <span className="text-11 font-mono text-tertiary tabular-nums whitespace-nowrap">
          {items.length ? (all ? t('chat {chatN} of {length} · turn {v} of {length2}', { chatN, length: chats.length, v: at + 1, length2: items.length }) : t('turn {v} of {length}', { v: at + 1, length: items.length })) : ''}
        </span>
        <IconButton onClick={flipTerm} label={t('The agent\'s terminal beside the chat (T)')} active={termOn}><SquareTerminal size={14} /></IconButton>
        <IconButton onClick={() => setGear((v) => !v)} label={t('Settings')} active={gear}><Settings2 size={14} /></IconButton>
        {gear && <FocusSettings prefs={prefs} set={set} onClose={() => setGear(false)} listTitle={t('Chats list')} />}
      </header>
      <div className="flex-1 min-h-0 flex">
        {prefs.drawer && (
          <aside ref={listRef} className="relative shrink-0 border-r border-border-subtle min-h-0 flex flex-col" style={{ width: prefs.listWidth }}>
            <div className="shrink-0 px-12 pt-8 flex items-center gap-6 text-10 uppercase tracking-wide font-mono text-tertiary">
              {t('Chats ·')}{' '}{listed.length}{listed.length !== pool.length && <span className="normal-case tracking-normal"> {t('of {n}', { n: pool.length })}</span>}
              <span className="ml-auto normal-case tracking-normal">
                <IconButton onClick={() => older && openChat(older.id)} disabled={!older} label={t('The chat before (])')}><ChevronUp size={12} /></IconButton>
                <IconButton onClick={() => newer && openChat(newer.id)} disabled={!newer} label={t('The chat after ([)')}><ChevronDown size={12} /></IconButton>
              </span>
            </div>
            <div className="flex-1 min-h-0"><ChatList sessions={listed} current={here.id} onPick={openChat} size={prefs.listSize}
              tools={<FilterButton open={filtering} filter={filter} onToggle={() => setFiltering((v) => !v)} />}
              below={filtering && <FilterPanel pool={pool} filter={filter} onChange={setFilter} />} /></div>
            <EdgeHandle panel={listRef} value={prefs.listWidth} onWidth={(w) => set({ listWidth: w })} min={220} max={720} />
          </aside>
        )}
        <div ref={scroller} className="flex-1 min-w-0 min-h-0 overflow-y-auto">
          <Column width={prefs.width} onWidth={(w) => set({ width: w })} className="py-32 flex flex-col gap-48">
            {q.isLoading && <p className="text-12 font-mono text-tertiary">{t('Reading')}{' '}{all ? t('{length} chats', { length: chats.length }) : t('the chat')}…</p>}
            {!q.isLoading && !items.length && <p className="text-12 font-mono text-tertiary">{all && !listed.length ? t('The filter leaves no chat. Change it, or clear it, in the list on the left.') : t('No turns.')}</p>}
            {all && range[0] > 0 && <div ref={topEdge} className="text-11 font-mono text-tertiary text-center">{range[0]} {t('older chats above…')}</div>}
            {shown.map((x) => (
              <Fragment key={`${x.chat.id}:${x.turn.n}`}>
                {all && x.first && (
                  <header data-chat-head={x.chat.id} className="flex flex-col gap-2 pt-16 border-t-2 border-border-default">
                    <span className="text-10 font-mono text-tertiary tabular-nums">{fmtDay(x.chat.created_date)} {x.chat.start_time} · {mentionLabel(x.chat)} · {x.chat.turns_n} {t('turns ·')}{' '}{fmtMinutes(x.chat.duration_min)}</span>
                    <h2 className="text-16 font-semibold text-primary leading-snug">{x.chat.l1 || 'A chat'}</h2>
                  </header>
                )}
                <section data-turn-index={x.gi} className="flex flex-col gap-16 scroll-mt-24">
                  <div className="flex items-center gap-8 text-10 font-mono text-tertiary tabular-nums">
                    <span>{t('Turn')}{' '}{x.turn.n} · {x.turn.at}</span><WorkMark turn={x.turn} />
                    <span className="ml-auto">{x.chat.id === p.session.id || !all ? p.star?.(x.turn.n, x.turn.user) : null}</span>
                  </div>
                  <YourMessage text={x.turn.user} size={prefs.size} clamp clampAt={900} clampHeight="16em" />
                  <Answer text={x.turn.agent} size={prefs.size} fold onOpenTask={p.onOpenTask} />
                  {x.turn.work && <WorkLine work={x.turn.work} sessionId={x.chat.id} />}
                </section>
              </Fragment>
            ))}
            {all && range[1] < chats.length && <div ref={bottomEdge} className="text-11 font-mono text-tertiary text-center">{chats.length - range[1]} {t('newer chats below…')}</div>}
            {items.length > 0 && (!all || range[1] >= chats.length) && <p className="text-11 font-mono text-tertiary text-center pb-96">{all ? t('The newest chat ends here.') : t('The end of the chat.')}</p>}
          </Column>
        </div>
        {items.length > 0 && <Minimap scroller={scroller} turns={turns} at={at} goTo={goTo} chats={all} version={shown.length * 1000 + range[0]} />}
        {termOn && <AgentTerminal agentId={here.agent_id} label={here.l1} />}
      </div>
      <footer className="shrink-0 h-24 px-16 flex items-center gap-12 border-t border-border-subtle text-10 font-mono text-tertiary">
        <span>{t('the map on the right: click or drag')}</span><span>{t('j k — turns')}</span><span>{t('[ ] — chats')}</span><span>{t('A — one chat / all')}</span><span>{t('T — terminal')}</span><span>{t('C — the list')}</span><span>{t('Esc — leave')}</span>
      </footer>
    </Frame>
  )
}

/** The agent's terminal as a pane beside the chat, its width dragged at its left edge. */
function AgentTerminal({ agentId, label }: { agentId: string; label: string }) {
  const st = useTerminalStatus().data
  const list = useTerminals(true).data
  const act = useTerminalActions()
  const live = terminalOfAgent(list?.sessions, agentId)
  const pane = useRef<HTMLElement>(null)
  const [w, setW] = useState(() => Math.max(360, Number(readPref('sp-focus-term-w')) || 640))
  const drag = (e: React.PointerEvent) => {
    e.preventDefault()
    const right = pane.current?.getBoundingClientRect().right ?? window.innerWidth
    const move = (ev: PointerEvent) => {
      const nw = Math.round(Math.max(360, Math.min(window.innerWidth - 480, right - ev.clientX)))
      setW(nw)
    }
    // Kept once, when the drag ends — not on every move.
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); setW((v) => { persistPref('sp-focus-term-w', String(v)); return v }) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  const maxW = Math.max(360, window.innerWidth - 480)
  const keys = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    // The handle is the terminal's left edge: left widens it, right narrows.
    const nw = Math.round(Math.max(360, Math.min(maxW, w + (e.key === 'ArrowLeft' ? 24 : -24))))
    setW(nw)
    persistPref('sp-focus-term-w', String(nw))
  }
  return (
    <aside ref={pane} className="relative shrink-0 border-l border-border-default flex flex-col min-h-0" style={{ width: w, background: TERMINAL_GROUND }} aria-label={t('The agent\'s terminal')}>
      <div role="separator" aria-orientation="vertical" aria-label={t('Change the terminal\'s width')}
        aria-valuenow={w} aria-valuemin={360} aria-valuemax={maxW}
        title={t('Drag, or the left and right arrows, to change the width')}
        tabIndex={0} onKeyDown={keys} onPointerDown={drag}
        className="absolute top-0 bottom-0 -left-4 w-8 z-10 cursor-col-resize hover:bg-border-strong/40 focus-visible:bg-brand/40" />
      <div className="shrink-0 h-[28px] px-10 flex items-center gap-6 border-b border-white/10 bg-[var(--term-bar)] text-12 text-[var(--term-text)]">
        {live ? <StateDot state={live.state} size={7} /> : <SquareTerminal size={12} className="text-[var(--term-muted)]" aria-hidden />}
        <span className="truncate">{live ? live.label : 'Terminal'}</span>
        {live && <span className="text-10 font-mono text-[var(--term-muted)]">{STATE_WORD[live.state]}</span>}
      </div>
      <div className="flex-1 min-h-0">
        {!st ? null : !st.enabled ? (
          <div className="h-full bg-base overflow-auto"><TurnOn /></div>
        ) : live ? (
          <Screen key={live.id} sid={live.id} token={st.token} fontSize={st.font_size} scrollback={st.scrollback} editor={st.editor} project={live.project} backend={live.backend} visible autoFocus={false} />
        ) : (
          <div className="h-full flex flex-col items-start justify-center gap-10 p-24 text-[var(--term-soft)]">
            <span className="text-14">{t('This agent has no terminal open.')}</span>
            <span className="text-12 text-[var(--term-muted)] max-w-[420px]">{t('Resume it to open its terminal here, in its own folder, beside the chat.')}</span>
            <button type="button" disabled={act.opening} onClick={() => act.open({ kind: 'resume', agent_id: agentId, label }, { quiet: true })}
              className="inline-flex items-center gap-6 h-[28px] px-12 rounded-pill bg-brand text-12 font-medium text-on-brand hover:opacity-90 disabled:opacity-50">
              <RotateCcw size={12} aria-hidden /> {t('Resume it here')}
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}

/* ---------------------------------------------------------------- router */

export function MapFocus(props: Props) {
  return <MapLook {...props} />
}
