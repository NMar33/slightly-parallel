/**
 * SP Aqua (tk_bbb84183): Slightly Parallel's terminal window, at /term,
 * built from the design round's J (`../design/round3/J.tsx`) on real data.
 *
 * At rest it is an ordinary terminal: a title row (folds with alt+T or a
 * double click), the tab strip of the current workspace with the others
 * folded behind "+N", and the live terminal of the tab in front — the
 * only terminal mounted. Around it, on demand:
 *
 * - the sidebars (alt+[ and alt+]): workspaces, chats and servers on the
 *   left; the chat's messages, pins, branches and stats on the right. In
 *   the app's own window they grow the window outward (the bridge's
 *   `grow`) and the terminal keeps its size and place; in a browser they
 *   open beside the terminal on whichever side the page has room (J's
 *   rule), and the terminal does not move;
 * - the overview (Ctrl+Shift+↑ out, Esc back in): the workspace as still
 *   text tiles, then every workspace — transform and opacity only;
 * - groups, sleep and wake, restore after a restart, detach into another
 *   window, typing ticks — each drawn only when the server has its route.
 *
 * `?detached=<id>` is a window of one chat; `?ws=<project or group>` a
 * window of one workspace.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { ChevronRight, ChevronUp, Keyboard, LayoutGrid, Menu, Minus, PanelLeft, PanelRight, Plus, RotateCcw, Server, SquareTerminal, Sun, X, Zap } from 'lucide-react'

import '../design/aqua.css'
import { Screen } from '../../terminal/Screen'
import { PYWINPTY, useTerminalActions, useTerminalStatus } from '../../../lib/terminal'
import type { MsgMark } from '../../../lib/pins'
import { useMsgMarkActions } from '../../../lib/pins'
import { sendTyping, useAquaActions, useGroups, useRestoreNeeded, useSessions, type RestoreResult } from './api'
import { isNative, openWindow, post } from './bridge'
import {
  LW, RW, chordOf, deriveWorkspaces, detachUrl, foldTabs, groupWs, isAsleep, nextWaiting, parseView, placeSide, projectWs,
  cycleLevel, resolveWs, roleOf, seatBoth, shownOf, stepIn, stepOut, tabsOf, tilesOf, widths, wsIdOf,
  type AquaSession, type Level, type Seats, type Side, type Workspace,
} from './model'
import { AllLevel, GAP, HEAD, PAD, TILE_H, WsLevel } from './overview'
import { Dot, Float, GroupForm, GroupMenu, Item, RestoreCard, RoleIcon, SHOWN_WORD, Swatch, lane, moveTargets } from './parts'
import { LeftSidebar, RightSidebar, type RightTab } from './sidebars'
import { TypingBatcher } from './typing'
import { t, tn } from '../../../i18n/scope/aqua'

type Status = NonNullable<ReturnType<typeof useTerminalStatus>['data']>

const BAR = 34
const BAR_FOLDED = 12
const STRIP = 32
const INSET = 6
/** In a browser, the window stands on the page with this margin. */
const MARGIN = 24
const ACTIVE_KEY = 'sp-aqua-active'
/** A quiet button on the terminal's dark ground, in either theme. */
const ON_TERM = { color: 'var(--term-text)', borderColor: 'var(--term-muted)' }
const MOTION_KEY = 'sp-aqua-motion'
/** The levels' breadcrumb row. */
const CRUMB = 28

const store = {
  get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } },
}

function readMotion(): boolean {
  try {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return true
  } catch { /* no matchMedia */ }
  return store.get(MOTION_KEY) === 'instant'
}

/** The page without the app's sidebar and top bar: a terminal window of its own. */
export function TermApp() {
  const st = useTerminalStatus()
  const line = (text: ReactNode) => (
    <div className="aq fixed inset-0 flex items-center justify-center p-24" data-v="j" style={{ background: 'var(--bg-base)' }}>
      <p role="status" className="m-0 text-13" style={{ color: 'var(--text-secondary)' }}>{text}</p>
    </div>
  )
  if (st.isError) return line(t('Slightly Parallel did not answer: {error}', { error: st.error instanceof Error ? st.error.message : String(st.error) }))
  if (!st.data) return line('')
  if (st.data.supported === false) {
    return line(<>{t('The terminal needs the pywinpty package. Install it, then restart Slightly Parallel:')} <code className="font-mono px-4 rounded-[4px]" style={{ background: 'var(--bg-hover)' }}>{PYWINPTY}</code></>)
  }
  if (!st.data.enabled) {
    return line(<>{t('The terminal is off. Turn it on:')} <code className="font-mono px-4 rounded-[4px]" style={{ background: 'var(--bg-hover)' }}>python3 sp.py terminal on</code></>)
  }
  return <AquaWindow status={st.data} />
}

function useViewport() {
  const read = () => ({ w: typeof window !== 'undefined' ? window.innerWidth : 1280, h: typeof window !== 'undefined' ? window.innerHeight : 800 })
  const [vp, setVp] = useState(read)
  useEffect(() => {
    const on = () => setVp(read())
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return vp
}

type Menu =
  | null
  | { kind: 'tab'; id: string; x: number; form?: 'group' | 'rename' }
  | { kind: 'others' }
  | { kind: 'new' }
  | { kind: 'group'; ws: string }
  | { kind: 'keys' }

function AquaWindow({ status }: { status: Status }) {
  const location = useLocation()
  const view = useMemo(() => parseView(location.search), [location.search])
  const { sessions, loaded, canSleep } = useSessions()
  const groupsQ = useGroups()
  const groups = groupsQ.data ?? null
  const canGroup = Array.isArray(groupsQ.data)
  const projects = useMemo(() => Object.keys(status.projects ?? {}), [status.projects])
  const workspaces = useMemo(() => deriveWorkspaces(sessions, projects, groups), [sessions, projects, groups])
  const act = useAquaActions()
  const termAct = useTerminalActions()
  const marks = useMsgMarkActions()
  const [native] = useState(isNative)
  const vp = useViewport()

  const fixedChat = view.detached
  const fixedWs = view.ws ? resolveWs(view.ws, workspaces) : ''
  const kind: 'main' | 'ws' | 'chat' = fixedChat ? 'chat' : fixedWs ? 'ws' : 'main'

  /* ------------------------------------------------ which terminal is in front */
  const [picked, setPicked] = useState(() => fixedChat || store.get(ACTIVE_KEY) || '')
  const [wsSel, setWsSel] = useState('')
  const byId = useMemo(() => new Map(sessions.map((s) => [s.id, s])), [sessions])
  const pickedS = byId.get(picked)
  // At first: the workspace of a chat waiting on you, else of the newest terminal.
  const firstWs = useMemo(() => {
    const all = workspaces.flatMap((w) => w.sessions.map((s) => ({ w, s })))
    const pick = all.find((x) => shownOf(x.s) === 'waiting') ?? all.sort((a, b) => (b.s.created || '').localeCompare(a.s.created || ''))[0]
    return pick?.w.id ?? workspaces[0]?.id ?? ''
  }, [workspaces])
  const ws = fixedWs || wsSel || (pickedS ? wsIdOf(pickedS, groups) : '') || firstWs
  const wsObj = workspaces.find((w) => w.id === ws)
  const active: AquaSession | undefined = kind === 'chat'
    ? byId.get(fixedChat)
    : pickedS && wsIdOf(pickedS, groups) === ws ? pickedS : tabsOf(wsObj)[0]

  const [level, setLevel] = useState<Level>('chat')
  const [settled, setSettled] = useState(true)
  useEffect(() => {
    if (level !== 'chat') { setSettled(false); return }
    const h = setTimeout(() => setSettled(true), 260)
    return () => clearTimeout(h)
  }, [level])
  const [folded, setFolded] = useState(false)
  const unfoldedAt = useRef(0)
  const [instant, setInstantState] = useState(readMotion)
  const setInstant = (v: boolean) => { setInstantState(v); store.set(MOTION_KEY, v ? 'instant' : 'fluid') }
  const [menu, setMenu] = useState<Menu>(null)
  const [rtab, setRtab] = useState<RightTab>('messages')
  /** An ended terminal the operator chose to open a plain shell in. */
  const [reopened, setReopened] = useState('')
  const [flashText, setFlash] = useState<{ text: string; n: number } | null>(null)
  const flash = useCallback((text: string) => setFlash((f) => ({ text, n: (f?.n ?? 0) + 1 })), [])
  useEffect(() => {
    if (!flashText) return
    const h = setTimeout(() => setFlash(null), 2600)
    return () => clearTimeout(h)
  }, [flashText])

  /** The keyboard back to the terminal, after any action of the chrome. */
  const refocus = useCallback(() => {
    setTimeout(() => document.querySelector<HTMLTextAreaElement>('.aqua-screen .xterm-helper-textarea')?.focus(), 0)
  }, [])

  // `fresh`: a terminal just opened, which the list read before it does not have yet.
  const go = useCallback((id: string, fresh?: AquaSession) => {
    const s = byId.get(id) ?? fresh
    if (!s) return
    if (kind === 'chat' && id !== fixedChat) return
    if (kind === 'ws' && wsIdOf(s, groups) !== fixedWs) { openWindow(detachUrl('chat', id)); return }
    setPicked(id)
    setWsSel(wsIdOf(s, groups))
    setLevel('chat')
    setMenu(null)
    if (kind === 'main') store.set(ACTIVE_KEY, id)
    refocus()
  }, [byId, kind, fixedChat, fixedWs, groups, refocus])

  const goWs = useCallback((id: string, to: Level = 'chat') => {
    if (fixedWs || kind === 'chat') return
    const w = workspaces.find((x) => x.id === id)
    setWsSel(id)
    const first = tabsOf(w)[0]
    if (first) setPicked(first.id)
    setMenu(null)
    setLevel(to)
    if (to === 'chat') refocus()
  }, [fixedWs, kind, workspaces, refocus])

  const out = () => { if (kind !== 'chat') { setLevel((l) => stepOut(l, kind === 'ws')); (document.activeElement as HTMLElement | null)?.blur?.() } }
  const into = () => setLevel((l) => { const n = stepIn(l); if (n === 'chat') refocus(); return n })
  const cycle = () => { if (kind === 'chat') return; const n = cycleLevel(level, kind === 'ws'); setLevel(n); if (n === 'chat') refocus(); else (document.activeElement as HTMLElement | null)?.blur?.() }

  /* -------------------------------------------------------------- geometry */
  const [open, setOpen] = useState({ left: false, right: false })
  const [seats, setSeats] = useState<Seats>({ left: null, right: null })
  const [slide, setSlide] = useState(0)
  const sides = kind === 'chat' ? { left: false, right: false } : open
  const at: Seats = native ? { left: sides.left ? 'left' : null, right: sides.right ? 'right' : null } : { left: sides.left ? seats.left : null, right: sides.right ? seats.right : null }
  const { lw, rw } = widths(at)
  // In the app's window the terminal keeps its width while the window grows:
  // its width is taken from the window only once the window has answered.
  const [nativeW, setNativeW] = useState(vp.w)
  const lwrw = useRef({ lw, rw })
  lwrw.current = { lw, rw }
  const growTurn = useRef(0)
  useEffect(() => { if (native) setNativeW(Math.max(320, vp.w - lwrw.current.lw - lwrw.current.rw)) }, [native, vp.w])
  const termW = native ? nativeW : Math.max(360, Math.min(1000, vp.w - 2 * MARGIN))
  const termX = native ? lw : Math.round((vp.w - termW) / 2) + slide
  const frameH = native ? vp.h : vp.h - 2 * MARGIN
  const bar = folded ? BAR_FOLDED : BAR
  const strip = kind === 'chat' ? 0 : STRIP
  const bodyH = Math.max(120, frameH - bar - strip - (native ? 0 : 2))

  function toggle(side: Side, on = !sides[side]) {
    if (kind === 'chat') return
    const other: Side = side === 'left' ? 'right' : 'left'
    const width = side === 'left' ? LW : RW
    if (native) {
      setOpen((o) => ({ ...o, [side]: on }))
      post({ op: 'grow', left: side === 'left' ? (on ? width : -width) : 0, right: side === 'right' ? (on ? width : -width) : 0 })
      // A window that cannot grow (maximised, at the screen's edge) never
      // answers with a resize: the terminal then gives up the room itself.
      // Only the last toggle may do that, and with the sidebars as they are
      // then: a sidebar opened and closed again inside the wait leaves the
      // window at its first width, and the first toggle's check would take
      // that for "no answer" and shrink the terminal by the closed panel.
      const before = window.innerWidth
      const turn = ++growTurn.current
      setTimeout(() => {
        if (growTurn.current !== turn || window.innerWidth !== before) return
        setNativeW(Math.max(320, window.innerWidth - lwrw.current.lw - lwrw.current.rw))
      }, 500)
      refocus()
      return
    }
    if (!on) {
      setOpen((o) => ({ ...o, [side]: false }))
      setSeats((s) => ({ ...s, [side]: null }))
      if (slide && !sides[other]) setSlide(0)
      refocus()
      return
    }
    const x = termX
    const p = placeSide(x, termW, vp.w, at, side)
    if (p.slide && sides[other]) {
      const seat = seatBoth(x, termW, vp.w)
      if (seat) { setSeats(seat); setOpen({ left: true, right: true }); flash(t('Both sidebars seated where the screen has room; the terminal and the toggles stay')); refocus(); return }
    }
    if (p.pick !== side) flash(side === 'left' ? t('No room on the left: the sidebar opens on the right; the terminal and the toggles stay') : t('No room on the right: the sidebar opens on the left; the terminal and the toggles stay'))
    if (p.slide) { setSlide((v) => v + p.slide); flash(t('No room on either side: the window moved in')) }
    setSeats((s) => ({ ...s, [side]: p.pick }))
    setOpen((o) => ({ ...o, [side]: true }))
    refocus()
  }

  /* ------------------------------------------------------------- the title */
  const title = active ? (kind === 'chat' ? `${active.label} — ${t('from')} ${wsObj?.name ?? active.project}` : `${active.label} — ${wsObj?.name ?? ''}`) : 'SP Aqua'
  useEffect(() => {
    document.title = title
    post({ op: 'title', text: title })
  }, [title])

  /* ------------------------------------------------------------- typing */
  const typing = useMemo(() => new TypingBatcher(sendTyping), [])
  useEffect(() => {
    const away = () => void typing.flush()
    window.addEventListener('pagehide', away)
    return () => { window.removeEventListener('pagehide', away); void typing.flush() }
  }, [typing])

  /* ------------------------------------------------------------- restore */
  const restoreQ = useRestoreNeeded()
  const [restoreOut, setRestoreOut] = useState<RestoreResult[] | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [restoreShut, setRestoreShut] = useState(false)
  const restoreRows = restoreQ.data?.sessions ?? []
  const showRestore = kind === 'main' && !restoreShut && ((restoreQ.data?.needed ?? 0) > 0 || restoreOut !== null)
  const runRestore = async () => { setRestoring(true); const r = await act.restore(); setRestoring(false); setRestoreOut(r ?? []) }

  /* --------------------------------------------------------- the actions */
  const projectHere = wsObj?.kind === 'project' ? wsObj.key : active?.project || wsObj?.sessions[0]?.project || projects[0] || ''
  const groupHere = wsObj?.kind === 'group' ? wsObj.key : ''
  const newTerminal = async (role: 'chat' | 'server' | 'shell') => {
    setMenu(null)
    const req = role === 'chat'
      ? { kind: 'shell' as const, project: projectHere, label: status.agent, command: status.agent, role, group: groupHere }
      : { kind: 'shell' as const, project: projectHere, label: role === 'server' ? t('server') : projectHere || t('shell'), role, group: groupHere }
    const s = await act.open(req)
    if (s) go(s.id, s)
  }
  const sleepOne = async (s: AquaSession, asleep: boolean) => { await (asleep ? act.sleep(s.id) : act.wake(s.id)); refocus() }
  const sleepWs = async (w: Workspace, asleep: boolean) => {
    const targets = w.sessions.filter((s) => roleOf(s) !== 'server' && s.state !== 'ended' && isAsleep(s) !== asleep)
    for (const s of targets) await (asleep ? act.sleep(s.id) : act.wake(s.id))
    flash(asleep ? tn(targets.length, '{n} chat put to sleep; servers keep running', '{n} chats put to sleep; servers keep running') : tn(targets.length, '{n} chat woken', '{n} chats woken'))
  }
  const detachChat = (id: string) => { setMenu(null); openWindow(detachUrl('chat', id)) }
  const detachWs = (id: string) => { setMenu(null); openWindow(detachUrl('ws', id)) }
  const resume = async (agentId: string) => {
    const s = await act.open({ kind: 'resume', agent: agentId, role: 'chat' })
    if (s) go(s.id, s)
  }
  const fork = async (m: MsgMark) => {
    const s = await act.open({ kind: 'shell', project: m.project, label: t('fork of {name}', { name: active?.label ?? m.agent_id }), command: m.command, role: 'chat', group: groupHere })
    if (s) { marks.setState(m.target, 'started'); go(s.id, s) }
  }

  /* -------------------------------------------------------------- keys */
  const hidden = useCallback((_sid: string) => false, [])
  const keys: Record<string, (e: KeyboardEvent) => boolean | void> = {
    'mod+shift+ArrowUp': () => out(),
    'mod+shift+ArrowDown': () => into(),
    'alt+BracketLeft': () => toggle('left'),
    'alt+BracketRight': () => toggle('right'),
    'alt+KeyT': () => { setFolded((f) => !f); refocus() },
    'alt+KeyW': () => { const n = nextWaiting(kind === 'ws' ? workspaces.filter((w) => w.id === fixedWs) : workspaces, active?.id ?? '', hidden); if (n) go(n); else flash(t('No chat is waiting on you')) },
    'alt+KeyN': () => { if (kind !== 'chat') setMenu({ kind: 'new' }) },
    'alt+Slash': () => setMenu({ kind: 'keys' }),
    'alt+shift+Slash': () => setMenu({ kind: 'keys' }),
    Escape: () => {
      if (menu) { setMenu(null); refocus(); return }
      if (level !== 'chat') { into(); return }
      return false
    },
  }
  const strip_ = foldTabs(workspaces, ws, hidden)
  strip_.tabs.slice(0, 9).forEach((s, i) => { keys[`alt+Digit${i + 1}`] = () => go(s.id) })
  const keysRef = useRef(keys)
  keysRef.current = keys
  useEffect(() => {
    // Capture: the terminal takes every key it sees, so the window's chords are read before it.
    const onKey = (e: KeyboardEvent) => {
      const f = keysRef.current[chordOf(e)]
      if (!f || e.isComposing) return
      if (f(e) === false) return
      e.preventDefault()
      e.stopPropagation()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [])

  // The title row moves the app's window; a double click folds it. Folded,
  // it is a thin row with the title in small type: one click unfolds it, the
  // sidebar toggles sit in the tab strip, and the strip moves the window.
  const onBarDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest('button,input,[data-nodrag]') || e.button !== 0) return
    post({ op: 'drag' })
  }

  /* ---------------------------------------------------------- the strip */
  const tabRefs = useRef(new Map<string, HTMLButtonElement>())
  const openTabMenu = (id: string, el: HTMLElement) => {
    const frame = el.closest('[data-aqua-frame]')?.getBoundingClientRect()
    setMenu({ kind: 'tab', id, x: el.getBoundingClientRect().left - (frame?.left ?? 0) })
  }
  const waitingHere = wsObj ? wsObj.sessions.filter((s) => shownOf(s) === 'waiting').length : 0
  const stripEl = kind === 'chat' ? null : (
    <div className={`shrink-0 flex items-end gap-2 px-6 min-w-0 relative ${native && folded ? 'aq-app-drag' : ''}`} style={{ height: STRIP, background: 'var(--r2-strip)', borderBottom: '1px solid var(--aq-line)', paddingLeft: folded ? 24 : undefined, paddingRight: folded ? 24 : undefined }}>
      <div className="flex items-end gap-1 min-w-0 overflow-x-auto overflow-y-hidden r2-tabs" role="tablist" aria-label={t('Chats')}
        onKeyDown={(e) => {
          if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
          const list = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')]
          const i = list.indexOf(document.activeElement as HTMLElement)
          list[(i + (e.key === 'ArrowRight' ? 1 : -1) + list.length) % list.length]?.focus()
          e.preventDefault()
        }}>
        {strip_.tabs.map((s, i) => {
          const on = s.id === active?.id
          const dim = on && level !== 'chat'
          const server = roleOf(s) === 'server'
          return (
            <button key={s.id} ref={(el) => { if (el) tabRefs.current.set(s.id, el); else tabRefs.current.delete(s.id) }} type="button" role="tab" aria-selected={on} data-nodrag aria-label={`${s.label} · ${SHOWN_WORD[shownOf(s)]}`}
              onClick={() => go(s.id)}
              onContextMenu={(e) => { e.preventDefault(); openTabMenu(s.id, e.currentTarget) }}
              onKeyDown={(e) => { if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); openTabMenu(s.id, e.currentTarget) } }}
              title={`${s.label} · ${SHOWN_WORD[shownOf(s)]}${i < 9 ? ` · alt+${i + 1}` : ''}\n${t('Right-click: the tab menu')}`}
              className={`h-[26px] px-10 inline-flex items-center gap-6 text-12 rounded-t-[6px] max-w-[190px] shrink-0 ${server && i > 0 && roleOf(strip_.tabs[i - 1]!) !== 'server' ? 'ml-8' : ''}`}
              style={{
                background: dim ? 'var(--aq-hover)' : on ? 'var(--aq-term-bg)' : undefined,
                color: dim ? 'var(--aq-ink)' : on ? 'var(--aq-term-fg)' : 'var(--aq-ink2)',
                boxShadow: on ? 'inset 0 2px 0 var(--brand)' : wsObj?.kind === 'group' ? `inset 0 -2px 0 ${lane(wsObj.color)}` : undefined,
                opacity: isAsleep(s) ? 0.6 : 1,
              }}>
              <Dot s={s} /><span className="truncate">{s.label}</span><RoleIcon s={s} />
            </button>
          )
        })}
        {!strip_.tabs.length && <span className="self-center px-8 text-12 aq-ink3">{t('No terminal here yet.')}</span>}
      </div>
      {kind === 'main' && strip_.folded.length > 0 && (
        <span className="self-center relative ml-4 shrink-0">
          <button type="button" data-nodrag className="aq-btn line !h-[20px] text-11" aria-expanded={menu?.kind === 'others'} aria-haspopup="menu"
            onClick={() => setMenu(menu?.kind === 'others' ? null : { kind: 'others' })} title={t('The other workspaces, folded')}>
            +{strip_.folded.length}
            {strip_.anyWaiting && <span className="w-[6px] h-[6px] rounded-full" style={{ background: 'var(--aq-wait)' }} aria-label={t('your turn')} />}
          </button>
          {menu?.kind === 'others' && (
            <Float label={t('The other workspaces, folded')} className="top-[24px] left-0 w-[280px]">
              {strip_.folded.map(({ ws: w, count, waiting }, i) => (
                <div key={w.id} className="flex items-center">
                  <button type="button" role="menuitem" autoFocus={i === 0} data-nodrag className="aq-row h-[28px] px-8 text-12 flex-1 min-w-0" onClick={() => goWs(w.id)}>
                    <Swatch w={w} />
                    <span className="truncate" style={{ color: 'var(--aq-ink)' }}>{w.name}</span>
                    {w.kind === 'group' && <span className="aq-chip">{t('group')}</span>}
                    <span className="ml-auto font-mono text-10 aq-ink3">{count}</span>
                    {waiting > 0 && <span className="w-[6px] h-[6px] rounded-full shrink-0" style={{ background: 'var(--aq-wait)' }} aria-label={t('your turn')} />}
                  </button>
                  {w.kind === 'group' && <button type="button" data-nodrag className="aq-btn icon shrink-0" aria-label={`${t('Group')} ${w.name}`} onClick={() => setMenu({ kind: 'group', ws: w.id })}><Menu size={11} /></button>}
                </div>
              ))}
            </Float>
          )}
        </span>
      )}
      <span className="self-center relative shrink-0">
        <button type="button" data-nodrag className="aq-btn icon" aria-label={t('New terminal (alt+N)')} title={t('New terminal (alt+N)')} aria-haspopup="menu" aria-expanded={menu?.kind === 'new'}
          onClick={() => setMenu(menu?.kind === 'new' ? null : { kind: 'new' })}><Plus size={13} /></button>
        {menu?.kind === 'new' && (
          <Float label={t('New terminal')} className="top-[24px] left-0 w-[260px]">
            <span className="aq-label px-6 py-4">{projectHere || t('no project')}{groupHere ? ` · ${wsObj?.name}` : ''}</span>
            <Item autoFocus onClick={() => void newTerminal('chat')}><Plus size={12} />{t('New chat ({agent})', { agent: status.agent })}</Item>
            <Item onClick={() => void newTerminal('shell')}><SquareTerminal size={12} />{t('Shell')}</Item>
            <Item onClick={() => void newTerminal('server')}><Server size={12} />{t('New server')}</Item>
          </Float>
        )}
      </span>
    </div>
  )

  /* ----------------------------------------------------------- the body */
  const dur = instant ? 0 : 200
  const cols = termW >= 900 ? 3 : 2
  const tiles = tilesOf(wsObj)
  const tileIndex = Math.max(0, tiles.findIndex((s) => s.id === active?.id))
  const tileW = (termW - 2 * PAD - (cols - 1) * GAP) / cols
  const zoomTo = `translate(${PAD + (tileIndex % cols) * (tileW + GAP)}px, ${CRUMB + PAD + HEAD + GAP + Math.floor(tileIndex / cols) * (TILE_H + GAP)}px) scale(${tileW / termW})`
  const showLevels = level !== 'chat' || !settled
  const terminal = active ? (
    isAsleep(active) ? (
      <div className="h-full flex flex-col items-center justify-center gap-10" style={{ background: 'var(--term-ground)', color: 'var(--term-text)' }}>
        <span className="text-13">{t('{name} is asleep: the agent is stopped, the chat is kept.', { name: active.label })}</span>
        {canSleep && <button type="button" className="aq-btn solid" onClick={() => void sleepOne(active, false)}><Sun size={12} />{t('Wake')}</button>}
      </div>
    ) : active.state === 'ended' && reopened !== active.id ? (
      // Attaching to an ended terminal would start a bare shell in it, and its
      // agent would not come back: waking it runs what it ran.
      <div className="h-full flex flex-col items-center justify-center gap-10" style={{ background: 'var(--term-ground)', color: 'var(--term-text)' }}>
        <span className="text-13">{t('{name} ended.', { name: active.label })}</span>
        <span className="flex gap-6">
          {canSleep && <button type="button" className="aq-btn solid" onClick={() => void sleepOne(active, false)}><RotateCcw size={12} />{t('Start it again')}</button>}
          <button type="button" className="aq-btn line" style={ON_TERM} onClick={() => { setReopened(active.id); refocus() }}><SquareTerminal size={12} />{t('Open a shell in it')}</button>
          <button type="button" className="aq-btn line" style={ON_TERM} onClick={() => void act.close(active.id)}><X size={12} />{t('Close the terminal')}</button>
        </span>
      </div>
    ) : (
      <Screen key={active.id} sid={active.id} token={status.token} fontSize={status.font_size} scrollback={status.scrollback} editor={status.editor}
        project={active.project} taskId={active.task_id} backend={active.backend} visible autoFocus={level === 'chat'}
        onInput={() => typing.tick(active.id)}
        onZoom={(d) => void termAct.setting({ 'terminal.font_size': Math.max(10, Math.min(22, status.font_size + d)) })} />
    )
  ) : (
    <div className="h-full flex flex-col items-center justify-center gap-10" style={{ background: 'var(--term-ground)', color: 'var(--term-muted)' }}>
      <span className="text-13">{!loaded ? '' : kind === 'chat' ? t('This terminal is gone.') : t('No terminal in this workspace.')}</span>
      {loaded && kind !== 'chat' && <button type="button" className="aq-btn solid" onClick={() => void newTerminal('chat')}><Plus size={12} />{t('New chat ({agent})', { agent: status.agent })}</button>}
    </div>
  )
  const body = (
    <div className="relative min-h-0 overflow-hidden" style={{ width: termW, height: bodyH }} data-level={level}>
      {kind !== 'chat' && (
        <div className="absolute inset-0" style={{ background: 'var(--r2-over)', opacity: level === 'chat' ? 0 : 1, transition: `opacity ${dur}ms var(--aq-ease)`, pointerEvents: level === 'chat' ? 'none' : 'auto', visibility: showLevels ? 'visible' : 'hidden' }}
          aria-hidden={level === 'chat'}>
          <div className="absolute inset-0 flex flex-col">
            <nav className="shrink-0 flex items-center gap-6 px-12 text-12" style={{ height: CRUMB }} aria-label={t('Where you are')}>
              {kind === 'main' && <button type="button" data-nodrag className="aq-btn" data-on={level === 'all'} onClick={() => setLevel('all')}>{t('All workspaces')}</button>}
              {kind === 'main' && <ChevronRight size={12} className="aq-ink3" />}
              <button type="button" data-nodrag className="aq-btn" data-on={level === 'ws'} style={{ opacity: level === 'all' ? 0.55 : 1 }} onClick={() => setLevel('ws')}>{wsObj?.name}</button>
              <ChevronRight size={12} className="aq-ink3" style={{ opacity: 0.55 }} />
              <button type="button" data-nodrag className="aq-btn" style={{ opacity: 0.55 }} onClick={() => { setLevel('chat'); refocus() }}>{active?.label ?? '—'}</button>
              <span className="ml-auto text-10 aq-ink3 font-mono">Esc {t('back to the terminal')}</span>
            </nav>
            <div className="flex-1 min-h-0 relative">
              <div className="absolute inset-0" style={{ transform: level === 'all' ? 'scale(0.94)' : 'none', opacity: level === 'all' ? 0 : 1, transition: `transform ${dur}ms var(--aq-ease), opacity ${dur}ms`, pointerEvents: level === 'ws' ? 'auto' : 'none' }}>
                {showLevels && <WsLevel ws={wsObj} current={active?.id ?? ''} on={level === 'ws'} cols={cols} canSleep={canSleep}
                  onChat={go} onWake={(id) => { const s = byId.get(id); if (s) void sleepOne(s, false) }}
                  onSleepWs={(a) => { if (wsObj) void sleepWs(wsObj, a) }} onDetach={() => detachWs(ws)}
                  onMenu={wsObj?.kind === 'group' && canGroup ? () => setMenu({ kind: 'group', ws }) : undefined} />}
              </div>
              {kind === 'main' && (
                <div className="absolute inset-0" style={{ transform: level === 'all' ? 'none' : 'scale(1.05)', opacity: level === 'all' ? 1 : 0, transition: `transform ${dur}ms var(--aq-ease), opacity ${dur}ms`, pointerEvents: level === 'all' ? 'auto' : 'none' }}>
                  {showLevels && <AllLevel workspaces={workspaces} current={active?.id ?? ''} cols={cols} onWs={(id) => goWs(id, 'ws')} onChat={go} />}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      <div className="absolute inset-0 origin-top-left aqua-screen" style={{
        transform: level === 'chat' ? 'none' : zoomTo, opacity: level === 'chat' ? 1 : 0,
        transition: `transform ${dur}ms var(--aq-ease), opacity ${Math.round(dur * 0.7)}ms`, pointerEvents: level === 'chat' ? 'auto' : 'none',
        willChange: instant || settled ? undefined : 'transform', background: 'var(--term-ground)',
      }}>
        {terminal}
      </div>
    </div>
  )

  /* ---------------------------------------------------------- the frame */
  const leftSeated = (['right', 'left'] as const).filter((k) => sides[k] && at[k] === 'left')
  const rightSeated = (['right', 'left'] as const).filter((k) => sides[k] && at[k] === 'right')
  const panel = (k: Side) => (
    <aside key={k} className={`shrink-0 ${instant ? '' : k === 'left' ? 'r2-side-l' : 'r2-side-r'}`} aria-label={k === 'left' ? t('Left sidebar') : t('Right sidebar')}
      style={{ width: k === 'left' ? LW : RW, height: strip + bodyH, background: 'var(--aq-panel)', borderLeft: '1px solid var(--aq-line)', borderRight: '1px solid var(--aq-line)' }}>
      {k === 'left'
        ? <LeftSidebar workspaces={workspaces} ws={ws} active={active?.id ?? ''} canSleep={canSleep} onChat={go} onWs={(id) => goWs(id)}
            onSleep={(s, a) => void sleepOne(s, a)} onSleepWs={(w, a) => void sleepWs(w, a)} onNew={(r) => void newTerminal(r)}
            onGroupMenu={(w) => setMenu({ kind: 'group', ws: w.id })} />
        : <RightSidebar s={active} tab={rtab} setTab={setRtab} workspaces={workspaces} onChat={go} onResume={(a) => void resume(a)} onFork={(m) => void fork(m)} />}
    </aside>
  )
  const lt = lw + INSET
  const rt = lw + termW - INSET - 24
  const toggleBtn = (side: Side) => {
    const on = sides[side]
    const away = !native && on && at[side] !== side
    const label = side === 'left' ? t('Left sidebar') : t('Right sidebar')
    const hint = side === 'left'
      ? (away ? t('Left sidebar (alt+[) — opened on the right: no room on the left') : t('Left sidebar (alt+[)'))
      : (away ? t('Right sidebar (alt+]) — opened on the left: no room on the right') : t('Right sidebar (alt+])'))
    const x = side === 'left' ? lt : rt
    // Folded: a small rectangle at the end of the tab strip, half as wide.
    if (folded) return (
      <button type="button" data-nodrag data-toggle={side} data-in="strip" aria-pressed={on} aria-label={label} title={hint}
        className="absolute rounded-[2px] hover:opacity-100"
        style={{ left: side === 'left' ? 6 : termW - 6 - 12, top: Math.round((STRIP - 14) / 2), width: 12, height: 14, opacity: on ? 1 : 0.6,
          background: on ? 'var(--brand)' : 'transparent', border: `1.5px solid ${on ? 'var(--brand)' : 'var(--text-tertiary)'}` }} onClick={() => toggle(side)} />
    )
    return (
      <button type="button" data-nodrag data-toggle={side} aria-pressed={on} aria-label={label} title={hint}
        className="absolute inline-flex items-center justify-center rounded-[6px] hover:bg-[var(--aq-hover)]"
        style={{ left: x, top: 5, width: 24, height: 24 }} onClick={() => toggle(side)}>
        {side === 'left' ? <PanelLeft size={14} style={{ color: on ? 'var(--brand)' : undefined }} /> : <PanelRight size={14} style={{ color: on ? 'var(--brand)' : undefined }} />}
        {away && <span className={`absolute text-11 font-semibold ${side === 'left' ? '-right-10' : '-left-10'}`} style={{ color: 'var(--brand)' }} aria-hidden>{side === 'left' ? '▸' : '◂'}</span>}
      </button>
    )
  }

  const tabMenuS = menu?.kind === 'tab' ? byId.get(menu.id) : undefined
  const groupMenuWs = menu?.kind === 'group' ? workspaces.find((w) => w.id === menu.ws) : undefined

  const frame = (
    <div data-aqua-frame className={`absolute flex flex-col ${native ? '' : 'r2-win'}`} role="dialog" aria-label={`${t('Window')}: ${kind === 'main' ? 'SP Aqua' : title}`}
      data-folded={folded || undefined}
      style={native ? { left: 0, top: 0, width: lw + termW + rw, height: frameH } : { left: termX - lw, top: MARGIN, height: frameH }}>
      <div className={`flex flex-col overflow-hidden ${native ? 'h-full' : 'rounded-[8px] h-full'}`} style={native ? undefined : {
        boxShadow: 'var(--shadow-lg)', border: '1px solid var(--border-strong)', borderTop: kind !== 'main' && wsObj ? `3px solid ${lane(wsObj.color)}` : undefined,
      }}>
        {/* the title row: folds to a 12px strip */}
        <div className={`relative shrink-0 select-none ${native ? 'aq-app-drag' : ''}`} style={{ height: bar, background: 'var(--r2-bar)', color: 'var(--r2-bar-ink)', transition: instant ? undefined : 'height 120ms var(--aq-ease)', borderTop: native && kind !== 'main' && wsObj ? `3px solid ${lane(wsObj.color)}` : undefined }}
          onPointerDown={onBarDown} onDoubleClick={(e) => { if (!(e.target as HTMLElement).closest('button') && Date.now() - unfoldedAt.current > 600) { setFolded(!folded); refocus() } }}>
          {kind !== 'chat' && !folded && toggleBtn('left')}
          <span className="absolute truncate text-center pointer-events-none" style={{ left: lw + (folded ? 40 : 110), width: Math.max(40, termW - (folded ? 80 : 220)), top: 0, lineHeight: `${bar}px`, fontSize: folded ? 9 : 13, fontWeight: folded ? 500 : 600, color: folded ? 'var(--text-tertiary)' : 'var(--r2-bar-ink)' }}>
            {title}
          </span>
          {!folded && (
            <span className="absolute flex items-center gap-2" style={{ right: rw + (kind === 'chat' ? 8 : 36), top: 5 }}>
              {kind !== 'chat' && (
                <button type="button" data-nodrag className="aq-btn" aria-pressed={level !== 'chat'} onClick={cycle}
                  title={t('Workspaces: the chat, its workspace, every workspace (Ctrl+Shift+↑)')} aria-label={t('Workspaces')}>
                  <LayoutGrid size={13} />{wsObj && <span className="text-11 max-w-[120px] truncate">{wsObj.name}</span>}
                  {waitingHere > 0 && <span className="text-11 font-semibold" style={{ color: 'var(--aq-wait)' }}>● {waitingHere}</span>}
                </button>
              )}
              <button type="button" data-nodrag className="aq-btn icon" aria-label={t('Keys')} title={t('Keys (alt+/)')} onClick={() => setMenu({ kind: 'keys' })}><Keyboard size={13} /></button>
              <button type="button" data-nodrag className="aq-btn icon" aria-pressed={instant} aria-label={instant ? t('Motion: instant') : t('Motion: fluid')} title={instant ? t('Motion: instant') : t('Motion: fluid')} onClick={() => { setInstant(!instant); refocus() }}><Zap size={13} /></button>
              <button type="button" data-nodrag className="aq-btn icon" aria-label={t('Fold the title row (alt+T)')} title={t('Fold the title row (alt+T)')} onClick={() => { setFolded(true); refocus() }}><ChevronUp size={14} /></button>
              {native && <button type="button" data-nodrag className="aq-btn icon" aria-label={t('Minimise')} title={t('Minimise')} onClick={() => post({ op: 'minimize' })}><Minus size={13} /></button>}
              {native && <button type="button" data-nodrag className="aq-btn icon" aria-label={t('Close the window')} title={t('Close the window')} onClick={() => post({ op: 'close' })}><X size={13} /></button>}
            </span>
          )}
          {folded && (
            /* the whole thin row unfolds on a click */
            <button type="button" data-nodrag className="absolute inset-0 w-full cursor-pointer hover:bg-[var(--aq-hover)]" aria-label={t('Unfold the title row (alt+T)')} title={t('Unfold the title row (alt+T)')}
              onClick={() => { unfoldedAt.current = Date.now(); setFolded(false); refocus() }} />
          )}
          {kind !== 'chat' && !folded && toggleBtn('right')}
        </div>
        <div className="flex min-h-0 flex-1" style={{ background: 'var(--aq-panel)' }}>
          {leftSeated.map(panel)}
          <div className="flex flex-col min-w-0 relative" style={{ width: termW }}>
            {stripEl}
            {kind !== 'chat' && folded && toggleBtn('left')}
            {kind !== 'chat' && folded && toggleBtn('right')}
            {body}
          </div>
          {rightSeated.map(panel)}
        </div>
      </div>

      {menu && menu.kind !== 'keys' && <button type="button" aria-label={t('Close the menu')} tabIndex={-1} className="fixed inset-0 z-[35] cursor-default" onClick={() => { setMenu(null); refocus() }} />}
      {tabMenuS && menu?.kind === 'tab' && (
        <Float label={tabMenuS.label} className="w-[280px]" style={{ left: Math.max(0, Math.min(menu.x, lw + termW - 284)), top: bar + STRIP + 2 }}>
          <span className="aq-label px-6 py-4 truncate">{tabMenuS.label}</span>
          {menu.form === 'rename' ? (
            <form className="p-4" onSubmit={(e) => { e.preventDefault(); const v = String(new FormData(e.currentTarget).get('label') ?? '').trim(); if (v) void act.rename(tabMenuS.id, v); setMenu(null); refocus() }}>
              <input name="label" autoFocus defaultValue={tabMenuS.label} aria-label={t('Name')} maxLength={80}
                className="w-full h-[26px] px-8 rounded-[6px] text-12 outline-none" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }} />
            </form>
          ) : menu.form === 'group' ? (
            <GroupForm submit={t('Make the group')} onSubmit={async (name, color) => {
              setMenu(null)
              const g = await act.newGroup(name, color)
              if (!g) return
              await act.setGroup(tabMenuS.id, g.id)
              setWsSel(groupWs(g.id)); setPicked(tabMenuS.id)
              flash(t('New workspace {name} with {chat}', { name: g.name, chat: tabMenuS.label }))
              refocus()
            }} />
          ) : (
            <>
              <Item autoFocus onClick={() => setMenu({ ...menu, form: 'rename' })}>{t('Rename…')}</Item>
              {canSleep && tabMenuS.state !== 'ended' && <Item onClick={() => { setMenu(null); void sleepOne(tabMenuS, !isAsleep(tabMenuS)) }}>{isAsleep(tabMenuS) ? t('Wake') : t('Sleep: the agent stops, the chat stays')}</Item>}
              {canGroup && <Item onClick={() => setMenu({ ...menu, form: 'group' })}>{t('New group from this tab')}…</Item>}
              {canGroup && moveTargets(tabMenuS, groups).map((g) => (
                <Item key={g.id} onClick={() => { setMenu(null); void act.setGroup(tabMenuS.id, g.id).then(() => { flash(t('{chat} moved to {name}', { chat: tabMenuS.label, name: g.name })); refocus() }) }}>
                  <span className="w-[8px] h-[8px] rounded-[2px]" style={{ background: lane(g.color) }} />{t('Move to')} {g.name}</Item>
              ))}
              {canGroup && tabMenuS.group && (
                <Item onClick={() => { setMenu(null); void act.setGroup(tabMenuS.id, '').then(() => { setWsSel(projectWs(tabMenuS.project)); flash(t('{chat} is back in {name}', { chat: tabMenuS.label, name: tabMenuS.project })); refocus() }) }}>
                  {t('Out of the group, back to')} {tabMenuS.project}</Item>
              )}
              {kind !== 'chat' && <Item onClick={() => detachChat(tabMenuS.id)}>{t('Detach into its own window')}</Item>}
              <Item onClick={() => { setMenu(null); void act.close(tabMenuS.id).then(refocus) }}>{t('Close the terminal')}</Item>
            </>
          )}
        </Float>
      )}
      {groupMenuWs && (
        <GroupMenu ws={groupMenuWs} style={{ left: lw + 40, top: bar + STRIP + 6 }} canSleep={canSleep}
          asleep={groupMenuWs.sessions.length > 0 && groupMenuWs.sessions.filter((s) => roleOf(s) !== 'server').every(isAsleep)}
          onEdit={(name, color) => void act.editGroup(groupMenuWs.key, { name, color })}
          onRemove={() => { void act.removeGroup(groupMenuWs.key); if (ws === groupMenuWs.id) setWsSel('') }}
          onDetach={() => detachWs(groupMenuWs.id)} onSleep={(a) => void sleepWs(groupMenuWs, a)}
          onClose={() => { setMenu(null); refocus() }} />
      )}
      {menu?.kind === 'keys' && <Keys onClose={() => { setMenu(null); refocus() }} />}
      {showRestore && <RestoreCard rows={restoreRows} results={restoreOut} running={restoring} onRun={() => void runRestore()} onClose={() => { setRestoreShut(true); refocus() }} />}
      {flashText && (
        <div key={flashText.n} role="status" className="absolute bottom-16 left-1/2 -translate-x-1/2 z-[50] rounded-[999px] px-14 py-6 text-12 aq-fade"
          style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--text-primary)' }}>{flashText.text}</div>
      )}
    </div>
  )

  return (
    <div className="aq fixed inset-0 overflow-hidden" data-v="j" style={{ background: native ? 'var(--aq-panel)' : 'var(--r2-wall)' }}>
      {frame}
    </div>
  )
}

function Keys({ onClose }: { onClose: () => void }) {
  const rows: Array<[string, string]> = [
    ['Ctrl Shift ↑', t('zoom out: the workspace, then every workspace')], ['Ctrl Shift ↓', t('zoom back in')], ['Esc', t('back to the terminal')],
    ['alt [', t('left sidebar')], ['alt ]', t('right sidebar')], ['alt T', t('fold or unfold the title row')], ['alt W', t('next chat waiting on you')],
    ['alt N', t('new terminal')], ['alt 1…9', t('the tab with that number')], ['alt /', t('these keys')],
    [t('right-click a tab'), t('its menu: rename, sleep, group, detach, close')], ['Shift F10', t('the focused tab\'s menu')],
  ]
  return (
    <div className="absolute inset-0 z-[50] flex items-center justify-center" role="dialog" aria-label={t('Keys')}>
      <button type="button" aria-label={t('Close')} className="absolute inset-0 cursor-default" style={{ background: 'oklch(0 0 0 / 0.28)' }} onClick={onClose} />
      <div className="relative rounded-[12px] p-20 aq-fade w-[620px] max-w-[92%]" style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-lg)' }}>
        <div className="flex items-center mb-12"><b className="text-14">{t('Keys')}</b><button type="button" autoFocus className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={onClose}><X size={14} /></button></div>
        <dl className="m-0 grid grid-cols-2 gap-x-24 gap-y-6">
          {rows.map(([k, what]) => (
            <div key={k} className="flex items-center gap-10 text-12">
              <dt className="w-[110px] shrink-0 flex gap-2 flex-wrap">{k.split(' ').map((x) => <kbd key={x} className="aq-kbd">{x}</kbd>)}</dt>
              <dd className="m-0 aq-ink2">{what}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}

