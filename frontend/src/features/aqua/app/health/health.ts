/**
 * Health and time in the terminal window, variant a «quiet» (tk_810245f2,
 * tk_caf2b06a). The look was chosen in the mockup
 * (design/round3/lab3/health.ts, Health.tsx); this is the product's state,
 * on real time and real activity.
 *
 * What the counter counts — continuous work, in minutes:
 * - the operator is working at a moment when there was input no more than
 *   READING_MS (two minutes, the smart timer's rule, time/beats.ts) before
 *   it. Input is the window's own keys, clicks, wheel, pastes and pointer
 *   moves, and the computer's input anywhere (the server's idle reading,
 *   GET /api/time/auto `idle_sec`), so work in an editor counts too;
 * - a gap with no input of `reset` minutes or more sets it to zero (and
 *   is kept as a break of the day); a shorter gap only stands it still
 *   past the two minutes of reading;
 * - «Перерыв» stands it still and stops the project's time on the server
 *   (POST /api/time/auto/break); «Готово» sets it to zero.
 *
 * Zones by the counter: green, yellow from `yellow` minutes, red from `red`.
 * Today's minutes in yellow and red, the breaks and the actions done are
 * kept in localStorage under the date, so a reload keeps them.
 */

import { useSyncExternalStore } from 'react'

import { postJson } from '../../../../lib/getJson'
import { persistPref } from '../../../../lib/uiPrefs'
import { READING_MS } from '../../../time/beats'

/* ------------------------------------------------------------ settings */

export type ActId = 'stretch' | 'water' | 'eat' | 'far' | 'walk'
export const ACTS: ActId[] = ['stretch', 'water', 'eat', 'far', 'walk']
export type Zone = 'green' | 'yellow' | 'red'

/** A repeating reminder: `act` every `every` work minutes, `times` in a row, then a pause of `pause` minutes. */
export interface Reminder { id: string; act: ActId; every: number; times: number; pause: number; on: boolean }

export interface HealthSettings {
  /** Off: nothing is drawn and nothing counts. */
  on: boolean
  yellow: number
  red: number
  /** A gap or a break this long, in minutes, sets the counter back to zero. */
  reset: number
  acts: { yellow: ActId[]; red: ActId[] }
  pomo: { on: boolean; work: number; rest: number }
  reminders: Reminder[]
}

export const HEALTH_DEFAULT: HealthSettings = {
  on: true, yellow: 90, red: 150, reset: 10,
  acts: { yellow: ['stretch', 'water'], red: ['walk', 'eat'] },
  pomo: { on: false, work: 25, rest: 5 },
  reminders: [
    { id: 'r1', act: 'water', every: 45, times: 3, pause: 180, on: true },
    { id: 'r2', act: 'stretch', every: 60, times: 2, pause: 120, on: true },
  ],
}
export const LATER_MIN = 15
export const AGAIN_MIN = 30
export const SETTINGS_KEY = 'sp-term-health'
export const DAY_KEY = 'sp-term-health-day'
const MIN = 60_000

const num = (v: unknown, lo: number, hi: number, d: number) => (typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi ? Math.round(v) : d)
const acts = (v: unknown, d: ActId[]) => (Array.isArray(v) ? v.filter((a): a is ActId => ACTS.includes(a as ActId)) : d)

/** Whatever was stored, made whole: a missing or wrong field takes its default. */
export function cleanSettings(v: unknown): HealthSettings {
  const d = HEALTH_DEFAULT
  if (!v || typeof v !== 'object') return d
  const o = v as Partial<HealthSettings>
  const yellow = num(o.yellow, 1, 1440, d.yellow)
  const red = Math.max(num(o.red, 2, 1440, d.red), yellow + 1)
  const pomo = (o.pomo && typeof o.pomo === 'object' ? o.pomo : {}) as Partial<HealthSettings['pomo']>
  const reminders = Array.isArray(o.reminders)
    ? o.reminders.filter((r): r is Reminder => !!r && typeof r === 'object' && typeof r.id === 'string' && ACTS.includes(r.act)).map((r) => ({
      id: r.id, act: r.act, every: num(r.every, 1, 600, 45), times: num(r.times, 1, 20, 3), pause: num(r.pause, 1, 1440, 60), on: r.on !== false,
    }))
    : d.reminders
  return {
    on: o.on !== false, yellow, red, reset: num(o.reset, 1, 120, d.reset),
    acts: { yellow: acts(o.acts?.yellow, d.acts.yellow), red: acts(o.acts?.red, d.acts.red) },
    pomo: { on: pomo.on === true, work: num(pomo.work, 1, 120, d.pomo.work), rest: num(pomo.rest, 1, 60, d.pomo.rest) },
    reminders,
  }
}

export function readSettings(): HealthSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    return raw ? cleanSettings(JSON.parse(raw)) : HEALTH_DEFAULT
  } catch { return HEALTH_DEFAULT }
}

/* ------------------------------------------------------------ the day */

/** A break: when it began (ms), its length (min), whether it set the counter to zero, a note; `idle` for a gap with no input. */
export interface Break { at: number; len: number; reset: boolean; note?: string; idle?: boolean }
/** Where a reminder is in its schedule, in work minutes: due at `next`; `count` done in this series; `paused` after a series. */
export interface RemState { next: number; count: number; paused: boolean }

/** What one day holds. Minutes are minutes of work; moments are ms since the epoch. */
export interface Day {
  date: string
  /** Continuous work, minutes. */
  run: number
  /** Work minutes today: the reminders' clock, still during a break. */
  wk: number
  pomo: number
  inYellow: number
  inRed: number
  /** The last moment counted. */
  at: number
  /** The last input seen (0: none yet). */
  input: number
  /** When the break under way began, or null. */
  away: number | null
  /** The next zone suggestion or pomodoro is not shown before this moment. */
  nextAt: number
  rem: Record<string, RemState>
  breaks: Break[]
  done: Array<{ at: number; act: ActId }>
}

export const dateOf = (ms: number) => {
  const d = new Date(ms)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export const freshDay = (now: number): Day => ({
  date: dateOf(now), run: 0, wk: 0, pomo: 0, inYellow: 0, inRed: 0, at: now, input: 0, away: null, nextAt: 0, rem: {}, breaks: [], done: [],
})

/** A new date: the day's counts start again; the stretch under way, the last input and a break go on. */
export function rollDay(d: Day, now: number): Day {
  if (d.date === dateOf(now)) return d
  return { ...freshDay(now), run: d.run, pomo: d.pomo, at: d.at, input: d.input, away: d.away, nextAt: d.nextAt }
}

export const zoneOf = (run: number, s: HealthSettings): Zone => (run >= s.red ? 'red' : run >= s.yellow ? 'yellow' : 'green')
const rank: Record<Zone, number> = { green: 0, yellow: 1, red: 2 }
const overlap = (a: number, b: number, lo: number, hi: number) => Math.max(0, Math.min(b, hi) - Math.max(a, lo))

/** Work from moment `a` to `b`: the counters grow, split exactly at the thresholds; a new zone asks at once. */
function work(d: Day, a: number, b: number, s: HealthSettings): Day {
  if (b <= a) return d
  const dm = (b - a) / MIN
  const run = d.run + dm
  const up = rank[zoneOf(run, s)] > rank[zoneOf(d.run, s)]
  return {
    ...d, run, wk: d.wk + dm, pomo: d.pomo + dm,
    inYellow: d.inYellow + overlap(d.run, run, s.yellow, s.red),
    inRed: d.inRed + overlap(d.run, run, s.red, Infinity),
    nextAt: up ? b : d.nextAt,
  }
}

/**
 * The clock moves to `now`; `seen` is the latest input known (the window's
 * or the computer's). Work is a moment with input up to READING_MS before
 * it; a gap with no input of `reset` minutes is a break that zeroes the
 * counter. Between steps only the latest input is known, so the runtime
 * steps on every input (at most once a second) and every few seconds.
 */
export function step(d: Day, now: number, seen: number, s: HealthSettings): Day {
  const input = Math.max(d.input, seen)
  if (now <= d.at) return input === d.input ? d : { ...d, input }
  if (d.away !== null) return { ...d, at: now, input }
  const resetMs = s.reset * MIN
  const prevEnd = d.input ? d.input + READING_MS : -Infinity
  let x = d
  if (d.input && input - d.input >= resetMs) {
    // a long gap between two inputs: the stretch before it ends, a break, a new stretch
    x = work(x, d.at, Math.min(now, prevEnd), s)
    x = { ...x, run: 0, pomo: 0, nextAt: input, breaks: [...x.breaks, { at: d.input, len: (input - d.input) / MIN, reset: true, idle: true }] }
    x = work(x, Math.max(d.at, input), Math.min(now, input + READING_MS), s)
  } else if (input > 0 && input <= prevEnd) {
    x = work(x, d.at, Math.min(now, input + READING_MS), s)
  } else {
    x = work(x, d.at, Math.min(now, prevEnd), s)
    if (input > 0) x = work(x, Math.max(d.at, input), Math.min(now, input + READING_MS), s)
  }
  // no input for `reset` minutes: the counter already shows zero; the break is kept when input comes back
  if (input && now - input >= resetMs && x.run > 0) x = { ...x, run: 0, pomo: 0 }
  return { ...x, at: now, input }
}

/* ------------------------------------------------------------ what is due */

export type Due =
  | { kind: 'yellow' | 'red'; act: ActId; acts: ActId[] }
  | { kind: 'remind'; id: string; act: ActId; n: number; r: Reminder }
  | { kind: 'pomo' }
  | null

/** A reminder's place in its schedule; a new one is first due one interval in. */
export const remOf = (d: Day, r: Reminder): RemState => d.rem[r.id] ?? { next: r.every, count: 0, paused: false }

/** What is suggested at `now`, if anything: a zone first, then a reminder, then the pomodoro. A zone's actions take turns. */
export function dueOf(d: Day, s: HealthSettings, now: number): Due {
  if (d.away !== null || !s.on) return null
  const zone = zoneOf(d.run, s)
  if (zone !== 'green' && now >= d.nextAt) {
    const list = s.acts[zone]
    if (list.length) {
      const n = d.done.filter((x) => list.includes(x.act)).length
      return { kind: zone, act: list[n % list.length]!, acts: list }
    }
  }
  for (const r of s.reminders) {
    if (!r.on) continue
    const st = remOf(d, r)
    if (d.wk >= st.next) return { kind: 'remind', id: r.id, act: r.act, n: st.count + 1, r }
  }
  if (zone === 'green' && now >= d.nextAt && s.pomo.on && d.pomo >= s.pomo.work) return { kind: 'pomo' }
  return null
}

/** A reminder answered: the next one in its series, or the long pause after the last. */
function advance(d: Day, r: Reminder): Record<string, RemState> {
  const st = remOf(d, r)
  const count = st.count + 1
  const end = count >= r.times
  return { ...d.rem, [r.id]: end ? { next: d.wk + r.pause, count: 0, paused: true } : { next: d.wk + r.every, count, paused: false } }
}

/** «Сделал»: logged; a zone asks again in 30 minutes, a reminder moves on. On a pomodoro: null — the caller starts the break. */
export function didItDay(d: Day, s: HealthSettings, now: number): Day | null {
  const due = dueOf(d, s, now)
  if (!due) return d
  if (due.kind === 'pomo') return null
  if (due.kind === 'remind') return { ...d, done: [...d.done, { at: now, act: due.act }], rem: advance(d, due.r) }
  return { ...d, done: [...d.done, { at: now, act: due.act }], nextAt: now + AGAIN_MIN * MIN }
}

/** «Позже»: the whole schedule moves 15 minutes on — the zone's suggestion, the pomodoro and every reminder. */
export function laterDay(d: Day, s: HealthSettings, now: number): Day {
  const rem = { ...d.rem }
  for (const r of s.reminders) { const st = remOf(d, r); rem[r.id] = { ...st, next: Math.max(st.next, d.wk) + LATER_MIN } }
  return { ...d, nextAt: now + LATER_MIN * MIN, rem }
}

/** «Перерыв» on a suggestion counts as answered; then the break begins. */
export function breakNowDay(d: Day, s: HealthSettings, now: number): Day {
  const due = dueOf(d, s, now)
  let x = d
  if (due?.kind === 'remind') x = { ...d, rem: advance(d, due.r) }
  else if (due && due.kind !== 'pomo') x = { ...d, nextAt: now + AGAIN_MIN * MIN }
  return startBreakDay(x, now)
}

export function startBreakDay(d: Day, now: number): Day {
  return d.away === null ? { ...d, away: now, at: now } : d
}

/** «Готово»: the break is kept with its note; every counter starts again — the run, the pomodoro, each reminder's interval (one in its long pause keeps it). */
export function finishBreakDay(d: Day, s: HealthSettings, now: number, note = ''): Day {
  if (d.away === null) return d
  const rem = { ...d.rem }
  for (const r of s.reminders) { const st = remOf(d, r); if (!st.paused) rem[r.id] = { ...st, next: d.wk + r.every } }
  const n = note.trim()
  return {
    ...d, away: null, at: now, input: Math.max(d.input, now), run: 0, pomo: 0, nextAt: now, rem,
    breaks: [...d.breaks, { at: d.away, len: Math.max(0, now - d.away) / MIN, reset: true, ...(n ? { note: n } : {}) }],
  }
}

/* ------------------------------------------------------------ the store */

export interface HealthState {
  s: HealthSettings
  d: Day
  now: number
  /** The project of the tab in front. */
  project: string
  ui: { summary: boolean; settings: boolean }
}

/** The day stored for its date, or a fresh one. */
export function readDay(now: number): Day {
  try {
    const v = JSON.parse(localStorage.getItem(DAY_KEY) ?? 'null') as Day | null
    if (v && typeof v === 'object' && typeof v.run === 'number' && typeof v.at === 'number' && Array.isArray(v.breaks) && Array.isArray(v.done) && v.rem) {
      return rollDay({ ...freshDay(now), ...v }, now)
    }
  } catch { /* private mode, damaged */ }
  return freshDay(now)
}

let state: HealthState | null = null
let lastSaved = 0
const ls = new Set<() => void>()
const emit = () => { for (const l of ls) l() }
const sub = (l: () => void) => { ls.add(l); return () => { ls.delete(l) } }
const clock = { now: () => Date.now() }

function snap(): HealthState {
  if (!state) { const now = clock.now(); state = { s: readSettings(), d: readDay(now), now, project: '', ui: { summary: false, settings: false } } }
  return state
}

function saveDay(d: Day, force = false) {
  const now = clock.now()
  if (!force && now - lastSaved < 5000) return
  lastSaved = now
  try { localStorage.setItem(DAY_KEY, JSON.stringify(d)) } catch { /* private mode */ }
}

function put(p: Partial<HealthState>, force = false) {
  const prev = snap()
  state = { ...prev, ...p }
  if (p.d && p.d !== prev.d) saveDay(p.d, force)
  emit()
}

export const useHealth = () => useSyncExternalStore(sub, snap, snap)
export const getHealth = () => snap()

/** Tests: a clean store, and their own clock. */
export function resetHealthStore(now?: () => number) {
  state = null
  lastSaved = 0
  clock.now = now ?? (() => Date.now())
}

export const nowMs = () => clock.now()

export function setHealthSettings(patch: Partial<HealthSettings>) {
  const s = cleanSettings({ ...snap().s, ...patch })
  persistPref(SETTINGS_KEY, JSON.stringify(s))
  put({ s })
}

/** The settings changed elsewhere (the Settings page, another window): read them again. */
export function reloadSettings() { const s = readSettings(); if (JSON.stringify(s) !== JSON.stringify(snap().s)) put({ s }) }

export function setProject(project: string) { if (snap().project !== project) put({ project }) }

/** The clock moves to now with the latest input known. */
export function tick(seen = 0) {
  const h = snap()
  if (!h.s.on) return
  const now = clock.now()
  const d = step(rollDay(h.d, now), now, seen, h.s)
  if (d === h.d && now === h.now) return
  put({ d, now })
}

/* ------------------------------------------------------------ the operator's answers */

/** The server's side of a break: the project's time stops (POST /api/time/auto/break). A failure leaves the window's break as it is. */
const sendBreak = (on: boolean, note = '') => postJson('/api/time/auto/break', on ? { on } : { on, note }).catch(() => undefined)

export function didIt() {
  const h = snap(); const now = clock.now()
  const d = didItDay(h.d, h.s, now)
  if (d === null) { startBreak(); return }
  put({ d, now }, true)
}

export function later() { const h = snap(); const now = clock.now(); put({ d: laterDay(h.d, h.s, now), now }, true) }

export function breakNow() {
  const h = snap(); const now = clock.now()
  if (h.d.away !== null) return
  put({ d: breakNowDay(step(h.d, now, 0, h.s), h.s, now), now }, true)
  void sendBreak(true)
}

export function startBreak() {
  const h = snap(); const now = clock.now()
  if (h.d.away !== null) return
  put({ d: startBreakDay(step(h.d, now, 0, h.s), now), now }, true)
  void sendBreak(true)
}

export function finishBreak(note = '') {
  const h = snap(); const now = clock.now()
  if (h.d.away === null) return
  put({ d: finishBreakDay(h.d, h.s, now, note), now }, true)
  void sendBreak(false, note.trim())
}

/** The server's word on a break, read when the window opens: a break it holds is under way here too; one it ended is ended here. */
export function adoptServerBreak(on: boolean, sinceMs: number | null) {
  const h = snap(); const now = clock.now()
  if (on && h.d.away === null) put({ d: startBreakDay(h.d, sinceMs && sinceMs <= now ? sinceMs : now), now }, true)
  else if (!on && h.d.away !== null) put({ d: finishBreakDay(h.d, h.s, now), now }, true)
}

let made = 0
/** A new reminder: the first action no reminder has yet. */
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

export function openUi(p: Partial<HealthState['ui']>) { put({ ui: { ...snap().ui, ...p } }) }

/** Before the window goes: the day as it is now. */
export function flushDay() { saveDay(snap().d, true) }

/* ------------------------------------------------------------ words for numbers */

/** 94 → "1:34". */
export const clockOf = (min: number) => { const m = Math.max(0, Math.floor(min)); return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}` }
/** 13:05 for a moment. */
export const timeOfDay = (ms: number) => { const d = new Date(ms); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` }
