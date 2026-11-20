/**
 * Round 5, variant f (the operator's idea, tk_d2e11125): six dots in the
 * middle of the tab's top edge — the chat's mood and a signal. "Чтобы они не
 * были вразнобой, чтобы элегантно смотрелось, и это не просто сигнал, а ещё
 * и муд чата": one hue per chat, colour that builds up slowly, a pattern that
 * differs per chat; when the chat needs the operator the row warms from the
 * right toward amber, then red.
 *
 * The pattern («Рисунок», `&pattern=1|2|3`):
 *   1 · rhythm — the six dots are the last six hours, oldest on the left;
 *       a dot's colour builds up with that hour's activity.
 *   2 · constellation — the same hours; the dot also sits up to 2 px higher
 *       or lower with the activity: a small sparkline of dots.
 *   3 · six properties — each dot one fact (waiting, context, uncommitted
 *       changes, time since the last check, tasks closed, commits today),
 *       more of it is a fuller colour.
 * Activity of an hour = messages + 3 × commits + 4 × tasks closed + tokens
 * (thousands) / 10, full at 30. Mock data only.
 */

import { createContext, useContext, useSyncExternalStore } from 'react'
import { useSearchParams } from 'react-router-dom'

import { SESSIONS, type Session } from '../mock'
import { getAqua } from '../store'
import type { Facts } from '../round3/lab/live'
import { CTX_AMBER, CTX_RED } from './tabStateModel'

export const PATTERNS = ['1', '2', '3'] as const
export type Pattern = (typeof PATTERNS)[number]
export const PATTERN_DEFAULT: Pattern = '1'

/** One hour of a chat: messages, commits, tasks closed, tokens in thousands. */
export interface Hour { msgs: number; commits: number; tasks: number; tok: number }
export interface Mood { hours: Hour[]; uncommitted: number; checkAgo: number; checkFailed: boolean; commitsToday: number }

const h = (msgs: number, commits = 0, tasks = 0, tok = msgs * 3): Hour => ({ msgs, commits, tasks, tok })
/** Six different histories, so every row looks its own. */
const SEED: Record<string, Omit<Mood, 'commitsToday'>> = {
  // steady, heavy work all afternoon
  'cc-4e7a19d2': { hours: [h(12, 2, 1), h(8, 1), h(15, 3, 1), h(10, 1), h(14, 2, 1), h(9, 1)], uncommitted: 4, checkAgo: 12, checkFailed: false },
  // a burst early, quiet since: it waits
  'cc-b03d55e1': { hours: [h(20, 3, 1), h(16, 2, 1), h(4), h(2), h(1), h(3)], uncommitted: 0, checkAgo: 160, checkFailed: false },
  // slow start, growing
  'cc-c37d2e86': { hours: [h(0), h(2), h(5), h(9, 1), h(14, 2, 1), h(6)], uncommitted: 7, checkAgo: 40, checkFailed: false },
  // on and off
  'cx-0d4b8e37': { hours: [h(10, 1), h(2), h(12, 2, 1), h(3), h(13, 2), h(11, 1, 1)], uncommitted: 2, checkAgo: 25, checkFailed: false },
  // a light, late start
  'cc-5a0f7e19': { hours: [h(0), h(0), h(3), h(4, 1), h(6), h(8, 1)], uncommitted: 3, checkAgo: 60, checkFailed: false },
  // busy once, idle now
  'cx-91c2f0a7': { hours: [h(6, 1), h(9, 1, 1), h(1), h(0), h(0), h(0)], uncommitted: 0, checkAgo: 240, checkFailed: false },
}

/** The other chats: a history from their id, so it is stable. */
function seedOf(s: Session): Mood {
  let x = 0
  for (const ch of s.id) x = (x * 31 + ch.charCodeAt(0)) >>> 0
  const base = SEED[s.id] ?? {
    hours: Array.from({ length: 6 }, (_, i) => h(((x >>> (i * 3)) % 7) * (s.state === 'idle' ? 1 : 2))),
    uncommitted: x % 6, checkAgo: 30 + (x % 90), checkFailed: false,
  }
  return { ...base, hours: base.hours.map((y) => ({ ...y })), commitsToday: base.hours.reduce((n, y) => n + y.commits, 0) }
}

export type MoodLab = { moods: Record<string, Mood>; tick: number }
export const freshMood = (over: Record<string, Partial<Mood>> = {}): MoodLab => ({
  moods: Object.fromEntries(SESSIONS.map((s) => [s.id, { ...seedOf(s), ...over[s.id] }])),
  tick: 0,
})
export const moodOf = (l: MoodLab, s: Session): Mood => l.moods[s.id] ?? seedOf(s)

let lab = freshMood()
const listeners = new Set<() => void>()
const emit = () => { for (const l of listeners) l() }
export const getMood = () => lab
export const useMoodLab = () => useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l) } }, () => lab, () => lab)
export function resetMood() { lab = freshMood(); emit() }
function patch(id: string, f: (m: Mood) => Mood) {
  const s = SESSIONS.find((x) => x.id === id)
  if (!s) return
  lab = { ...lab, moods: { ...lab.moods, [id]: f(moodOf(lab, s)) } }
  emit()
}

/** A mock minute: a working chat's current hour gains a message and tokens; every 60th minute a new hour starts. */
export function tickMood() {
  const st = getAqua()
  const n = lab.tick + 1
  const moods = { ...lab.moods }
  for (const s of SESSIONS) {
    const m = moodOf(lab, s)
    const working = s.state === 'working' && !st.asleep[s.id]
    let hours = m.hours
    if (n % 60 === 0) hours = [...hours.slice(1), h(0, 0, 0, 0)]
    if (working) hours = [...hours.slice(0, 5), { ...hours[5]!, msgs: hours[5]!.msgs + 1, tok: hours[5]!.tok + 4 }]
    moods[s.id] = { ...m, hours, checkAgo: m.checkAgo + 1 }
  }
  lab = { moods, tick: n }
  emit()
}

/** «+3 коммита»: three commits in the chat's current hour; its changes are committed. */
export function addCommits(id: string, n = 3) {
  patch(id, (m) => ({ ...m, hours: [...m.hours.slice(0, 5), { ...m.hours[5]!, commits: m.hours[5]!.commits + n }], commitsToday: m.commitsToday + n, uncommitted: 0 }))
}
/** «Проверка упала» / back: the chat's last check failed just now, or passed. */
export function setCheck(id: string, failed: boolean) { patch(id, (m) => ({ ...m, checkFailed: failed, checkAgo: 0 })) }
/** «Всё спокойно» clears the failed checks too. */
export function calmMood() {
  lab = { ...lab, moods: Object.fromEntries(Object.entries(lab.moods).map(([id, m]) => [id, { ...m, checkFailed: false }])) }
  emit()
}

/* ------------------------------------------------------------ what the dots show */

/** An hour's activity, 0–1. */
export const activity = (y: Hour) => Math.min((y.msgs + 3 * y.commits + 4 * y.tasks + y.tok / 10) / 30, 1)

/** The six values, 0–1, left to right. */
export function values(p: Pattern, m: Mood, f: Facts, waiting: boolean): number[] {
  if (p !== '3') return m.hours.map(activity)
  return [
    waiting ? Math.min(f.waited / 30, 1) : 0,
    f.ctx / 100,
    Math.min(m.uncommitted / 12, 1),
    Math.min(m.checkAgo / 180, 1),
    f.all ? f.done / f.all : 0,
    Math.min(m.commitsToday / 10, 1),
  ]
}

/** Waiting starts to warm the row after 5 min. */
export const MOOD_WAIT = 5

/**
 * How much the chat needs the operator, 0–2: 0 calm; up to 1 the row warms
 * toward amber (waiting 5 → 10 min, context 70 → 85%); past 1 toward red
 * (waiting 10 → 20 min, context 85 → 95%); a failed check is 1.5.
 */
export function warmth(f: Facts, waiting: boolean, m: Mood): number {
  const clamp = (v: number) => Math.max(0, Math.min(v, 1))
  const w = !waiting || f.waited < MOOD_WAIT ? 0 : f.waited < 10 ? clamp((f.waited - MOOD_WAIT) / 5) : 1 + clamp((f.waited - 10) / 10)
  const c = f.ctx <= CTX_AMBER ? 0 : f.ctx <= CTX_RED ? 0.4 + 0.6 * clamp((f.ctx - CTX_AMBER) / (CTX_RED - CTX_AMBER)) : 1 + clamp((f.ctx - CTX_RED) / 10)
  return Math.max(w, c, m.checkFailed ? 1.5 : 0)
}

/** How warm each dot is, 0–1, left to right: the warmth fills from the right (the newest) leftward — three dots at amber, all six at red. */
export function warmDots(u: number): number[] {
  const n = Math.min(u, 2) * 3
  return [0, 1, 2, 3, 4, 5].map((i) => Math.max(0, Math.min(n - (5 - i), 1)))
}

/* ------------------------------------------------------------ the pick and the frozen copies */

const isPattern = (v: string | null): v is Pattern => (PATTERNS as readonly string[]).includes(v ?? '')
export function usePattern(): [Pattern, (p: Pattern) => void] {
  const [params, setParams] = useSearchParams()
  const v = params.get('pattern')
  const set = (p: Pattern) => setParams((prev) => { const q = new URLSearchParams(prev); q.set('pattern', p); return q }, { replace: true })
  return [isPattern(v) ? v : PATTERN_DEFAULT, set]
}

/** The compare view's tiles draw a pattern of their own on frozen moods; the live window leaves both unset. */
export const MoodFrozen = createContext<{ pattern?: Pattern; mood?: MoodLab }>({})
export const useMoodFrozen = () => useContext(MoodFrozen)
