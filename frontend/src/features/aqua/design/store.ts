import { useSyncExternalStore } from 'react'

import { MESSAGES, SERVERS, SESSIONS, sessionOf, type Mark } from './mock'

/**
 * The mock app's state, shared by every variant so a pin, a sleep or a
 * detached window made in one shows in the others until the page reloads.
 * The real app would hold this on the SP server (sessions in tmux, marks
 * on captured messages); here it lives in memory.
 */

export type ResumeStep = 'wait' | 'run' | 'ok' | 'fail'

export interface AquaState {
  active: string
  asleep: Record<string, boolean>
  up: Record<string, boolean>
  pinned: Record<string, boolean>
  important: Record<string, boolean>
  marks: Record<string, Mark>
  tasked: Record<string, string>
  forkLater: Record<string, boolean>
  detached: string[]
  /** After a (simulated) reboot: each session's step in the one-button restore. */
  restore: Record<string, ResumeStep> | null
  rebooted: boolean
  flash: { text: string; n: number } | null
}

function seed(): AquaState {
  return {
    active: 'cc-4e7a19d2',
    asleep: Object.fromEntries(SESSIONS.map((s) => [s.id, !!s.asleep])),
    up: Object.fromEntries(SERVERS.map((s) => [s.id, s.up])),
    pinned: Object.fromEntries(MESSAGES.map((m) => [m.id, !!m.pinned])),
    important: Object.fromEntries(MESSAGES.map((m) => [m.id, !!m.important])),
    marks: Object.fromEntries(MESSAGES.map((m) => [m.id, m.mark])),
    tasked: Object.fromEntries(MESSAGES.filter((m) => m.task).map((m) => [m.id, m.task!])),
    forkLater: { m24: true },
    detached: [],
    restore: null,
    rebooted: false,
    flash: null,
  }
}

let state = seed()
const listeners = new Set<() => void>()
const set = (patch: Partial<AquaState>) => { state = { ...state, ...patch }; for (const l of listeners) l() }
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }

export function useAqua(): AquaState { return useSyncExternalStore(subscribe, () => state, () => state) }
export const getAqua = () => state
export function resetAqua() { state = seed(); for (const l of listeners) l() }

let flashN = 0
export function flash(text: string) { set({ flash: { text, n: ++flashN } }) }

export function focus(id: string) { set({ active: id }) }

export function sleep(id: string) { set({ asleep: { ...state.asleep, [id]: true } }) }
export function wake(id: string) {
  const s = sessionOf(id)
  if (s?.gone) { flash(`${s.name}: session ${s.sessionRef} is gone — start fresh with the briefing`); return }
  set({ asleep: { ...state.asleep, [id]: false } })
}
export function toggleSleep(id: string) { if (state.asleep[id]) wake(id); else sleep(id) }

/** A project sleeps with its agent chats and its servers; it wakes the same way. */
export function setProjectAsleep(code: string, asleep: boolean) {
  const next = { ...state.asleep }
  for (const s of SESSIONS) if (s.project === code && !s.gone) next[s.id] = asleep
  const up = { ...state.up }
  for (const s of SERVERS) if (s.project === code) up[s.id] = asleep ? false : (s.up || up[s.id]!)
  set({ asleep: next, up })
}
export const projectAsleep = (st: AquaState, code: string) => SESSIONS.filter((s) => s.project === code).every((s) => st.asleep[s.id])

export function toggleServer(id: string) { set({ up: { ...state.up, [id]: !state.up[id] } }) }

export function togglePin(id: string) { set({ pinned: { ...state.pinned, [id]: !state.pinned[id] } }) }
export function toggleImportant(id: string) { set({ important: { ...state.important, [id]: !state.important[id] } }) }
export function toggleForkLater(id: string) { set({ forkLater: { ...state.forkLater, [id]: !state.forkLater[id] } }) }
/** Cycle the memory mark by hand: none → summary (yellow) → verbatim (red) → none. */
export function cycleMark(id: string) {
  const now = state.marks[id] ?? null
  const next: Mark = now === null ? 'yellow' : now === 'yellow' ? 'red' : null
  set({ marks: { ...state.marks, [id]: next } })
}
export function toTask(id: string) {
  if (state.tasked[id]) return state.tasked[id]!
  const tk = `tk_${(0x3a1c0000 + id.length * 7919 + id.charCodeAt(id.length - 1) * 131).toString(16).slice(-8)}`
  set({ tasked: { ...state.tasked, [id]: tk } })
  flash(`${tk} written to the board (todo)`)
  return tk
}

export function detach(key: string) { if (!state.detached.includes(key)) set({ detached: [...state.detached, key] }) }
export function dock(key: string) { set({ detached: state.detached.filter((k) => k !== key) }) }

/** Simulate the machine coming back from a reboot: every process gone, nothing lost. */
export function reboot() {
  set({
    rebooted: true,
    restore: null,
    asleep: Object.fromEntries(SESSIONS.map((s) => [s.id, true])),
    up: Object.fromEntries(SERVERS.map((s) => [s.id, false])),
  })
}

/** One button: servers first, then every chat that was awake, one by one; a gone session fails and waits. */
export function restoreAll(onDone?: () => void) {
  const before = seed()
  const order = SESSIONS.filter((s) => !before.asleep[s.id] || s.gone)
  const steps: Record<string, ResumeStep> = Object.fromEntries(order.map((s) => [s.id, 'wait' as ResumeStep]))
  set({ restore: steps, up: before.up })
  order.forEach((s, i) => {
    setTimeout(() => set({ restore: { ...state.restore!, [s.id]: 'run' } }), 120 + i * 260)
    setTimeout(() => {
      const ok = !s.gone
      set({ restore: { ...state.restore!, [s.id]: ok ? 'ok' : 'fail' }, asleep: { ...state.asleep, [s.id]: !ok } })
      if (i === order.length - 1) { set({ rebooted: false }); onDone?.() }
    }, 320 + i * 260)
  })
}
export function closeRestore() { set({ restore: null }) }

/** Round 2: put several chats to sleep or wake them at once, and set the servers that follow. */
export function setChatsAsleep(ids: string[], asleep: boolean, servers: Record<string, boolean> = {}) {
  const next = { ...state.asleep }
  for (const id of ids) if (!sessionOf(id)?.gone || asleep) next[id] = asleep
  set({ asleep: next, up: { ...state.up, ...servers } })
}
