/**
 * The clocks a page with a running timer needs, kept apart so a second
 * hand does not redraw the page around it.
 *
 * - `Live` draws one readout and redraws only itself, once a second. Every
 *   `Live` on screen shares one interval, so they turn over together.
 * - `useNow` is the page's own, slower clock: the totals a page shows are
 *   in minutes, and counting five thousand entries again every second to
 *   move a number once a minute was most of what those pages did.
 */

import { useEffect, useState, useSyncExternalStore, type ReactNode } from 'react'

const listeners = new Set<() => void>()
let nowMs = Date.now()
let timer: ReturnType<typeof setInterval> | null = null

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  if (!timer) {
    nowMs = Date.now()
    timer = setInterval(() => {
      nowMs = Date.now()
      listeners.forEach((l) => l())
    }, 1000)
  }
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0 && timer) {
      clearInterval(timer)
      timer = null
    }
  }
}
const still = () => () => {}
const read = () => nowMs

/** The time now, turning over every second while `on`. */
function useSecond(on = true): number {
  // Nobody was listening: the stored time is as old as the last listener.
  if (on && !timer) nowMs = Date.now()
  return useSyncExternalStore(on ? subscribe : still, read, read)
}

/** One readout that follows the second hand; nothing around it redraws. */
export function Live({ on = true, children }: { on?: boolean; children: (nowMs: number) => ReactNode }) {
  return <>{children(useSecond(on))}</>
}

/** The time now, read again every `everyMs` — a page's clock for its minute-sized numbers. */
export function useNow(everyMs: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    setNow(Date.now())
    const id = window.setInterval(() => setNow(Date.now()), everyMs)
    return () => window.clearInterval(id)
  }, [everyMs])
  return now
}

/** Local midnight of the day `nowMs` falls in, as epoch ms. */
export function dayStartOf(nowMs: number): number {
  const d = new Date(nowMs)
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/**
 * The start of today, read again every minute: it changes once, at
 * midnight, so a page left open overnight rolls to the new day while
 * whatever is keyed on it stays put the rest of the day. The minute's read
 * stores the midnight, not the time, so React leaves the caller alone until
 * the day turns.
 */
export function useDayStart(): number {
  const [start, setStart] = useState(() => dayStartOf(Date.now()))
  useEffect(() => {
    setStart(dayStartOf(Date.now()))
    const id = window.setInterval(() => setStart(dayStartOf(Date.now())), 60_000)
    return () => window.clearInterval(id)
  }, [])
  return start
}
