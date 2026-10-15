import { useSyncExternalStore } from 'react'

import { persistPref, readPref } from '../../lib/uiPrefs'
import { parseLayout, serialize, type Layout } from './layout'

/**
 * One layout for the whole tab. The sidebar and the settings page read the
 * same value, so an arrangement shows in the sidebar as it is made. The
 * pref store carries it across reloads and origins; another tab's change
 * arrives through the storage event.
 */
const LAYOUT_PREF = 'sp-sidebar-layout'
const UNDO_DEPTH = 60

let current: Layout | null = null
let past: Layout[] = []
const listeners = new Set<() => void>()

function read(): Layout {
  try { return parseLayout(readPref(LAYOUT_PREF)) } catch { return parseLayout(null) }
}

export function getLayout(): Layout {
  if (!current) current = read()
  return current
}

function emit(): void {
  for (const fn of listeners) fn()
}

export function setLayout(next: Layout, opts: { history?: boolean } = {}): void {
  const prev = getLayout()
  if (serialize(prev) === serialize(next)) return
  if (opts.history !== false) past = [...past.slice(-(UNDO_DEPTH - 1)), prev]
  current = next
  persistPref(LAYOUT_PREF, serialize(next))
  emit()
}

export function update(fn: (l: Layout) => Layout, opts?: { history?: boolean }): void {
  setLayout(fn(getLayout()), opts)
}

export function undo(): boolean {
  const prev = past.pop()
  if (!prev) return false
  current = prev
  persistPref(LAYOUT_PREF, serialize(prev))
  emit()
  return true
}

export function undoDepth(): number {
  return past.length
}

/** Forget the past — used by tests and by "reset". */
export function clearHistory(): void {
  past = []
  emit()
}

/** Drop the cached value so the next read comes from storage. */
function reload(): void {
  current = null
  emit()
}

/** One handler for the module: the last unsubscribe removes the same function the first one added. */
function onStorage(e: StorageEvent): void {
  if (e.key === LAYOUT_PREF) reload()
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  if (listeners.size === 1 && typeof window !== 'undefined') window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(fn)
    if (listeners.size === 0 && typeof window !== 'undefined') window.removeEventListener('storage', onStorage)
  }
}

export function useSidebarLayout(): Layout {
  return useSyncExternalStore(subscribe, getLayout, getLayout)
}

export function useUndoDepth(): number {
  return useSyncExternalStore(subscribe, undoDepth, undoDepth)
}
