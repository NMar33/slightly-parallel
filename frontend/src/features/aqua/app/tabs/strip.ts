/**
 * The status strip over each tab (variant c «dots», tk_a9306fb1): its
 * settings and what each part shows. From the lab's `live.ts` and `Tabs.tsx`.
 *
 * Parts: closed tasks (green), context used (grey, amber past 70%, red past
 * 85% — the chat compacts soon; empty when not known), waiting for your
 * answer (green to red over 30 minutes). The mockup also offered agent
 * activity and time since the last commit: Slightly Parallel has no cheap
 * per-chat reading of those, so they are left out.
 *
 * Settings live in the operator's preferences (`sp-term-strip`, shared by
 * the window and Settings › Terminal through the server's ui_prefs).
 */

import { useSyncExternalStore } from 'react'

import { persistPref } from '../../../../lib/uiPrefs'
import type { Facts } from './facts'
import { TAB_STATE_KEY, tabStateChanged } from './rhythm'

export type PartKind = 'closed' | 'context' | 'waiting'
export const PART_KINDS: PartKind[] = ['closed', 'context', 'waiting']
export interface StripSettings { on: boolean; parts: 1 | 2 | 3; kinds: [PartKind, PartKind, PartKind]; px: 1 | 2 | 3 | 4 }
export const STRIP_DEFAULT: StripSettings = { on: true, parts: 3, kinds: ['closed', 'context', 'waiting'], px: 2 }
export const STRIP_KEY = 'sp-term-strip'

export function parseStrip(raw: string | null): StripSettings {
  try {
    const v = JSON.parse(raw ?? 'null') as Partial<StripSettings> | null
    if (v && [1, 2, 3].includes(v.parts as number) && [1, 2, 3, 4].includes(v.px as number)
      && Array.isArray(v.kinds) && v.kinds.length === 3 && v.kinds.every((k) => PART_KINDS.includes(k))) {
      return { on: v.on !== false, parts: v.parts!, px: v.px!, kinds: v.kinds as StripSettings['kinds'] }
    }
  } catch { /* a broken value: the defaults */ }
  return STRIP_DEFAULT
}

let strip: StripSettings = STRIP_DEFAULT
let stripRaw: string | null | undefined
const listeners = new Set<() => void>()
/** The cache follows localStorage: the server's copy, hydrated at boot or re-read, wins. */
const read = (): StripSettings => {
  let raw: string | null = null
  try { raw = localStorage.getItem(STRIP_KEY) } catch { /* private mode */ }
  if (raw !== stripRaw) { stripRaw = raw; strip = parseStrip(raw) }
  return strip
}
export const useStripSettings = () => useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l) } }, read, read)
export function setStrip(patch: Partial<StripSettings>) {
  strip = { ...read(), ...patch }
  stripRaw = JSON.stringify(strip)
  persistPref(STRIP_KEY, stripRaw)
  for (const l of listeners) l()
}
/** Tell the strip's readers that localStorage may hold a new value (the server's copy was read again). */
export function stripChanged() { for (const l of listeners) l() }

/** Which slots show: with two parts the first and the last, with one the last. */
export const shownSlots = (s: StripSettings): number[] => (s.parts === 3 ? [0, 1, 2] : s.parts === 2 ? [0, 2] : [2])

const mix = (p: number, from: string, to: string) => `color-mix(in oklch, ${to} ${Math.round(p * 100)}%, ${from})`

/** A part's fill, 0–1, and its colour. */
export function partValue(kind: PartKind, f: Facts): { v: number; color: string } {
  switch (kind) {
    case 'closed': return { v: f.all ? f.done / f.all : 0, color: 'var(--aq-up)' }
    case 'context': {
      if (f.ctx === null) return { v: 0, color: 'var(--aq-ink3)' }
      return { v: f.ctx / 100, color: f.ctx > 85 ? 'var(--aq-down)' : f.ctx > 70 ? 'var(--aq-wait)' : 'var(--aq-ink3)' }
    }
    case 'waiting': {
      if (!f.waiting) return { v: 0, color: 'var(--aq-up)' }
      const p = Math.min(f.waited / 30, 1)
      return { v: Math.max(p, 0.04), color: p < 0.5 ? mix(p * 2, 'var(--aq-up)', 'var(--aq-wait)') : mix((p - 0.5) * 2, 'var(--aq-wait)', 'var(--aq-down)') }
    }
  }
}

/** How many of five dots a part fills. */
export const dotsOf = (v: number) => [0, 1, 2, 3, 4].filter((k) => v * 5 > k + 0.25).length

/** Settings › Terminal is another page (and in the app's window, another browser profile): when this
 *  window comes to the front, the server's copy of the strip's settings is read again. */
export async function refreshStripFromServer(get: (url: string) => Promise<{ prefs?: Record<string, string> }>) {
  try {
    const d = await get('/api/prefs')
    // The strip's settings and the tab state (tk_d2e11125), each told to its readers when it changed.
    for (const [key, changed] of [[STRIP_KEY, stripChanged], [TAB_STATE_KEY, tabStateChanged]] as const) {
      const v = d?.prefs?.[key]
      if (typeof v !== 'string') continue
      let cur: string | null = null
      try { cur = localStorage.getItem(key) } catch { /* private mode */ }
      if (cur === v) continue
      try { localStorage.setItem(key, v) } catch { /* private mode */ }
      changed()
    }
  } catch { /* offline: the local copy stands */ }
}
