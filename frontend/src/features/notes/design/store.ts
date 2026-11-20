import { useSyncExternalStore } from 'react'

import type { Marks } from '../render/env'

/**
 * The operator's marks on notes: ticks, answers, copies. The real feature
 * keeps them on the server (one row per item, keyed by the item's text
 * hash so a new version keeps the ticks of unchanged items); this mock
 * keeps them in memory, shared by every variant so a tick made in one
 * shows in the others.
 */

let marks: Marks = { ticks: {}, answers: {}, copied: {} }
const listeners = new Set<() => void>()
const emit = () => { for (const l of listeners) l() }

export function tick(id: string, on: boolean) { marks = { ...marks, ticks: { ...marks.ticks, [id]: on } }; emit() }
export function answer(id: string, option: number | null) {
  const next = { ...marks.answers }
  if (option == null) delete next[id]
  else next[id] = option
  marks = { ...marks, answers: next }
  emit()
}
export function markCopied(id: string, at = new Date().toISOString()) { marks = { ...marks, copied: { ...marks.copied, [id]: at } }; emit() }

/** For tests and the seed: start again from these marks. */
export function resetMarks(seed: Partial<Marks> = {}) { marks = { ticks: {}, answers: {}, copied: {}, ...seed }; emit() }

const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
export function useMarks(): Marks { return useSyncExternalStore(subscribe, () => marks, () => marks) }

// The counts and the checks are the shared ones the Notes page uses.
export { isTicked, needsYou, openOf, type Open } from '../render/env'
