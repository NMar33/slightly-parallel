/**
 * Round 5 (tk_d2e11125): the tab's state, quieter than the dots over the
 * tabs. The operator: "меня чутка раздражают эти точки сверху". Each
 * variant is calm at rest and shows only what needs an answer:
 *
 *   now · as now — the dots of strip c, five per part (closed tasks, context, waiting).
 *   a · only when it matters — nothing at rest; a thin line over the tab while
 *       the agent waits 10 min or more (amber, red from 20) or context is over
 *       70% (amber, red over 85); it goes when the state is normal again.
 *   b · ring on the dot — the waiting dot becomes a ring that fills clockwise
 *       over 30 min, green, amber, red; context over 70% is a small mark on it.
 *   c · tab background — the tab fills faintly from the left while the agent
 *       waits; the tint turns amber or red only at the thresholds.
 *   d · one line below — one 1 px line under the tab in the colour of the most
 *       urgent state: waiting, then context, else none.
 *   e · only with Alt — nothing at rest; the dots show while Alt is held,
 *       together with the Alt view.
 *   f · six dots — the operator's idea: six dots in the middle of the top
 *       edge, the chat's mood in its own hue and the signal (./mood.ts).
 *
 * `&tabstate=now|a|b|c|d|e`. Mock facts only (round3/lab/live): waiting grows
 * one mock minute a tick there; context grows here, and compacts at 96%.
 */

import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'

import { SESSIONS } from '../mock'
import { getAqua } from '../store'
import { TICK_MS, factsOf, getLab, patchFacts, type Facts } from '../round3/lab/live'
import { calmMood, tickMood } from './mood'

export const TABSTATE = ['now', 'a', 'b', 'c', 'd', 'e', 'f'] as const
export type TabState = (typeof TABSTATE)[number]
/** The operator's six dots (f), pattern 1, open first. */
export const TABSTATE_DEFAULT: TabState = 'f'

/** Minutes waited before amber and red. */
export const WAIT_AMBER = 10
export const WAIT_RED = 20
/** The ring (b) and the tint (c) are full at this wait. */
export const WAIT_FULL = 30
/** Context used, %: amber over 70, red over 85 — the chat compacts soon. */
export const CTX_AMBER = 70
export const CTX_RED = 85

export type Level = 'green' | 'amber' | 'red'
export const LEVEL_INK: Record<Level, string> = { green: 'var(--aq-up)', amber: 'var(--aq-wait)', red: 'var(--aq-down)' }
const RANK: Record<Level, number> = { green: 0, amber: 1, red: 2 }

export const waitLevel = (min: number): Level => (min >= WAIT_RED ? 'red' : min >= WAIT_AMBER ? 'amber' : 'green')
export const ctxLevel = (ctx: number): Level | null => (ctx > CTX_RED ? 'red' : ctx > CTX_AMBER ? 'amber' : null)

/** What a variant shows on one tab: the state it shows (none at rest), its colour, how far the wait has filled, the context mark (b). */
export interface Signal { kind: 'wait' | 'ctx' | null; level: Level | null; fill: number; notch: Level | null }

export function signal(look: TabState, f: Facts, waiting: boolean): Signal {
  const wl = waiting ? waitLevel(f.waited) : null
  const cl = ctxLevel(f.ctx)
  const fill = waiting ? Math.min(f.waited / WAIT_FULL, 1) : 0
  const none: Signal = { kind: null, level: null, fill, notch: null }
  switch (look) {
    case 'a': {
      const w = wl && wl !== 'green' ? wl : null
      if (w && (!cl || RANK[w] >= RANK[cl])) return { kind: 'wait', level: w, fill, notch: null }
      if (cl) return { kind: 'ctx', level: cl, fill, notch: null }
      return none
    }
    case 'b': return { kind: waiting ? 'wait' : null, level: wl, fill, notch: cl }
    case 'c':
      if (waiting) return { kind: 'wait', level: wl, fill, notch: null }
      if (cl) return { kind: 'ctx', level: cl, fill: 1, notch: null }
      return none
    case 'd':
      if (waiting) return { kind: 'wait', level: wl, fill, notch: null }
      if (cl) return { kind: 'ctx', level: cl, fill, notch: null }
      return none
    // now and e: the dots show the facts themselves; f: the six dots warm by their own rule (mood.ts)
    case 'now':
    case 'e':
    case 'f':
      return none
  }
}

/* ------------------------------------------------------------ the pick */

const isTabState = (v: string | null): v is TabState => (TABSTATE as readonly string[]).includes(v ?? '')

/** The variant from the address (`&tabstate=`); a pick writes the address back. */
export function useTabState(): [TabState, (v: TabState) => void] {
  const [params, setParams] = useSearchParams()
  const v = params.get('tabstate')
  const set = (next: TabState) => setParams((prev) => { const p = new URLSearchParams(prev); p.set('tabstate', next); return p }, { replace: true })
  return [isTabState(v) ? v : TABSTATE_DEFAULT, set]
}

/* ------------------------------------------------------------ time and the jumps */

/** Context a chat is left with after it compacts. */
const CTX_AFTER = 18
const CTX_FULL = 96

/** A mock minute: every working chat's context grows by one; at 96% the chat compacts. */
export function tickContext() {
  const st = getAqua()
  const lab = getLab()
  const patch: Record<string, Partial<Facts>> = {}
  for (const s of SESSIONS) {
    if (s.state !== 'working' || st.asleep[s.id]) continue
    const ctx = factsOf(lab, s).ctx
    patch[s.id] = { ctx: ctx >= CTX_FULL ? CTX_AFTER : ctx + 1 }
  }
  patchFacts(patch)
}

/** Runs the context clock (and the six dots' hours) while L is open. */
export function useContextClock() {
  useEffect(() => {
    const h = setInterval(() => { tickContext(); tickMood() }, TICK_MS)
    return () => clearInterval(h)
  }, [])
}

export type Moment = 'calm' | 'wait' | 'ctx'
export const MOMENTS: Moment[] = ['calm', 'wait', 'ctx']
/** The chat the wait jump sets (Harbor's api-limits, waiting) and the one the context jump sets (calendar-overlap, working). */
export const WAIT_CHAT = 'cc-b03d55e1'
export const CTX_CHAT = 'cc-4e7a19d2'
/** The tab each moment changes. */
export const MOMENT_CHAT: Record<Moment, string> = { calm: WAIT_CHAT, wait: WAIT_CHAT, ctx: CTX_CHAT }

/** The facts of Harbor's four first tabs in each moment: all calm (two chats wait 2 min, context at most 64%), one waits 25 min, context 80%. */
const CALM: Record<string, Partial<Facts>> = {
  'cc-4e7a19d2': { ctx: 64 }, 'cc-b03d55e1': { waited: 2 }, 'cc-c37d2e86': { waited: 2 }, 'cx-0d4b8e37': { ctx: 45 },
}
export const MOMENT_FACTS: Record<Moment, Record<string, Partial<Facts>>> = {
  calm: CALM,
  wait: { ...CALM, [WAIT_CHAT]: { waited: 25 } },
  ctx: { ...CALM, [CTX_CHAT]: { ctx: 80 } },
}

/** The jump buttons: all calm (every wait 2 min at most, every context 60% at most), one chat waits 25 min, context 80%. */
export function jumpTab(m: Moment) {
  if (m === 'calm') {
    const lab = getLab()
    patchFacts(Object.fromEntries(SESSIONS.map((s) => { const f = factsOf(lab, s); return [s.id, { waited: Math.min(f.waited, 2), ctx: Math.min(f.ctx, 60) }] })))
    calmMood()
  } else patchFacts({ [MOMENT_CHAT[m]]: MOMENT_FACTS[m][MOMENT_CHAT[m]]! })
}
