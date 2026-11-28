/**
 * SP Aqua (tk_bbb84183): Slightly Parallel's terminal window, at /term,
 * built from the design round's J (`../design/round3/J.tsx`) on real data.
 *
 * At rest it is an ordinary terminal: a title row (folds with alt+T or a
 * double click), the tab strip of the current workspace with the others
 * folded behind "+N", and the live terminal of the tab in front. The last
 * few tabs in front (KEEP_SCREENS) stay mounted, hidden, socket and all: a
 * switch back shows them in the same frame instead of a new xterm waiting on
 * a new tmux client to draw (tk_74f2d3ba). Around it, on demand:
 *
 * - the sidebars (alt+[ and alt+]): workspaces, chats and servers on the
 *   left; the chat's messages, pins, branches and stats on the right. In
 *   the app's own window they can grow the window outward (the bridge's
 *   `grow`) or use space inside its current width; in a browser they
 *   open beside the terminal on whichever side the page has room (J's
 *   rule), and the terminal does not move;
 * - the overview (Ctrl+Shift+↑ out, Esc back in): the workspace as still
 *   text tiles, then every workspace — transform and opacity only;
 * - groups, sleep and wake, restore after a restart, detach into another
 *   window, typing ticks — each drawn only when the server has its route;
 * - the smart timer: the tab in front is the project being worked on while
 *   the window is in front with input (useWorkBeats, source "window"); the
 *   strip's right end says today's time on its project and in all, and
 *   whether the timer counts (TimerGroup; a click opens the Timer page).
 *
 * `?detached=<id>` is a window of one chat; `?ws=<project or group>` a
 * window of one workspace.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { ChevronDown, ChevronRight, ChevronUp, LayoutGrid, Maximize, Menu, Minimize, Minus, PanelLeft, PanelRight, PanelsTopLeft, Plus, RotateCcw, Settings, SquareTerminal, Sun, X } from 'lucide-react'
import { smoothOn } from '../../terminal/smoothScroll'

import '../design/aqua.css'
import { Screen } from '../../terminal/Screen'
import { MessageLayer } from '../../terminal/messageMenu/MessageMenu'
import { PYWINPTY, useTerminalActions, useTerminalStatus } from '../../../lib/terminal'
import type { MsgMark } from '../../../lib/pins'
import { useMsgMarkActions } from '../../../lib/pins'
import { sendTyping, useAquaActions, useGroups, useRestoreNeeded, useSessions, type RestoreResult } from './api'
import { hasNativeDashboard, isNative, observeFullscreen, openWindow, post, setDashboardView } from './bridge'
import { DashboardRecord, useDashboard } from './dashboard'
import {
  LW, RW, chordOf, deriveWorkspaces, lastTabIn, rememberTab, detachUrl, fitSidebarWidths, foldTabs, groupWs, isAsleep, nextWaiting, parseView, placeSide, projectWs,
  cycleLevel, moveTab, orderedTabs, resolveWs, roleOf, seatBoth, shownOf, stepIn, stepOut, tabSections, tilesOf, widths, wsIdOf,
  type AquaSession, type LastTabs, type Level, type Seats, type Side, type Workspace,
} from './model'
import { AllLevel, GAP, HEAD, PAD, TILE_H, WsLevel } from './overview'
import { Float, GroupForm, GroupMenu, Item, RestoreCard, Swatch, lane, moveTargets } from './parts'
import { LeftSidebar, RightSidebar, type RightTab } from './sidebars'
import { RestoreOffer } from './restoreOffer'
import { ResourceMeter } from './ResourceMeter'
import { TypingBatcher } from './typing'
import { useWorkBeats } from '../../time/beats'
import { TimerGroup } from './timer'
import { useWindowScheme } from './scheme'
import { terminalLimitPending, useTerminalLimit } from '../../../lib/terminalLimit'
import { TerminalLimitPanel } from './TerminalLimitPanel'
import { useWindowPreferences, WindowSettings } from './WindowSettings'
import { HealthLayer, HealthTint, HealthTitle, useHealthEdge, useHealthRuntime } from './health'
import { factsOf, markNamed, noteOscTitle, tabTitle, useNamed, useOscTitles, useTabInfo } from './tabs/facts'
import { StripTab, useAltHeld } from './tabs/Tab'
import { refreshStripFromServer } from './tabs/strip'
import { PlusButton, agentOf, type AgentCmd, type PlusProps } from './tabs/Plus'
import { getJson } from '../../../lib/getJson'
import { t, tn } from '../../../i18n/scope/aqua'

const CLOCK_REFRESH_INTERVAL_MS = 30_000
const CHAT_LAYOUT_SETTLE_MS = 260
const NOTICE_DURATION_MS = 2600
const WINDOW_RESIZE_ACK_TIMEOUT_MS = 500

type Status = NonNullable<ReturnType<typeof useTerminalStatus>['data']>

const BAR = 34
const BAR_FOLDED = 12
const STRIP = 32
const INSET = 6
/** In a browser, the window stands on the page with this margin. */
const MARGIN = 24
const ACTIVE_KEY = 'sp-aqua-active'
const WORKSPACE_KEY = 'sp-aqua-workspace'
/**
 * Terminals kept mounted: the tab in front and the ones last in front before
 * it (tk_74f2d3ba). A switch to one of them is a CSS change, no reconnect. Each
 * costs one xterm and one socket (the window's bench: desktop/e2e/bench).
 */
export const KEEP_SCREENS = 4
/** The tab last in front in each workspace (tk_f7a924a6): a workspace opens on it again. */
const WS_TABS_KEY = 'sp-aqua-ws-tabs'
const COLLAPSED_GROUPS_KEY = 'sp-aqua-collapsed-tab-groups'
const TAB_ORDER_KEY = 'sp-aqua-tab-order'
/** A quiet button on the terminal's dark ground, in either theme. */
const ON_TERM = { color: 'var(--term-text)', borderColor: 'var(--term-muted)' }
const MOTION_KEY = 'sp-aqua-motion'
const SIDEBAR_MODE_KEY = 'sp-aqua-sidebar-mode'
type SidebarMode = 'outward' | 'inward'
/** The levels' breadcrumb row. */
const CRUMB = 28

const store = {
  get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } },
}

function readLastTabs(): LastTabs | null {
  try {
    const value: unknown = JSON.parse(store.get(WS_TABS_KEY) ?? 'null')
    return value && typeof value === 'object' && !Array.isArray(value) ? value as LastTabs : null
  } catch { return null }
}

function readTabOrder(): Record<string, string[]> {
  try {
    const value: unknown = JSON.parse(store.get(TAB_ORDER_KEY) ?? '{}')
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
    return Object.fromEntries(Object.entries(value).filter(([, ids]) =>
      Array.isArray(ids) && ids.every((id) => typeof id === 'string')))
  } catch { return {} }
}

function readCollapsedGroups(): string[] {
  try {
    const value: unknown = JSON.parse(store.get(COLLAPSED_GROUPS_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : []
  } catch { return [] }
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

/** Now, in ms, read again every 30 s: the minutes a chat waited move on. */
function useMinuteClock() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const h = setInterval(() => setNow(Date.now()), CLOCK_REFRESH_INTERVAL_MS)
    return () => clearInterval(h)
  }, [])
  return now
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
  | { kind: 'tabSelection'; ws: string; ids: string[]; x: number; naming?: boolean }
  | { kind: 'others' }
  | { kind: 'group'; ws: string }
  | { kind: 'tabGroup'; id: string; x: number }
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
  // The colour scheme (Settings › Terminal › Colour scheme) on the window's tokens.
  const scheme = useWindowScheme()
  const pendingTerminal = useTerminalLimit()
  const [fullscreen, setFullscreen] = useState(false)
  useEffect(() => observeFullscreen(setFullscreen), [])
  const fullscreenLabel = fullscreen ? t('Exit fullscreen') : t('Enter fullscreen')
  const layout = useWindowPreferences()
  // The tab strip (tk_a9306fb1): titles the programs set, the chats' facts, Alt held.
  const tabInfo = useTabInfo()
  const oscTitles = useOscTitles()
  const named = useNamed()
  const alt = useAltHeld()
  const nowMs = useMinuteClock()
  const titleOf = useCallback((s: AquaSession) => tabTitle(s, tabInfo?.[s.id], oscTitles, named), [tabInfo, oscTitles, named])
  const [plusOpen, setPlusOpen] = useState(false)
  useEffect(() => {
    const again = () => void refreshStripFromServer((u) => getJson(u))
    window.addEventListener('focus', again)
    return () => window.removeEventListener('focus', again)
  }, [])

  const fixedChat = view.detached
  const fixedWs = view.ws ? resolveWs(view.ws, workspaces) : ''
  const kind: 'main' | 'ws' | 'chat' = fixedChat ? 'chat' : fixedWs ? 'ws' : 'main'
  const hasDashboard = native && hasNativeDashboard() && !view.detached && !view.ws
  const dashboard = useDashboard(hasDashboard)

  /* ------------------------------------------------ which terminal is in front */
  const [picked, setPicked] = useState(() => fixedChat || (kind === 'main' ? store.get(ACTIVE_KEY) || '' : ''))
  const [lastTabs, setLastTabs] = useState<LastTabs>(() => readLastTabs() ?? {})
  const [tabOrder, setTabOrder] = useState(readTabOrder)
  const [split, setSplit] = useState<{ workspace: string; id: string }>()
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === TAB_ORDER_KEY) setTabOrder(readTabOrder()) }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])
  const [tabSelection, setTabSelection] = useState<{ ws: string; anchor: string; ids: string[] }>()
  const [collapsedGroups, setCollapsedGroups] = useState(readCollapsedGroups)
  const collapseGroup = useCallback((id: string, collapsed: boolean) => {
    const saved = readCollapsedGroups()
    const next = collapsed ? [...new Set([...saved, id])] : saved.filter((key) => key !== id)
    store.set(COLLAPSED_GROUPS_KEY, JSON.stringify(next))
    setCollapsedGroups(next)
  }, [])
  useEffect(() => {
    const syncGroups = (event: StorageEvent) => {
      if (event.key === COLLAPSED_GROUPS_KEY) setCollapsedGroups(readCollapsedGroups())
    }
    window.addEventListener('storage', syncGroups)
    return () => window.removeEventListener('storage', syncGroups)
  }, [])
  const [wsSel, setWsSel] = useState(() => kind === 'main' ? store.get(WORKSPACE_KEY) || '' : '')
  const byId = useMemo(() => new Map(sessions.map((s) => [s.id, s])), [sessions])
  const pickedS = byId.get(picked)
  // At first: the workspace of a chat waiting on you, else of the newest terminal.
  const firstWs = useMemo(() => {
    const all = workspaces.flatMap((w) => w.sessions.map((s) => ({ w, s })))
    const pick = all.find((x) => shownOf(x.s) === 'waiting') ?? all.sort((a, b) => (b.s.created || '').localeCompare(a.s.created || ''))[0]
    return pick?.w.id ?? workspaces[0]?.id ?? ''
  }, [workspaces])
  // A stored workspace can precede the session/group lists, or have been removed.
  const ready = loaded && !groupsQ.isPending
  const selectedWs = !ready || workspaces.some((w) => w.id === wsSel) ? wsSel : ''
  const ws = fixedWs || selectedWs || (pickedS ? wsIdOf(pickedS, groups) : '') || firstWs
  const wsObj = workspaces.find((w) => w.id === ws)
  const active: AquaSession | undefined = kind === 'chat'
    ? byId.get(fixedChat)
    : pickedS && wsIdOf(pickedS, groups) === ws ? pickedS : lastTabIn(wsObj, lastTabs)

  // Whatever brought a tab to the front, its workspace opens on it next time.
  const activeId = active?.id ?? ''
  const splitId = split?.workspace === ws && split.id !== activeId ? split.id : ''
  const activeWs = active ? wsIdOf(active, groups) : ''
  useEffect(() => {
    if (!ready || kind === 'chat' || !activeId || !activeWs) return
    setLastTabs((local) => rememberTab(local, activeWs, activeId))
    // Detached workspaces share storage. Merge with the latest map they may have written.
    const saved = readLastTabs() ?? {}
    const next = rememberTab(saved, activeWs, activeId)
    if (next !== saved) store.set(WS_TABS_KEY, JSON.stringify(next))
  }, [ready, kind, activeId, activeWs])
  // The tabs last in front, newest first: their terminals stay mounted (KEEP_SCREENS).
  const [recent, setRecent] = useState<string[]>([])
  // Record the active tab before the strip can receive another click.
  useLayoutEffect(() => {
    if (!activeId) return
    setRecent((r) => r[0] === activeId ? r : [activeId, ...r.filter((x) => x !== activeId)].slice(0, KEEP_SCREENS))
  }, [activeId])
  const [level, setLevel] = useState<Level>('chat')
  const [settled, setSettled] = useState(true)
  useEffect(() => {
    if (level !== 'chat') { setSettled(false); return }
    const h = setTimeout(() => setSettled(true), CHAT_LAYOUT_SETTLE_MS)
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
    const h = setTimeout(() => setFlash(null), NOTICE_DURATION_MS)
    return () => clearTimeout(h)
  }, [flashText])

  /** The keyboard back to the terminal, after any action of the chrome. */
  const refocus = useCallback(() => {
    setTimeout(() => {
      // A double click on a tab opens its name editor after selecting the tab.
      if (document.activeElement?.matches('[data-tab] input')) return
      document.querySelector<HTMLTextAreaElement>('.aqua-screen .xterm-helper-textarea')?.focus()
    }, 0)
  }, [])
  const dashboardShown = dashboard.shown
  const terminalInput = useRef<HTMLTextAreaElement | null>(null)
  const returnToTerminal = () => {
    dashboard.show(false)
    const input = terminalInput.current
    if (input?.isConnected && input.closest('.aqua-screen, .aqua-right-pane')) {
      requestAnimationFrame(() => input.focus({ preventScroll: true }))
    } else refocus()
  }
  const focusRight = useCallback(() => {
    setTimeout(() => document.querySelector<HTMLTextAreaElement>('.aqua-right-pane .xterm-helper-textarea')?.focus(), 0)
  }, [])
  const showRight = (id: string) => {
    setMenu(null)
    setSplit({ workspace: ws, id })
    setLevel('chat')
    focusRight()
  }

  const select = useCallback((workspace: string, id: string) => {
    setTabSelection(undefined)
    setWsSel(workspace)
    setPicked(id)
    if (kind === 'main') {
      store.set(WORKSPACE_KEY, workspace)
      store.set(ACTIVE_KEY, id)
    }
  }, [kind])

  // `fresh`: a terminal just opened, which the list read before it does not have yet.
  const go = useCallback((id: string, fresh?: AquaSession) => {
    const s = byId.get(id) ?? fresh
    if (!s) return
    if (kind === 'chat' && id !== fixedChat) return
    if (kind === 'ws' && wsIdOf(s, groups) !== fixedWs) { openWindow(detachUrl('chat', id)); return }
    if (s.group && collapsedGroups.includes(s.group)) collapseGroup(s.group, false)
    select(wsIdOf(s, groups), id)
    setLevel('chat')
    setMenu(null)
    refocus()
  }, [byId, kind, fixedChat, fixedWs, groups, collapsedGroups, collapseGroup, select, refocus])

  const goWs = useCallback((id: string, to: Level = 'chat') => {
    if (fixedWs || kind === 'chat') return
    const w = workspaces.find((x) => x.id === id)
    const first = lastTabIn(w, readLastTabs() ?? lastTabs)
    select(id, first?.id ?? '')
    setMenu(null)
    setLevel(to)
    if (to === 'chat') refocus()
  }, [fixedWs, kind, workspaces, select, refocus, lastTabs])

  const out = () => { if (kind !== 'chat') { setLevel((l) => stepOut(l, kind === 'ws')); (document.activeElement as HTMLElement | null)?.blur?.() } }
  const into = () => setLevel((l) => { const n = stepIn(l); if (n === 'chat') refocus(); return n })
  const cycle = () => { if (kind === 'chat') return; const n = cycleLevel(level, kind === 'ws'); setLevel(n); if (n === 'chat') refocus(); else (document.activeElement as HTMLElement | null)?.blur?.() }

  /* -------------------------------------------------------------- geometry */
  const [open, setOpen] = useState({ left: false, right: false })
  const [settingsFromLeft, setSettingsFromLeft] = useState<boolean | null>(null)
  const settingsOpen = settingsFromLeft !== null
  const [seats, setSeats] = useState<Seats>({ left: null, right: null })
  const [slide, setSlide] = useState(0)
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>(() => store.get(SIDEBAR_MODE_KEY) === 'inward' ? 'inward' : 'outward')
  const sides = kind === 'chat' ? { left: false, right: false } : open
  const at: Seats = native ? { left: sides.left ? 'left' : null, right: sides.right ? 'right' : null } : { left: sides.left ? seats.left : null, right: sides.right ? seats.right : null }
  const wanted = widths(at)
  const [pendingNativeW, setPendingNativeW] = useState<number | null>(null)
  const growWait = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => {
    // A resize from an earlier toggle can arrive after the next one starts.
    // Only the current destination confirms the pending request.
    const actualWidth = window.innerWidth
    setPendingNativeW((pending) => pending === vp.w && pending === actualWidth ? null : pending)
  }, [vp.w])
  useEffect(() => () => clearTimeout(growWait.current), [])
  const nativeFrameW = sidebarMode === 'inward' ? vp.w : pendingNativeW ?? vp.w
  const { lw, rw } = native ? fitSidebarWidths(nativeFrameW, wanted.lw, wanted.rw) : wanted
  const termW = native ? nativeFrameW - lw - rw : Math.max(360, Math.min(1000, vp.w - 2 * MARGIN))
  // Inward panels resize the terminal inside a stationary window. Its title
  // controls stay attached to the window edges while its body gets narrower.
  // The frame follows the CSS viewport before React receives a native resize.
  const fixedSidebarControls = native && sidebarMode === 'inward'
  const headerLeft = fixedSidebarControls ? 0 : lw
  const headerRight = fixedSidebarControls ? 0 : rw
  const headerWidth = fixedSidebarControls ? nativeFrameW : termW
  const termX = native ? lw : Math.round((vp.w - termW) / 2) + slide
  const frameH = native ? vp.h : vp.h - 2 * MARGIN
  const bar = folded ? BAR_FOLDED : Math.round(BAR / layout.prefs.titleScale)
  useLayoutEffect(() => {
    if (hasDashboard) setDashboardView(dashboardShown, bar)
  }, [hasDashboard, dashboardShown, bar])
  const strip = kind === 'chat' ? 0 : Math.round(STRIP / layout.prefs.tabsScale)
  const bodyH = Math.max(120, frameH - bar - strip - (native ? 0 : 2))

  function growWindow(left: number, right: number) {
    if (!left && !right) return
    // Use the destination width as soon as the panels change. During a
    // shrink, drawing at the old native width briefly expands the live PTY.
    // If the compositor declines the change, the timeout uses the real width.
    setPendingNativeW((prev) => Math.max(termW, (prev ?? window.innerWidth) + left + right))
    post({ op: 'grow', left, right })
    clearTimeout(growWait.current)
    growWait.current = setTimeout(() => setPendingNativeW(null), WINDOW_RESIZE_ACK_TIMEOUT_MS)
  }

  const changeSidebarMode = (mode: SidebarMode) => {
    if (mode === sidebarMode) return
    const sign = mode === 'outward' ? 1 : -1
    if (native) growWindow(sign * wanted.lw, sign * wanted.rw)
    setSidebarMode(mode)
  }
  const changeSidebarModeRef = useRef(changeSidebarMode)
  changeSidebarModeRef.current = changeSidebarMode
  useEffect(() => {
    const onMode = (e: StorageEvent) => {
      if (e.key === SIDEBAR_MODE_KEY) changeSidebarModeRef.current(e.newValue === 'inward' ? 'inward' : 'outward')
    }
    window.addEventListener('storage', onMode)
    return () => window.removeEventListener('storage', onMode)
  }, [])

  function toggle(side: Side, on = !sides[side], focus = true) {
    if (kind === 'chat') return
    const other: Side = side === 'left' ? 'right' : 'left'
    const width = side === 'left' ? LW : RW
    if (native) {
      setOpen((o) => ({ ...o, [side]: on }))
      if (sidebarMode === 'outward') growWindow(side === 'left' ? (on ? width : -width) : 0, side === 'right' ? (on ? width : -width) : 0)
      if (focus) refocus()
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
    if (focus) refocus()
  }

  function toggleSettings() {
    if (settingsOpen) {
      setSettingsFromLeft(null)
      if (!settingsFromLeft) toggle('left', false)
      refocus()
    } else {
      setSettingsFromLeft(sides.left)
      if (!sides.left) toggle('left', true, false)
    }
  }

  /* ------------------------------------------------------------- the title */
  const activeTitle = active ? titleOf(active) : ''
  const title = active ? (kind === 'chat' ? `${activeTitle} — ${t('from')} ${wsObj?.name ?? active.project}` : `${activeTitle} — ${wsObj?.name ?? ''}`) : 'SP Aqua'
  useEffect(() => {
    document.title = title
    post({ op: 'title', text: title })
  }, [title])

  /* ---------------------------------------------------- the smart timer */
  // The tab in front is the work at hand: while this window is in front and
  // you give input, the timer hears of its project and task (the beats the
  // app's pages send, source "window"; timeauto.py counts them).
  const workProject = active?.project ?? ''
  const workTask = active?.task_id ?? ''
  useWorkBeats(() => (workProject && !dashboardShown ? { project: workProject, taskId: workTask } : null), 'window',
    dashboardShown ? '' : `${workProject}\n${workTask}`)

  /* ------------------------------------------------- health and time */
  // Variant a «quiet» (tk_810245f2): the main window only, so two windows never count the same work twice.
  const health = kind === 'main'
  useHealthRuntime(health ? workProject : '')
  const healthEdge = useHealthEdge()

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
  /** A plain terminal or a server, here or in `project` (an idle project's tile on the top level). */
  const newTerminal = async (role: 'server' | 'shell', project?: string) => {
    setMenu(null)
    const where = project ?? projectHere
    const s = await act.open({ kind: 'shell', project: where, label: role === 'server' ? t('server') : where || t('shell'), role, group: project === undefined ? groupHere : '' })
    if (s) go(s.id, s)
  }
  const newTerminalOnRight = async (s: AquaSession) => {
    setMenu(null)
    const opened = await act.open({ kind: 'shell', project: s.project, cwd: s.cwd || undefined, label: s.project || t('shell'), role: 'shell', group: s.group })
    if (!opened) return
    const saved = readTabOrder()
    const order = orderedTabs(strip_.tabs, saved[ws]).map(({ id }) => id)
    order.splice(order.indexOf(s.id) + 1, 0, opened.id)
    saveTabOrder({ ...saved, [ws]: order })
    go(opened.id, opened)
  }
  /** The agent the chat in front runs: the list offers it while the installed ones are read. */
  const currentAgent: AgentCmd = agentOf(active ? tabInfo?.[active.id]?.chat?.tool : undefined, active?.program, active?.command, status.agent)
  const openAgent = async (a: AgentCmd) => {
    setMenu(null)
    const s = await act.open({ kind: 'shell', project: projectHere, label: a, command: a, role: 'chat', group: groupHere })
    if (s) go(s.id, s)
  }
  const activeAgentId = active ? (tabInfo?.[active.id]?.agent_id || active.agent_id || '') : ''
  const activeTool = active ? tabInfo?.[active.id]?.chat?.tool ?? '' : ''
  const branchActive = active && activeAgentId && (activeTool === 'claude-code' || activeTool === 'codex') ? async () => {
    const d = await getJson<{ command: string; project: string; name: string }>(`/api/terminal/branch/${encodeURIComponent(activeAgentId)}`)
      .catch((e: unknown) => { flash(e instanceof Error ? e.message : String(e)); return null })
    if (!d) return
    const s = await act.open({ kind: 'shell', project: d.project || projectHere, label: `${activeTitle} ⑂`, command: d.command, role: 'chat', group: groupHere })
    if (s) { flash(`${t('Branched')}: ${activeTitle}`); go(s.id, s) }
  } : undefined
  const fromTask = async (taskId: string) => {
    const s = await act.open({ kind: 'start', task_id: taskId, project: projectHere, role: 'chat', group: groupHere })
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
    'alt+BracketLeft': () => settingsOpen ? toggleSettings() : toggle('left'),
    'alt+BracketRight': () => toggle('right'),
    'alt+KeyT': () => { setFolded((f) => !f); refocus() },
    'alt+KeyW': () => { const n = nextWaiting(kind === 'ws' ? workspaces.filter((w) => w.id === fixedWs) : workspaces, active?.id ?? '', hidden); if (n) go(n); else flash(t('No chat is waiting on you')) },
    'alt+KeyN': () => { if (kind !== 'chat') { setMenu(null); setPlusOpen((o) => !o) } },
    'mod+shift+KeyT': () => { if (kind === 'chat') return false; void newTerminal('shell') },
    'alt+Slash': () => setMenu({ kind: 'keys' }),
    'alt+shift+Slash': () => setMenu({ kind: 'keys' }),
    Escape: () => {
      if (menu) {
        if (menu.kind === 'tabSelection') setTabSelection(undefined)
        setMenu(null)
        refocus()
        return
      }
      if (settingsOpen) { toggleSettings(); return }
      const focused = document.activeElement
      if (markedTabs.length && focused?.matches('[role="tab"]') && tabListRef.current?.contains(focused)) {
        setTabSelection(undefined)
        return
      }
      if (level !== 'chat') { into(); return }
      return false
    },
  }
  const strip_ = foldTabs(workspaces, ws, hidden)
  const projectGroups = wsObj?.kind === 'project' ? (groups ?? []).filter((g) => g.project === wsObj.key) : []
  const sections = tabSections(orderedTabs(strip_.tabs, tabOrder[ws]), projectGroups)
  const saveTabOrder = (order: Record<string, string[]>) => {
    store.set(TAB_ORDER_KEY, JSON.stringify(order))
    setTabOrder(order)
  }
  const visibleTabs = sections.flatMap(({ group, tabs }) => group && collapsedGroups.includes(group.id) ? [] : tabs)
  const tabPositions = new Map(visibleTabs.map((s, i) => [s.id, i]))
  const selection = tabSelection?.ws === ws ? tabSelection : undefined
  const markedTabs = visibleTabs.filter((s) => selection?.ids.includes(s.id))
  const markRange = (start: string, end: string) => {
    const anchor = [selection?.anchor, start, end].find((id) => id && tabPositions.has(id))!
    const first = tabPositions.get(anchor)!
    const last = tabPositions.get(end)!
    const ids = visibleTabs.slice(Math.min(first, last), Math.max(first, last) + 1).map((tab) => tab.id)
    setTabSelection({ ws, anchor, ids })
  }
  const bulk = menu?.kind === 'tabSelection' && wsObj?.kind === 'project' && ws === menu.ws
    ? { project: wsObj.key, tabs: visibleTabs.filter((s) => menu.ids.includes(s.id)), count: menu.ids.length }
    : undefined
  visibleTabs.slice(0, 9).forEach((s, i) => { keys[`alt+Digit${i + 1}`] = () => go(s.id) })
  const keysRef = useRef(keys)
  keysRef.current = dashboardShown ? {} : keys
  useEffect(() => {
    // Capture: the terminal takes every key it sees, so the window's chords are read before it.
    const onKey = (e: KeyboardEvent) => {
      if (terminalLimitPending()) return
      if (e.target instanceof Element && e.target.closest('[data-inspector-edit]')) return
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
  const tabListRef = useRef<HTMLDivElement>(null)
  const tabRefs = useRef(new Map<string, HTMLButtonElement>())
  const groupRefs = useRef(new Map<string, HTMLButtonElement>())
  const activeGroup = sections.find(({ group, tabs }) => group && tabs.some((tab) => tab.id === activeId))?.group?.id
  const stripOrder = sections.map(({ group, tabs }) => `${group?.id ?? ''}:${tabs.map((s) => s.id).join(',')}`).join('|')
  useLayoutEffect(() => {
    const strip = tabListRef.current
    if (!strip || !activeId) return
    // Reveal a selected tab without moving focus away from the terminal.
    const reveal = () => {
      const tab = tabRefs.current.get(activeId) ?? (activeGroup ? groupRefs.current.get(activeGroup) : undefined)
      if (!tab) return
      const visible = strip.getBoundingClientRect()
      const rect = tab.getBoundingClientRect()
      if (rect.width > visible.width || rect.left < visible.left) strip.scrollLeft += rect.left - visible.left
      else if (rect.right > visible.right) strip.scrollLeft += rect.right - visible.right
    }
    reveal()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(reveal)
    observer.observe(strip)
    // Agent/OSC titles can resize earlier tabs after the workspace appears.
    for (const item of strip.children) observer.observe(item)
    return () => observer.disconnect()
  }, [activeId, activeGroup, ws, alt, stripOrder, collapsedGroups])
  const menuLeft = (el: HTMLElement) => {
    const frame = el.closest('[data-aqua-frame]')?.getBoundingClientRect()
    return el.getBoundingClientRect().left - (frame?.left ?? 0)
  }
  const plusProps: PlusProps = {
    agent: currentAgent, project: projectHere, path: status.projects?.[projectHere] ?? '', chatTitle: activeTitle,
    asleep: (wsObj?.sessions ?? []).filter((x) => isAsleep(x)).map((x) => ({ id: x.id, title: titleOf(x) })),
    act: {
      agent: (a) => void openAgent(a), shell: () => void newTerminal('shell'), server: () => void newTerminal('server'),
      branch: branchActive ? () => void branchActive() : undefined,
      wake: (id) => { const x = byId.get(id); if (x) void sleepOne(x, false).then(() => go(id)) },
      resume: (aid) => void resume(aid), task: (id) => void fromTask(id),
    },
  }
  const waitingHere = wsObj ? wsObj.sessions.filter((s) => shownOf(s) === 'waiting').length : 0
  /** A terminal that can show its screen: not asleep, not ended (unless a shell was opened in it). */
  const screenable = (x: AquaSession) => !isAsleep(x) && !(x.state === 'ended' && reopened !== x.id)
  const front = active && screenable(active) ? active : undefined
  const splitSession = byId.get(splitId)
  const right = splitSession && screenable(splitSession) && wsIdOf(splitSession, groups) === ws ? splitSession : undefined
  const renderTab = (s: AquaSession, under?: string) => {
    const on = s.id === activeId
    const i = tabPositions.get(s.id)!
    const previous = visibleTabs[i - 1]
    return (
      <StripTab key={s.id} s={s} title={titleOf(s)} f={factsOf(s, tabInfo?.[s.id], nowMs)} index={i} on={on}
        marked={markedTabs.some((tab) => tab.id === s.id)} dim={on && level !== 'chat'} alt={alt}
        under={under} gapBefore={roleOf(s) === 'server' && !!previous && roleOf(previous) !== 'server'} canClose
        tabRef={(el) => { if (el) tabRefs.current.set(s.id, el); else tabRefs.current.delete(s.id) }}
        onSelect={(e) => {
          if (s.id === right?.id && level === 'chat' && !(e?.shiftKey || e?.metaKey || e?.ctrlKey)) { focusRight(); return }
          if (!canGroup || wsObj?.kind !== 'project' || !(e?.shiftKey || e?.metaKey || e?.ctrlKey)) { go(s.id); return }
          if (e.shiftKey) {
            markRange(activeId, s.id)
          } else {
            const ids = selection ? markedTabs.map((tab) => tab.id) : tabPositions.has(activeId) ? [activeId] : []
            setTabSelection({ ws, anchor: s.id, ids: ids.includes(s.id) ? ids.filter((id) => id !== s.id) : [...ids, s.id] })
          }
        }}
        onClose={() => void act.close(s.id).then(refocus)}
        onRename={(v) => { markNamed(s.id); void act.rename(s.id, v).then(refocus) }}
        onDropTab={(source, before) => {
          const order = moveTab(sections, source, s.id, before)
          if (!order) return
          saveTabOrder({ ...readTabOrder(), [ws]: order })
        }}
        onMenu={(el) => {
          const x = menuLeft(el)
          if (markedTabs.length > 1 && markedTabs.some((tab) => tab.id === s.id)) {
            setMenu({ kind: 'tabSelection', ws, ids: markedTabs.map((tab) => tab.id), x })
          } else {
            setTabSelection(undefined)
            setMenu({ kind: 'tab', id: s.id, x })
          }
        }} />
    )
  }
  const stripEl = kind === 'chat' ? null : (
    <div data-window-tabs data-compact={layout.prefs.tabsScale > 1 || undefined} className={`shrink-0 flex items-end gap-2 px-6 min-w-0 relative ${native && folded ? 'aq-app-drag' : ''}`} style={{ height: strip, background: 'var(--r2-strip)', borderBottom: '1px solid var(--aq-line)', paddingLeft: folded ? 24 : undefined, paddingRight: folded ? 24 : undefined, '--aq-tab-height': `${Math.max(14, strip - 6)}px` } as CSSProperties}>
      <div ref={tabListRef} className="flex items-end gap-1 min-w-0 overflow-x-auto overflow-y-hidden r2-tabs" role="tablist" aria-label={t('Chats')}
        onKeyDown={(e) => {
          if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
          const list = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')]
          const i = list.indexOf(document.activeElement as HTMLElement)
          if (i < 0) return
          const next = i + (e.key === 'ArrowRight' ? 1 : -1)
          if (e.shiftKey && canGroup && wsObj?.kind === 'project') {
            const target = Math.max(0, Math.min(next, list.length - 1))
            const start = list[i]?.closest<HTMLElement>('[data-tab]')?.dataset.tab
            const end = list[target]?.closest<HTMLElement>('[data-tab]')?.dataset.tab
            if (start && end) markRange(start, end)
            list[target]?.focus()
          } else {
            list[(next + list.length) % list.length]?.focus()
          }
          e.preventDefault()
        }}>
        {sections.map(({ group, tabs }) => {
          if (!group) return renderTab(tabs[0]!, wsObj?.kind === 'group' ? lane(wsObj.color) : undefined)
          const collapsed = collapsedGroups.includes(group.id)
          const color = lane(group.color)
          const waiting = collapsed && tabs.find((tab) => shownOf(tab) === 'waiting')
          return (
            <div key={group.id} role="group" aria-label={group.name} className="flex shrink-0 items-end gap-1 mx-2">
              <div className="flex h-[22px] items-center mb-[2px] overflow-hidden rounded-[5px]" style={{ background: 'var(--aq-hover)', borderBottom: `2px solid ${color}` }}>
                <button type="button" data-nodrag className="aq-btn !h-[20px] !rounded-none focus-visible:!outline-offset-[-2px] gap-4"
                  ref={(el) => { if (el) groupRefs.current.set(group.id, el); else groupRefs.current.delete(group.id) }}
                  aria-label={group.name} aria-expanded={!collapsed} aria-current={collapsed && activeGroup === group.id ? 'true' : undefined}
                  data-on={collapsed && activeGroup === group.id} onClick={() => collapseGroup(group.id, !collapsed)}>
                  {collapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
                  <span className="max-w-[110px] truncate">{group.name}</span>
                  {collapsed && <span className="text-10 tabular-nums opacity-75">{tabs.length}</span>}
                  {waiting && <span className="aq-dot waiting" aria-label={t('your turn')} />}
                </button>
                <button type="button" data-nodrag className="aq-btn icon !h-[20px] !rounded-none focus-visible:!outline-offset-[-2px]" aria-haspopup="menu"
                  aria-label={t('Tab group settings: {name}', { name: group.name })}
                  onClick={(e) => setMenu({ kind: 'tabGroup', id: group.id, x: menuLeft(e.currentTarget) })}><Menu size={10} /></button>
              </div>
              {!collapsed && tabs.map((s) => renderTab(s, color))}
            </div>
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
      <PlusButton {...plusProps} open={plusOpen} setOpen={setPlusOpen} />
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
  // The tab in front and the ones last in front, mounted; in a fixed order, so a switch moves no DOM.
  const kept = [activeId, right?.id ?? '', ...recent].filter((id, i, all) => id && all.indexOf(id) === i)
    .map((id) => byId.get(id)).filter((x): x is AquaSession => !!x && screenable(x)).slice(0, KEEP_SCREENS)
    .sort((a, b) => a.id.localeCompare(b.id))
  // Only the terminal in front wears .aqua-screen (refocus, the tests); the others are hidden whole.
  const screenOf = (x: AquaSession) => {
    const on = x.id === front?.id
    const beside = x.id === right?.id
    const showing = on || beside
    return (
      <div key={x.id} className={`absolute inset-0 min-w-0 flex flex-col ${on ? 'aqua-screen' : beside ? 'aqua-right-pane border-l border-border-default' : 'aqua-kept'}`}
        style={beside ? { left: '50%' } : on && right ? { right: '50%' } : showing ? undefined : { display: 'none' }}
        role={beside ? 'region' : undefined} aria-label={beside ? t('Terminal on the right') : undefined} aria-hidden={showing ? undefined : true}>
        {beside && <div className="flex shrink-0 items-center justify-between gap-6 px-6 text-11" style={{ background: 'var(--r2-strip)' }}>
          <span className="truncate">{titleOf(x)}</span>
          <button type="button" className="aq-btn icon" aria-label={t('Close the right pane')} title={t('Close the right pane')}
            onClick={() => { setSplit(undefined); refocus() }}><X size={12} /></button>
        </div>}
        <div className="relative flex-1 min-h-0">
        {/* A right click on a message opens its menu; ids are links (messageMenu/). */}
        <MessageLayer agentId={tabInfo?.[x.id]?.agent_id || x.agent_id || ''} project={x.project} say={flash} refocus={beside ? focusRight : refocus} goTo={kind === 'chat' ? undefined : go}>
          {(layer) => (
            <Screen key={x.woken_at} sid={x.id} token={status.token} fontSize={status.font_size} scrollback={status.scrollback} smooth={smoothOn(status.smooth_scroll)} editor={status.editor}
              project={x.project} taskId={x.task_id} backend={x.backend} visible={showing} program={x.program ?? ''} autoFocus={(beside || on && !right) && level === 'chat'}
              onInput={() => typing.tick(x.id)}
              onEnded={() => { void restoreQ.refetch() }}
              onTitle={(title) => noteOscTitle(x.id, title)}
              hooks={layer.hooks} bind={layer.bind}
              onZoom={(d) => void termAct.setting({ 'terminal.font_size': Math.max(10, Math.min(22, status.font_size + d)) })} />
          )}
        </MessageLayer>
        </div>
      </div>
    )
  }
  const placeholder = front ? null : active ? (
    isAsleep(active) ? (
      <div className="h-full flex flex-col items-center justify-center gap-10" style={{ background: 'var(--term-ground)', color: 'var(--term-text)' }}>
        <span className="text-13">{t('{name} is asleep: the agent is stopped, the chat is kept.', { name: active.label })}</span>
        {canSleep && <button type="button" className="aq-btn solid" onClick={() => void sleepOne(active, false)}><Sun size={12} />{t('Wake')}</button>}
      </div>
    ) : (
      <div className="h-full flex flex-col items-center justify-center gap-10" style={{ background: 'var(--term-ground)', color: 'var(--term-text)' }}>
        <span className="text-13">{t('{name} ended.', { name: active.label })}</span>
        <span className="flex gap-6">
          {canSleep && <button type="button" className="aq-btn solid" onClick={() => void sleepOne(active, false)}><RotateCcw size={12} />{t('Start it again')}</button>}
          <button type="button" className="aq-btn line" style={ON_TERM} onClick={() => {
            if (status.open_shell) void termAct.wake(active.id, true).then(refocus)
            else { setReopened(active.id); refocus() } // Older servers open the shell on attach.
          }}><SquareTerminal size={12} />{t('Open a shell in it')}</button>
          <button type="button" className="aq-btn line" style={ON_TERM} onClick={() => void act.close(active.id)}><X size={12} />{t('Close the terminal')}</button>
        </span>
      </div>
    )
  ) : (
    <div className="h-full flex flex-col items-center justify-center gap-10" style={{ background: 'var(--term-ground)', color: 'var(--term-muted)' }}>
      <span className="text-13">{!loaded ? '' : kind === 'chat' ? t('This terminal is gone.') : t('No terminal in this workspace.')}</span>
      {loaded && kind !== 'chat' && <button type="button" className="aq-btn solid" onClick={() => void newTerminal('shell')}><Plus size={12} />{t('New terminal')}</button>}
    </div>
  )
  // overflow-clip, not -hidden: a hidden box is still a scroll container, and
  // the All level's scale(1.05) overflows it by 14 px; the browser scrolled it
  // (a message collapsed in the reader), hiding the terminal's top row under
  // the tab strip. A clipped box cannot scroll.
  const body = (
    <div className="relative min-h-0 overflow-clip" style={{ width: termW, height: bodyH }} data-level={level}>
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
              <span className="ml-auto text-10 aq-ink3 font-mono">Esc {level === 'all' ? t('back to the workspace') : t('back to the terminal')}</span>
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
                  {showLevels && <AllLevel workspaces={workspaces} current={active?.id ?? ''} cols={cols} onWs={(id) => goWs(id, 'ws')} onChat={go}
                    onIdle={(id) => goWs(id)} onNewShell={(code) => void newTerminal('shell', code)}
                    onNewSpace={canGroup ? async (name, color) => { const g = await act.newGroup(name, color); if (g) { goWs(groupWs(g.id)); flash(t('New workspace {name}', { name: g.name })) } } : undefined} />}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      <div className="absolute inset-0 origin-top-left aqua-stage" style={{
        transform: level === 'chat' ? 'none' : zoomTo, opacity: level === 'chat' ? 1 : 0,
        transition: `transform ${dur}ms var(--aq-ease), opacity ${Math.round(dur * 0.7)}ms`, pointerEvents: level === 'chat' ? 'auto' : 'none',
        willChange: instant || settled ? undefined : 'transform', background: 'var(--term-ground)',
      }}>
        {kept.map(screenOf)}
        {!front && <div className="absolute inset-0 aqua-screen" style={right ? { right: '50%' } : undefined}>{placeholder}</div>}
      </div>
    </div>
  )

  /* ---------------------------------------------------------- the frame */
  const leftSeated = (['right', 'left'] as const).filter((k) => sides[k] && at[k] === 'left')
  const rightSeated = (['right', 'left'] as const).filter((k) => sides[k] && at[k] === 'right')
  const settings = settingsOpen && <WindowSettings {...layout} instant={instant} setInstant={setInstant}
    native={native && kind !== 'chat'} mode={sidebarMode} setMode={(mode) => { changeSidebarMode(mode); store.set(SIDEBAR_MODE_KEY, mode) }}
    onClose={toggleSettings} keys={<KeyHints compact />} />
  const panel = (k: Side) => (
    <aside key={k} className={`shrink-0 min-w-0 overflow-hidden ${instant ? '' : k === 'left' ? 'r2-side-l' : 'r2-side-r'}`} aria-label={k === 'left' ? t(settingsOpen ? 'Window settings' : 'Left sidebar') : t('Right sidebar')}
      style={{ width: native ? (k === 'left' ? lw : rw) : (k === 'left' ? LW : RW), height: strip + bodyH,
        paddingTop: fixedSidebarControls && folded ? strip : undefined,
        background: 'var(--aq-panel)', borderLeft: '1px solid var(--aq-line)', borderRight: '1px solid var(--aq-line)' }}>
      {k === 'left'
        ? <><div hidden={settingsOpen} className="h-full"><LeftSidebar workspaces={workspaces} ws={ws} active={active?.id ?? ''} canSleep={canSleep} onChat={go} onWs={(id) => goWs(id)}
            onSleep={(s, a) => void sleepOne(s, a)} onSleepWs={(w, a) => void sleepWs(w, a)} onNew={(r) => void newTerminal(r)} plus={<PlusButton {...plusProps} look="side" />}
            onGroupMenu={(w) => setMenu({ kind: 'group', ws: w.id })} /></div>{settings}</>
        : <RightSidebar s={active} project={active?.project ?? (kind !== 'chat' && wsObj?.kind === 'project' ? wsObj.key : '')} agent={activeAgentId}
            tab={rtab} setTab={setRtab} workspaces={workspaces} onChat={go} onResume={(a) => void resume(a)} onFork={(m) => void fork(m)} />}
    </aside>
  )
  const toggleBtn = (side: Side) => {
    const on = sides[side]
    const away = !native && on && at[side] !== side
    const label = side === 'left' ? t('Left sidebar') : t('Right sidebar')
    const hint = side === 'left'
      ? (away ? t('Left sidebar (alt+[) — opened on the right: no room on the left') : t('Left sidebar (alt+[)'))
      : (away ? t('Right sidebar (alt+]) — opened on the left: no room on the right') : t('Right sidebar (alt+])'))
    const edge = side === 'left' ? 'left' : 'right'
    const activate = () => side === 'left' && settingsOpen ? toggleSettings() : toggle(side)
    // Folded: a small rectangle at the end of the tab strip, half as wide.
    if (folded) return (
      <button type="button" data-nodrag data-toggle={side} data-in="strip" aria-pressed={on} aria-label={label} title={hint}
        className={`absolute rounded-[2px] hover:opacity-100 ${fixedSidebarControls ? 'z-[2]' : ''}`}
        style={{ [edge]: INSET, top: Math.round((strip - 14) / 2), width: 12, height: 14, opacity: on ? 1 : 0.6,
          background: on ? 'var(--brand)' : 'transparent', border: `1.5px solid ${on ? 'var(--brand)' : 'var(--text-tertiary)'}` }} onClick={activate} />
    )
    return (
      <button type="button" data-nodrag data-toggle={side} aria-pressed={on} aria-label={label} title={hint}
        className="absolute inline-flex items-center justify-center rounded-[6px] hover:bg-[var(--aq-hover)]"
        style={{ [edge]: (side === 'left' ? headerLeft : headerRight) + INSET, top: Math.max(0, (bar - 24) / 2), width: 24, height: Math.min(24, bar) }} onClick={activate}>
        {side === 'left' ? <PanelLeft size={14} style={{ color: on ? 'var(--brand)' : undefined }} /> : <PanelRight size={14} style={{ color: on ? 'var(--brand)' : undefined }} />}
        {away && <span className={`absolute text-11 font-semibold ${side === 'left' ? '-right-10' : '-left-10'}`} style={{ color: 'var(--brand)' }} aria-hidden>{side === 'left' ? '▸' : '◂'}</span>}
      </button>
    )
  }
  const foldedToggles = kind !== 'chat' && folded && <>{toggleBtn('left')}{toggleBtn('right')}</>

  const tabMenuS = menu?.kind === 'tab' ? byId.get(menu.id) : undefined
  const groupMenuWs = menu?.kind === 'group' ? workspaces.find((w) => w.id === menu.ws) : undefined
  const tabGroupMenu = menu?.kind === 'tabGroup' ? projectGroups.find((g) => g.id === menu.id) : undefined

  const frame = (
    <div data-aqua-frame className={`absolute flex flex-col ${native ? '' : 'r2-win'}`} role="dialog" aria-label={`${t('Window')}: ${kind === 'main' ? 'SP Aqua' : title}`}
      data-folded={folded || undefined} data-sidebar-mode={native ? sidebarMode : undefined}
      style={native ? { left: 0, top: 0, width: fixedSidebarControls ? '100%' : lw + termW + rw, height: frameH } : { left: termX - lw, top: MARGIN, height: frameH }}>
      {/* A fixed border inside the title row would inherit its native drag region. */}
      {health && native && healthEdge && <span aria-hidden data-health-edge className="fixed inset-0 pointer-events-none z-[1]" style={{ boxShadow: `inset 0 0 0 1px ${healthEdge}` }} />}
      <div className={`flex flex-col h-full ${native ? 'overflow-clip' : 'overflow-hidden rounded-[8px]'}`} style={native ? undefined : {
        boxShadow: 'var(--shadow-lg)', border: `1px solid ${health && healthEdge ? healthEdge : 'var(--border-strong)'}`, borderTop: kind !== 'main' && wsObj ? `3px solid ${lane(wsObj.color)}` : undefined,
      }}>
        {/* the title row: folds to a 12px strip */}
        <div data-window-title data-compact={layout.prefs.titleScale > 1 || undefined} className={`relative shrink-0 select-none ${native ? 'aq-app-drag' : ''}`} style={{ height: bar, background: 'var(--r2-bar)', color: 'var(--r2-bar-ink)', transition: instant || dashboardShown ? undefined : 'height 120ms var(--aq-ease)', borderTop: native && kind !== 'main' && wsObj ? `3px solid ${lane(wsObj.color)}` : undefined }}
          onPointerDown={onBarDown} onDoubleClick={(e) => { if (!(e.target as HTMLElement).closest('button') && Date.now() - unfoldedAt.current > 600) { setFolded(!folded); refocus() } }}>
          {health && <HealthTint />}
          {kind !== 'chat' && !folded && toggleBtn('left')}
          {!folded && (
            <div className="absolute inset-y-0" data-window-title-controls style={{
              left: headerLeft + (kind === 'chat' ? 8 : 36), right: headerRight + (kind === 'chat' ? 8 : 36),
            }}>
              <div className="grid h-full items-center gap-4" data-window-title-grid>
                <span className="flex min-w-0 items-center gap-2">
                  <button type="button" data-nodrag className="aq-btn icon shrink-0" aria-label={t('Window settings')} title={t('Window settings')}
                    aria-expanded={settingsOpen} onClick={toggleSettings}><Settings size={13} /></button>
                  <ResourceMeter />
                </span>
                <span className="truncate text-center text-13 pointer-events-none" data-window-name>{title}</span>
                <span className="flex min-w-0 items-center justify-end gap-2" data-window-actions>
                  <button type="button" data-nodrag className="aq-btn icon shrink-0" aria-label={t('Fold the title row (alt+T)')} title={t('Fold the title row (alt+T)')} onClick={() => { setFolded(true); refocus() }}><ChevronUp size={14} /></button>
                  <TimerGroup project={active?.project ?? ''} prefs={layout.prefs} session={health ? <HealthTitle folded={false} /> : undefined} />
                  {kind !== 'chat' && (
                    <button type="button" data-nodrag data-title-action className="aq-btn shrink-0" aria-pressed={level !== 'chat'} onClick={cycle}
                      title={t('Workspaces: the chat, its workspace, every workspace (Ctrl+Shift+↑)')} aria-label={t('Workspaces')}>
                      <LayoutGrid size={13} />{wsObj && <span data-title-action-label className="text-11 max-w-[120px] truncate">{wsObj.name}</span>}
                      {waitingHere > 0 && <span data-title-action-label className="text-11 font-semibold" style={{ color: 'var(--aq-wait)' }}>● {waitingHere}</span>}
                    </button>
                  )}
                  {hasDashboard && (
                    <button type="button" data-nodrag data-title-action className="aq-btn line shrink-0"
                      aria-label={dashboardShown ? t('Terminal') : t('Dashboard')}
                      title={dashboardShown ? t('Terminal') : t('Dashboard')}
                      onClick={() => {
                        setMenu(null)
                        if (dashboardShown) returnToTerminal()
                        else dashboard.show(true)
                      }}>
                      {dashboardShown ? <SquareTerminal size={13} /> : <PanelsTopLeft size={13} />}
                      <span data-title-action-label className="text-11">{dashboardShown ? t('Terminal') : t('Dashboard')}</span>
                    </button>
                  )}
                  {native && <>
                    <button type="button" data-nodrag className="aq-btn icon shrink-0" aria-label={t('Minimise')} title={t('Minimise')} onClick={() => post({ op: 'minimize' })}><Minus size={13} /></button>
                    <button type="button" data-nodrag className="aq-btn icon shrink-0" aria-label={fullscreenLabel} title={fullscreenLabel} onClick={() => post({ op: 'fullscreen' })}>{fullscreen ? <Minimize size={13} /> : <Maximize size={13} />}</button>
                    <button type="button" data-nodrag className="aq-btn icon shrink-0" aria-label={t('Close the window')} title={t('Close the window')} onClick={() => post({ op: 'close' })}><X size={13} /></button>
                  </>}
                </span>
              </div>
            </div>
          )}
          {folded && <span className="absolute truncate text-center pointer-events-none text-9 aq-ink3"
            style={{ left: headerLeft + 40, width: Math.max(40, headerWidth - 80), lineHeight: `${bar}px` }}>{title}</span>}
          {folded && (
            /* the whole thin row unfolds on a click */
            <button type="button" data-nodrag className="absolute inset-0 w-full cursor-pointer hover:bg-[var(--aq-hover)]" aria-label={t('Unfold the title row (alt+T)')} title={t('Unfold the title row (alt+T)')}
              onClick={() => { unfoldedAt.current = Date.now(); setFolded(false); refocus() }} />
          )}
          {folded && health && layout.prefs.showSessionTimer && <span className="absolute z-[2]" style={{ right: headerRight + 40, top: 0 }}><HealthTitle folded /></span>}
          {kind !== 'chat' && !folded && toggleBtn('right')}
        </div>
        {/* Keep terminal geometry and xterm's live screen while the other side is up. */}
        <div className="relative flex min-h-0 flex-1" aria-hidden={dashboardShown || undefined}
          {...(dashboardShown ? { inert: '' } : {})}
          onFocusCapture={(e) => {
            if (e.target instanceof HTMLTextAreaElement && e.target.matches('.xterm-helper-textarea')) terminalInput.current = e.target
          }}
          style={{ background: 'var(--aq-panel)', visibility: dashboardShown ? 'hidden' : undefined }}>
          {leftSeated.map(panel)}
          <div className="flex flex-col min-w-0 relative" style={{ width: termW }}>
            {stripEl}
            {!fixedSidebarControls && foldedToggles}
            <div ref={(element) => { if (element) element.inert = pendingTerminal !== null }}>{body}</div>
            {pendingTerminal && <div className="absolute inset-x-0 bottom-0 z-[19] flex flex-col" style={{ top: strip }}>
              <TerminalLimitPanel pending={pendingTerminal} className="flex-1" />
            </div>}
            {health && <HealthLayer top={strip} project={workProject} />}
          </div>
          {rightSeated.map(panel)}
          {kind === 'chat' && settingsOpen && <aside aria-label={t('Window settings')} className="absolute inset-y-0 left-0 z-20 w-[236px] max-w-full bg-base">{settings}</aside>}
          {fixedSidebarControls && foldedToggles}
        </div>
      </div>

      {menu && menu.kind !== 'keys' && <button type="button" aria-label={t('Close the menu')} tabIndex={-1} className="fixed inset-0 z-[35] cursor-default" onClick={() => { setMenu(null); refocus() }} />}
      {tabMenuS && menu?.kind === 'tab' && (
        <Float label={tabMenuS.label} className="w-[280px] overflow-y-auto [&>*]:shrink-0"
          style={{ left: Math.max(0, Math.min(menu.x, lw + termW - 284)), top: bar + strip + 2, maxHeight: vp.h - bar - strip - 6 }}>
          <span className="aq-label px-6 py-4 truncate">{titleOf(tabMenuS)}</span>
          {menu.form === 'rename' ? (
            <form className="p-4" onSubmit={(e) => { e.preventDefault(); const v = String(new FormData(e.currentTarget).get('label') ?? '').trim(); if (v) { markNamed(tabMenuS.id); void act.rename(tabMenuS.id, v) } setMenu(null); refocus() }}>
              <input name="label" autoFocus defaultValue={titleOf(tabMenuS)} aria-label={t('Name')} maxLength={80}
                className="w-full h-[26px] px-8 rounded-[6px] text-12 outline-none" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }} />
            </form>
          ) : menu.form === 'group' ? (
            <GroupForm submit={t('Make the group')} onSubmit={async (name, color) => {
              setMenu(null)
              refocus()
              const project = wsObj?.kind === 'project' ? wsObj.key : undefined
              const g = await act.newGroup(name, color, project)
              if (!g || !await act.setGroup(tabMenuS.id, g.id)) return
              if (project === undefined) {
                select(groupWs(g.id), tabMenuS.id)
                flash(t('New workspace {name} with {chat}', { name: g.name, chat: tabMenuS.label }))
              } else {
                flash(t('New tab group {name}', { name: g.name }))
              }
            }} />
          ) : (
            <>
              <Item autoFocus onClick={() => setMenu({ ...menu, form: 'rename' })}>{t('Rename…')}</Item>
              {canSleep && tabMenuS.state !== 'ended' && <Item onClick={() => { setMenu(null); void sleepOne(tabMenuS, !isAsleep(tabMenuS)) }}>{isAsleep(tabMenuS) ? t('Wake') : t('Sleep: the agent stops, the chat stays')}</Item>}
              {canGroup && <Item onClick={() => setMenu({ ...menu, form: 'group' })}>{t('New group from this tab')}…</Item>}
              {canGroup && moveTargets(tabMenuS, groups).map((g) => (
                <Item key={g.id} onClick={async () => {
                  setMenu(null)
                  refocus()
                  if (!await act.setGroup(tabMenuS.id, g.id)) return
                  if (g.project !== undefined) collapseGroup(g.id, false)
                  flash(t('{chat} moved to {name}', { chat: tabMenuS.label, name: g.name }))
                }}>
                  <Swatch w={g} />{g.project === undefined ? `${t('Move to')} ${g.name}` : t('Add to tab group {name}', { name: g.name })}</Item>
              ))}
              {canGroup && tabMenuS.group && (
                <Item onClick={async () => {
                  setMenu(null)
                  refocus()
                  if (!await act.setGroup(tabMenuS.id, '')) return
                  if (!projectGroups.some((g) => g.id === tabMenuS.group)) {
                    select(projectWs(tabMenuS.project), tabMenuS.id)
                    flash(t('{chat} is back in {name}', { chat: tabMenuS.label, name: tabMenuS.project }))
                  }
                }}>
                  {projectGroups.some((g) => g.id === tabMenuS.group) ? t('Remove from tab group') : `${t('Out of the group, back to')} ${tabMenuS.project}`}</Item>
              )}
              {kind !== 'chat' && front && (tabMenuS.id === activeId
                ? <Item onClick={() => void newTerminalOnRight(tabMenuS)}>{t('Open a new terminal on the right')}</Item>
                : right?.id !== tabMenuS.id && screenable(tabMenuS) && <Item onClick={() => showRight(tabMenuS.id)}>{t('Open on the right')}</Item>)}
              {kind !== 'chat' && <Item onClick={() => detachChat(tabMenuS.id)}>{t('Detach into its own window')}</Item>}
              <Item onClick={() => { setMenu(null); void act.close(tabMenuS.id).then(refocus) }}>{t('Close the terminal')}</Item>
            </>
          )}
        </Float>
      )}
      {bulk && menu?.kind === 'tabSelection' && (
        <Float label={t('Selected tabs')} className="w-[280px]"
          style={{ left: Math.max(0, Math.min(menu.x, lw + termW - 284)), top: bar + strip + 2 }}>
          <span className="aq-label px-6 py-4">{t('Selected tabs: {count}', { count: bulk.count })}</span>
          {bulk.tabs.length !== bulk.count ? <span className="px-6 py-4 text-12">{t('The selection changed. Select the tabs again.')}</span>
            : menu.naming ? <GroupForm submit={t('Make the group')} onSubmit={async (name, color) => {
              setMenu(null)
              refocus()
              const group = await act.newGroup(name, color, bulk.project, menu.ids)
              if (!group) return
              setTabSelection((current) => current === selection ? undefined : current)
              flash(t('New tab group {name}', { name: group.name }))
            }} /> : <>
              <Item autoFocus onClick={() => setMenu({ ...menu, naming: true })}>{t('Group selected tabs')}…</Item>
              {projectGroups.filter((g) => bulk.tabs.some((s) => s.group !== g.id)).map((g) => (
                <Item key={g.id} onClick={async () => {
                  setMenu(null)
                  refocus()
                  if (!await act.moveTabs(menu.ids, bulk.project, g.id)) return
                  setTabSelection((current) => current === selection ? undefined : current)
                  collapseGroup(g.id, false)
                }}><Swatch w={g} />{t('Add to tab group {name}', { name: g.name })}</Item>
              ))}
              {bulk.tabs.some((s) => s.group) && <Item onClick={async () => {
                setMenu(null)
                refocus()
                if (await act.moveTabs(menu.ids, bulk.project, '')) setTabSelection((current) => current === selection ? undefined : current)
              }}>{t('Remove selected tabs from groups')}</Item>}
            </>}
        </Float>
      )}
      {tabGroupMenu && menu?.kind === 'tabGroup' && (
        <Float key={tabGroupMenu.id} label={tabGroupMenu.name} className="w-[280px]"
          style={{ left: Math.max(0, Math.min(menu.x, lw + termW - 284)), top: bar + strip + 2 }}>
          <GroupForm initial={tabGroupMenu} submit={t('Save')} onSubmit={(name, color) => {
            setMenu(null)
            refocus()
            void act.editGroup(tabGroupMenu.id, { name, color })
          }} />
          <Item onClick={() => {
            setMenu(null)
            refocus()
            void act.removeGroup(tabGroupMenu.id).then(() => collapseGroup(tabGroupMenu.id, false))
          }}><X size={12} />{t('Ungroup tabs')}</Item>
        </Float>
      )}
      {groupMenuWs && (
        <GroupMenu ws={groupMenuWs} style={{ left: lw + 40, top: bar + strip + 6 }} canSleep={canSleep}
          asleep={groupMenuWs.sessions.length > 0 && groupMenuWs.sessions.filter((s) => roleOf(s) !== 'server').every(isAsleep)}
          onEdit={(name, color) => void act.editGroup(groupMenuWs.key, { name, color })}
          onRemove={() => { void act.removeGroup(groupMenuWs.key); if (ws === groupMenuWs.id) select('', picked) }}
          onDetach={() => detachWs(groupMenuWs.id)} onSleep={(a) => void sleepWs(groupMenuWs, a)}
          onClose={() => { setMenu(null); refocus() }} />
      )}
      {menu?.kind === 'keys' && <Keys onClose={() => { setMenu(null); refocus() }} />}
      {kind === 'main' && native && <RestoreOffer refocus={refocus} />}
      {showRestore && <RestoreCard rows={restoreRows} results={restoreOut} running={restoring} onRun={() => void runRestore()} onClose={() => { setRestoreShut(true); refocus() }} />}
      {flashText && (
        <div key={flashText.n} role="status" className="absolute bottom-16 left-1/2 -translate-x-1/2 z-[50] rounded-[999px] px-14 py-6 text-12 aq-fade"
          style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--text-primary)' }}>{flashText.text}</div>
      )}
    </div>
  )

  return (
    <div className="aq fixed inset-0 overflow-clip" data-v="j" data-scheme={scheme.id} data-scheme-scope={scheme.scope} style={{ ...scheme.style, background: native ? 'var(--aq-panel)' : 'var(--r2-wall)' }}>
      <DashboardRecord.Provider value={hasDashboard ? dashboard.openRecord : null}>{frame}</DashboardRecord.Provider>
    </div>
  )
}

function KeyHints({ compact = false }: { compact?: boolean }) {
  const rows: Array<[string, string]> = [
    ['Ctrl Shift ↑', t('zoom out: the workspace, then every workspace')], ['Ctrl Shift ↓', t('zoom back in')], ['Esc', t('back one level in the overview')],
    ['alt [', t('left sidebar')], ['alt ]', t('right sidebar')], ['alt T', t('fold or unfold the title row')], ['alt W', t('next chat waiting on you')],
    ['alt N', t('new terminal: the list')], ['Ctrl Shift T', t('new terminal: a shell in the project')], ['alt 1…9', t('the tab with that number')], ['alt /', t('these keys')],
    ['alt', t('held: each tab\'s branches, tasks and minutes waited')], [t('Ctrl+click +'), t('the list of what to open; keys 1–9 pick')],
    [t('double click a tab'), t('rename it')],
    [t('right-click a tab'), t('its menu: rename, sleep, group, detach, close')], ['Shift F10', t('the focused tab\'s menu')],
    ['Shift+click / Shift+← →', t('Select a range of tabs to group')],
    ['Shift+drag', t('Select terminal text over a program that captures the mouse')],
  ]
  return (
    <dl className={`m-0 grid gap-x-24 gap-y-6 ${compact ? 'grid-cols-1' : 'grid-cols-2'}`}>
      {rows.map(([k, what]) => (
        <div key={k} className={`gap-6 text-12 ${compact ? 'grid' : 'flex items-center'}`}>
          <dt className="w-[110px] shrink-0 flex gap-2 flex-wrap">{k.split(' ').map((x) => <kbd key={x} className="aq-kbd">{x}</kbd>)}</dt>
          <dd className="m-0 aq-ink2">{what}</dd>
        </div>
      ))}
    </dl>
  )
}

function Keys({ onClose }: { onClose: () => void }) {
  return (
    <div className="absolute inset-0 z-[50] flex items-center justify-center" role="dialog" aria-label={t('Keys')}>
      <button type="button" aria-label={t('Close')} className="absolute inset-0 cursor-default" style={{ background: 'oklch(0 0 0 / 0.28)' }} onClick={onClose} />
      <div className="relative rounded-[12px] p-20 aq-fade w-[620px] max-w-[92%]" style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-lg)' }}>
        <div className="flex items-center mb-12"><b className="text-14">{t('Keys')}</b><button type="button" autoFocus className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={onClose}><X size={14} /></button></div>
        <KeyHints />
      </div>
    </div>
  )
}

