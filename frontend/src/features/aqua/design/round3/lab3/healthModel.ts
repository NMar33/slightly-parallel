/**
 * Round 3 lab 3 (tk_810245f2): health and time in J's window. Mock only:
 * a clock that runs fast, a continuous-work counter, zones and the day's
 * counts. The real timer lives in the app; this is where its look is chosen.
 *
 * - Work time: the counter runs while the operator works and pauses on a
 *   short break; a break of `reset` minutes or more sets it back to zero.
 *   (The real app would read activity; the mock has «Отойти» / «Вернуться».)
 * - Zones by the counter: green, yellow from `yellow` minutes, red from
 *   `red`. Work goes on in every zone; the minutes worked in yellow and in
 *   red are counted apart.
 * - A suggestion is due on entering a zone. «Сделал» logs the action and
 *   asks again in 30 minutes; «Позже» asks again in 15. Within the green
 *   zone, an optional pomodoro (25/5) asks for a short break.
 * - The clock: real time, ×60 (1.5 h in 90 s) or ×600. One step a second.
 * - Reminders (tk_caf2b06a) run beside the zones: an action, an interval, a
 *   series length and a long pause after the series (water every 45 min ×3,
 *   then 3 h). They count work minutes, so a break pauses them. «Отложить»
 *   shifts the whole schedule by 15 minutes; «Перерыв» starts a break, the
 *   work time and the project time stand still while it lasts; «Готово»
 *   (with an optional note) ends it and starts every counter again.
 */

import { useEffect, useSyncExternalStore } from 'react'
import { useSearchParams } from 'react-router-dom'

/* ------------------------------------------------------------ settings */

export type ActId = 'stretch' | 'water' | 'eat' | 'far' | 'walk'
export const ACTS: ActId[] = ['stretch', 'water', 'eat', 'far', 'walk']
export type Zone = 'green' | 'yellow' | 'red'

/** A repeating reminder: `act` every `every` work minutes, `times` in a row, then a pause of `pause` minutes. */
export interface Reminder { id: string; act: ActId; every: number; times: number; pause: number; on: boolean }

export interface HealthSettings {
  yellow: number
  red: number
  /** A break this long, in minutes, sets the counter back to zero. */
  reset: number
  acts: { yellow: ActId[]; red: ActId[] }
  pomo: { on: boolean; work: number; rest: number }
  reminders: Reminder[]
}

export const HEALTH_DEFAULT: HealthSettings = {
  yellow: 90, red: 150, reset: 10,
  acts: { yellow: ['stretch', 'water'], red: ['walk', 'eat'] },
  pomo: { on: false, work: 25, rest: 5 },
  reminders: [
    { id: 'r1', act: 'water', every: 45, times: 3, pause: 180, on: true },
    { id: 'r2', act: 'stretch', every: 60, times: 2, pause: 120, on: true },
  ],
}
export const LATER_MIN = 15
export const AGAIN_MIN = 30

/* ------------------------------------------------------------ state */

export interface Break { at: number; len: number; reset: boolean; note?: string }
/** Where a reminder is in its schedule, in work minutes: due at `next`; `count` done in this series; `paused` after a series. */
export interface RemState { next: number; count: number; paused: boolean }
export interface HealthState {
  s: HealthSettings
  /** Mock minutes since midnight. */
  now: number
  /** Continuous work, minutes. */
  run: number
  /** Work minutes since the mock opened: the reminders' clock, still during a break. */
  wk: number
  rem: Record<string, RemState>
  /** Minutes into the current pomodoro. */
  pomo: number
  /** When the current break began, or null while working. */
  away: number | null
  /** The next suggestion is not shown before this time. */
  nextAt: number
  /** Today, minutes: all projects and this one. */
  day: number
  project: number
  inYellow: number
  inRed: number
  breaks: Break[]
  done: Array<{ at: number; act: ActId }>
  /** What is open: the day card, the settings. */
  ui: { summary: boolean; settings: boolean }
}

const SETTINGS_KEY = 'sp-aqua-lab-health'

/** The part of [a, b) that falls in [lo, hi). */
const overlap = (a: number, b: number, lo: number, hi: number) => Math.max(0, Math.min(b, hi) - Math.max(a, lo))

function readSettings(): HealthSettings {
  try {
    const v = JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? 'null') as HealthSettings | null
    if (v && typeof v.yellow === 'number' && typeof v.red === 'number' && typeof v.reset === 'number' && v.acts && v.pomo) return { ...v, reminders: Array.isArray(v.reminders) ? v.reminders : HEALTH_DEFAULT.reminders }
  } catch { /* private mode */ }
  return HEALTH_DEFAULT
}

/** A working day already under way: 3 h 10 min worked before the current stretch of `run` minutes, two breaks taken. */
const seed = (s: HealthSettings = HEALTH_DEFAULT, run = 0): HealthState => ({
  s, now: 13 * 60 + 5 + run, run, wk: run, rem: {}, pomo: run % s.pomo.work, away: null, nextAt: 0,
  day: 190 + run, project: 95 + run, inYellow: 20 + overlap(0, run, s.yellow, s.red), inRed: overlap(0, run, s.red, Infinity),
  breaks: [{ at: 10 * 60 + 40, len: 15, reset: true }, { at: 12 * 60 + 20, len: 35, reset: true }],
  done: [], ui: { summary: false, settings: false },
})

/** A frozen state for K's compare view: `run` minutes without a break, on a break of `away` minutes if given. */
export function healthAt(run: number, away?: number): HealthState {
  const h = seed(HEALTH_DEFAULT, run)
  return away === undefined ? h : { ...h, now: h.now + away, away: h.now }
}

let state = seed()
let settingsRead = false
const ls = new Set<() => void>()
const emit = () => { for (const l of ls) l() }
const put = (p: Partial<HealthState>) => { state = { ...state, ...p }; emit() }
const sub = (l: () => void) => { ls.add(l); return () => { ls.delete(l) } }
const snap = () => { if (!settingsRead) { settingsRead = true; state = { ...state, s: readSettings() } } return state }
export const useHealth = () => useSyncExternalStore(sub, snap, () => state)
export const getHealth = () => snap()

/** Back to the start of the mock day, with the default settings unless `keep`. */
export function resetHealth(run = 0, keep = false) { settingsRead = true; state = seed(keep ? state.s : HEALTH_DEFAULT, run); emit() }

export function setHealthSettings(patch: Partial<HealthSettings>) {
  const s = { ...snap().s, ...patch }
  if (s.red <= s.yellow) s.red = s.yellow + 1
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)) } catch { /* private mode */ }
  put({ s })
}

export const zoneOf = (run: number, s: HealthSettings): Zone => (run >= s.red ? 'red' : run >= s.yellow ? 'yellow' : 'green')
const rank: Record<Zone, number> = { green: 0, yellow: 1, red: 2 }


/** The mock clock moves `dm` minutes. Working: the counters grow, split exactly at the thresholds. */
export function tickHealth(dm: number) {
  const h = snap()
  if (h.away !== null) { put({ now: h.now + dm }); return }
  const run = h.run + dm
  const before = zoneOf(h.run, h.s), after = zoneOf(run, h.s)
  put({
    now: h.now + dm, run, wk: h.wk + dm, pomo: h.pomo + dm, day: h.day + dm, project: h.project + dm,
    inYellow: h.inYellow + overlap(h.run, run, h.s.yellow, h.s.red),
    inRed: h.inRed + overlap(h.run, run, h.s.red, Infinity),
    // a new zone asks at once, whatever was put off before
    nextAt: rank[after] > rank[before] ? h.now + dm : h.nextAt,
  })
}

export type Due =
  | { kind: 'yellow' | 'red'; act: ActId; acts: ActId[] }
  | { kind: 'remind'; id: string; act: ActId; n: number; r: Reminder }
  | { kind: 'pomo' }
  | null

/** A reminder's place in its schedule; a new one is first due one interval in. */
export const remOf = (h: HealthState, r: Reminder): RemState => h.rem[r.id] ?? { next: r.every, count: 0, paused: false }

/** What is suggested now, if anything: a zone first, then a reminder, then the pomodoro. A zone's actions take turns. */
export function dueOf(h: HealthState): Due {
  if (h.away !== null) return null
  const zone = zoneOf(h.run, h.s)
  if (zone !== 'green' && h.now >= h.nextAt) {
    const acts = h.s.acts[zone]
    if (acts.length) {
      const n = h.done.filter((d) => acts.includes(d.act)).length
      return { kind: zone, act: acts[n % acts.length]!, acts }
    }
  }
  for (const r of h.s.reminders) {
    if (!r.on) continue
    const st = remOf(h, r)
    if (h.wk >= st.next) return { kind: 'remind', id: r.id, act: r.act, n: st.count + 1, r }
  }
  if (zone === 'green' && h.now >= h.nextAt && h.s.pomo.on && h.pomo >= h.s.pomo.work) return { kind: 'pomo' }
  return null
}

/** A reminder answered: the next one in its series, or the long pause after the last. */
function advance(h: HealthState, r: Reminder): Record<string, RemState> {
  const st = remOf(h, r)
  const count = st.count + 1
  const end = count >= r.times
  return { ...h.rem, [r.id]: end ? { next: h.wk + r.pause, count: 0, paused: true } : { next: h.wk + r.every, count, paused: false } }
}

/** «Сделал»: the action is logged; a zone asks again in 30 minutes, a reminder moves on in its series. On a pomodoro it starts the break. */
export function didIt() {
  const h = snap()
  const due = dueOf(h)
  if (!due) return
  if (due.kind === 'pomo') { startBreak(); return }
  if (due.kind === 'remind') { put({ done: [...h.done, { at: h.now, act: due.act }], rem: advance(h, due.r) }); return }
  put({ done: [...h.done, { at: h.now, act: due.act }], nextAt: h.now + AGAIN_MIN })
}

/** «Перерыв» on a suggestion: it counts as answered, and a break begins. */
export function breakNow() {
  const h = snap()
  const due = dueOf(h)
  if (due?.kind === 'remind') put({ rem: advance(h, due.r) })
  else if (due && due.kind !== 'pomo') put({ nextAt: h.now + AGAIN_MIN })
  startBreak()
}

/** «Позже» / «Отложить»: the whole schedule moves 15 minutes on — the zone's suggestion, the pomodoro and every reminder due within that time. */
export function later() {
  const h = snap()
  const rem = { ...h.rem }
  for (const r of h.s.reminders) { const st = remOf(h, r); rem[r.id] = { ...st, next: Math.max(st.next, h.wk) + LATER_MIN } }
  put({ nextAt: h.now + LATER_MIN, rem })
}

export function startBreak() { const h = snap(); if (h.away === null) put({ away: h.now }) }

/** Back from a break: a long one sets the counter to zero; any break of the pomodoro's rest restarts the pomodoro. */
export function endBreak() {
  const h = snap()
  if (h.away === null) return
  const len = h.now - h.away
  const reset = len >= h.s.reset
  put({
    away: null, breaks: [...h.breaks, { at: h.away, len, reset }],
    run: reset ? 0 : h.run, pomo: len >= Math.min(h.s.pomo.rest, h.s.reset) ? 0 : h.pomo, nextAt: h.now,
  })
}

/** «Готово» after a break: the note is kept with the break, and every counter starts again — the run, the pomodoro, each reminder's interval (one in its long pause keeps it). */
export function finishBreak(note = '') {
  const h = snap()
  if (h.away === null) return
  const rem = { ...h.rem }
  for (const r of h.s.reminders) { const st = remOf(h, r); if (!st.paused) rem[r.id] = { ...st, next: h.wk + r.every } }
  const n = note.trim()
  put({
    away: null, breaks: [...h.breaks, { at: h.away, len: h.now - h.away, reset: true, ...(n ? { note: n } : {}) }],
    run: 0, pomo: 0, nextAt: h.now, rem,
  })
}

let made = 0
/** A new reminder in the settings: the first action no reminder has yet. */
export function addReminder() {
  const s = snap().s
  const act = ACTS.find((a) => !s.reminders.some((r) => r.act === a)) ?? 'water'
  made += 1
  setHealthSettings({ reminders: [...s.reminders, { id: `r${Date.now().toString(36)}${made}`, act, every: 30, times: 3, pause: 60, on: true }] })
}
export function setReminder(id: string, patch: Partial<Reminder>) {
  setHealthSettings({ reminders: snap().s.reminders.map((r) => (r.id === id ? { ...r, ...patch } : r)) })
}
export function removeReminder(id: string) { setHealthSettings({ reminders: snap().s.reminders.filter((r) => r.id !== id) }) }

/** The lab's jump buttons: the clock runs on to a minute before the zone (counted as work); green is a long break. */
export function jumpTo(zone: Zone) {
  const h = snap()
  if (h.away !== null) endBreak()
  if (zone === 'green') { startBreak(); tickHealth(snap().s.reset); endBreak(); return }
  const to = zone === 'yellow' ? h.s.yellow - 1 : h.s.red - 1
  if (to > snap().run) tickHealth(to - snap().run)
  else put({ run: to })
}

export function openUi(p: Partial<HealthState['ui']>) { put({ ui: { ...snap().ui, ...p } }) }

/* ------------------------------------------------------------ words for numbers */

/** 94 → "1:34". */
export const clockOf = (min: number) => { const m = Math.floor(min); return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}` }
/** 13:05 for a time of day. */
export const timeOfDay = (min: number) => { const m = Math.floor(min) % (24 * 60); return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}` }

/* ------------------------------------------------------------ the variants and the clock */

export const HEALTH_VARIANTS = ['a', 'b', 'c', 'd'] as const
export type HealthLook = (typeof HEALTH_VARIANTS)[number]
export const CLOCKS = [1, 60, 600] as const
export type Clock = (typeof CLOCKS)[number]
export const HEALTH_LOOK_DEFAULT: HealthLook = 'b'
export const CLOCK_DEFAULT: Clock = 60

/** `&health=a|b|c` and `&clock=1|60|600` from the address; a pick writes it back. */
export function useHealthPick(): { look: HealthLook; clock: Clock; setLook: (v: HealthLook) => void; setClock: (v: Clock) => void } {
  const [params, setParams] = useSearchParams()
  const h = params.get('health'), c = Number(params.get('clock'))
  const look = (HEALTH_VARIANTS as readonly string[]).includes(h ?? '') ? h as HealthLook : HEALTH_LOOK_DEFAULT
  const clock = (CLOCKS as readonly number[]).includes(c) ? c as Clock : CLOCK_DEFAULT
  const set = (k: string, v: string) => setParams((prev) => { const next = new URLSearchParams(prev); next.set(k, v); return next }, { replace: true })
  return { look, clock, setLook: (v) => set('health', v), setClock: (v) => set('clock', String(v)) }
}

export const STEP_MS = 1000

/** Runs the mock clock: one step a second, `clock` mock seconds per real second. `&work=N` starts the counter at N minutes. */
export function useHealthClock() {
  const { clock } = useHealthPick()
  const [params] = useSearchParams()
  useEffect(() => {
    const w = Number(params.get('work'))
    if (w > 0) resetHealth(w, true)
    // the address is read once, when J opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    const h = setInterval(() => tickHealth(clock / 60), STEP_MS)
    return () => clearInterval(h)
  }, [clock])
}

/** The lab's jump to the next reminder: the clock runs on to the earliest one (counted as work). */
export function jumpToReminder() {
  const h = snap()
  if (h.away !== null) endBreak()
  const nexts = snap().s.reminders.filter((r) => r.on).map((r) => remOf(snap(), r).next)
  if (!nexts.length) return
  const at = Math.min(...nexts)
  if (at > snap().wk) tickHealth(at - snap().wk)
}
