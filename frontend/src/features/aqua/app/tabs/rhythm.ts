/**
 * The tab's state «f1 · ритм» (tk_d2e11125, the operator's pick in mockup L,
 * `design/round5/mood.ts`), on real data: six small dots centred on the top
 * edge of each tab — the chat's mood and a signal.
 *
 * - The dots are the chat's last six clock hours, oldest on the left; the
 *   last is the hour now running (`GET /api/terminal/tabs`, `chat.rhythm`).
 * - A dot's intensity is that hour's activity: messages (the operator's and
 *   the agent's answers) + 3 × commits tied to the chat + 4 × its tasks
 *   closed + tokens (the main agent's new input + output) / 10 000, the
 *   tokens' part at most 10; full at 30. The mockup's weights; the cap keeps
 *   a cache rebuild (hundreds of thousands of new tokens in one turn) from
 *   filling an hour with no other work.
 * - One hue per chat: a lane colour of Slightly Parallel, chosen by the
 *   chat's id (`projectColor`), as the mockup does; a dot's colour builds up
 *   with its hour's activity. No animation at rest: a change fades over 1.2 s.
 * - The signal: when the chat needs the operator, the row warms from the
 *   right (the newest hour) leftward — toward amber, then red; one gradient.
 *   Waiting for an answer: from 5 min, amber at 10, red at 20. Context
 *   (Claude Code's status line): past 70% two of the six dots warm at
 *   once, amber at 85%, red at 95%. The mockup's thresholds. A failed
 *   check is not read: Slightly Parallel has no per-chat check result it can
 *   read cheaply, so it is left out.
 *
 * The setting «Состояние вкладки» (`sp-term-tabstate`): rhythm (default),
 * the dotted strip c of tk_a9306fb1 («точки», its own settings in strip.ts),
 * or nothing. Shared with Settings › Terminal through the server's ui_prefs.
 */

import { useSyncExternalStore } from 'react'

import { persistPref } from '../../../../lib/uiPrefs'
import { projectColor } from '../../../../utils/projectColor'

/* ------------------------------------------------------------ the setting */

export const TAB_STATES = ['rhythm', 'dots', 'off'] as const
export type TabStateKind = (typeof TAB_STATES)[number]
export const TAB_STATE_DEFAULT: TabStateKind = 'rhythm'
export const TAB_STATE_KEY = 'sp-term-tabstate'

export const parseTabState = (raw: string | null): TabStateKind =>
  (TAB_STATES as readonly string[]).includes(raw ?? '') ? raw as TabStateKind : TAB_STATE_DEFAULT

let cur: TabStateKind = TAB_STATE_DEFAULT
let curRaw: string | null | undefined
const listeners = new Set<() => void>()
const read = (): TabStateKind => {
  let raw: string | null = null
  try { raw = localStorage.getItem(TAB_STATE_KEY) } catch { /* private mode */ }
  if (raw !== curRaw) { curRaw = raw; cur = parseTabState(raw) }
  return cur
}
export const useTabStateKind = () => useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l) } }, read, read)
export function setTabStateKind(v: TabStateKind) {
  cur = v
  curRaw = v
  persistPref(TAB_STATE_KEY, v)
  for (const l of listeners) l()
}
/** localStorage may hold a new value (the server's copy was read again). */
export function tabStateChanged() { for (const l of listeners) l() }

/* ------------------------------------------------------------ the hours */

/** One period of a chat, as the server counts it. */
export interface Period { start: string; end: string; msgs: number; commits: number; tasks: number; tokens: number }
export interface Rhythm { period_min: number; periods: Period[] }

export const DOTS = 6
export const FULL = 30
export const W_COMMIT = 3
export const W_TASK = 4
export const TOKENS_PER_POINT = 10_000
export const TOKEN_POINTS_MAX = 10

/** A period's activity, 0–1. */
export function intensity(p: Period): number {
  const tok = Math.min((p.tokens || 0) / TOKENS_PER_POINT, TOKEN_POINTS_MAX)
  const sum = (p.msgs || 0) + W_COMMIT * (p.commits || 0) + W_TASK * (p.tasks || 0) + tok
  return Math.max(0, Math.min(sum / FULL, 1))
}

/** The six values, oldest first; a chat with no rhythm known has six empty ones. */
export function values(r: Period[] | null | undefined): number[] {
  const ps = (r ?? []).slice(-DOTS)
  const v = ps.map(intensity)
  return [...Array<number>(DOTS - v.length).fill(0), ...v]
}

/** The chat's own hue: a lane colour chosen by its id. */
export const chatHue = (chatId: string) => projectColor(chatId)

/** A dot's colour at rest: the hue, fuller with more activity. */
export const baseInk = (hue: string, v: number) => `color-mix(in srgb, ${hue} ${Math.round((0.16 + 0.84 * v) * 100)}%, transparent)`

/* ------------------------------------------------------------ the signal */

/** Waiting starts to warm the row after 5 min; amber at 10, red at 20. */
export const WAIT_FROM = 5
export const WAIT_AMBER = 10
export const WAIT_RED = 20
/** Context used, %: warms past 70, amber at 85, red at 95. */
export const CTX_FROM = 70
export const CTX_AMBER = 85
export const CTX_RED = 95

const clamp = (v: number) => Math.max(0, Math.min(v, 1))

/**
 * How much the chat needs the operator, 0–2: 0 calm; up to 1 the row warms
 * toward amber, 1 is amber all over, 2 is red all over.
 */
export function warmth(waiting: boolean, waited: number, ctx: number | null): number {
  const w = !waiting || waited < WAIT_FROM ? 0
    : waited < WAIT_AMBER ? clamp((waited - WAIT_FROM) / (WAIT_AMBER - WAIT_FROM))
      : 1 + clamp((waited - WAIT_AMBER) / (WAIT_RED - WAIT_AMBER))
  const c = ctx === null || ctx <= CTX_FROM ? 0
    // past 70% it shows at once (the chat compacts soon), then fills toward amber
    : ctx <= CTX_AMBER ? 0.4 + 0.6 * clamp((ctx - CTX_FROM) / (CTX_AMBER - CTX_FROM))
      : 1 + clamp((ctx - CTX_AMBER) / (CTX_RED - CTX_AMBER))
  return Math.max(w, c)
}

/** How warm each dot is, 0–1, oldest first: the warmth fills from the right (the newest) leftward. */
export function warmDots(u: number): number[] {
  const n = clamp(u) * DOTS
  return Array.from({ length: DOTS }, (_, i) => clamp(n - (DOTS - 1 - i)))
}

/** The warm colour the whole row moves to: amber up to 1, then toward red. One target, so the row stays one gradient. */
export const warmTarget = (u: number) => (u <= 1 ? 'var(--aq-wait)' : `color-mix(in oklch, var(--aq-down) ${Math.round(clamp(u - 1) * 100)}%, var(--aq-wait))`)

/** A dot's colour: its hue at rest, mixed toward the warm target by how warm it is. */
export function dotInk(hue: string, v: number, k: number, u: number): string {
  const base = baseInk(hue, v)
  return k > 0 ? `color-mix(in oklch, ${warmTarget(u)} ${Math.round(k * 100)}%, ${base})` : base
}

/** What the signal is, for the tooltip: none, waiting, context (the larger wins). */
export function signalKind(waiting: boolean, waited: number, ctx: number | null): 'wait' | 'ctx' | null {
  const w = warmth(waiting, waited, null)
  const c = warmth(false, 0, ctx)
  if (!w && !c) return null
  return w >= c ? 'wait' : 'ctx'
}

/** "13:00–14:00": a period's clock, local. */
export function periodClock(p: Period): string {
  const hm = (iso: string) => (iso.length >= 16 ? iso.slice(11, 16) : '')
  return `${hm(p.start)}–${hm(p.end)}`
}
