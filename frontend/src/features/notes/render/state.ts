/**
 * The Notes page's state (design round 3): which side columns are folded, whether the
 * notes are grouped by task, and the view (reading or the tiles). All of it
 * sits in the address so a view can be linked and reloaded:
 *
 *   &hide=list | rail | list,rail   the folded side columns
 *   &by=task                         grouped by task
 *   &view=tiles | read               the view, when it is not the variant's first one
 *   &note=nt_…&at=<section>          the note read last (the one the tiles ring, the one reading returns to)
 *
 * The folded columns and the grouping are also kept in this browser, the
 * way the Entry points page keeps its layout: the address wins when it says.
 */

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { useSearchParams } from 'react-router-dom'

export type Side = 'list' | 'rail'
export type View = 'read' | 'tiles'

export const HIDE_KEY = 'notes-r3-hide'
export const BY_KEY = 'notes-r3-by'

export function read(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
export function keep(key: string, v: string) {
  try { localStorage.setItem(key, v) } catch { /* private mode */ }
}

const sidesOf = (s: string | null) => new Set((s ?? '').split(',').filter((c): c is Side => c === 'list' || c === 'rail'))

/** The folded side columns and the grouping, from the address or this browser. */
export function usePageState() {
  const [params, setParams] = useSearchParams()
  const hidden = sidesOf(params.has('hide') ? params.get('hide') : read(HIDE_KEY))
  const byTask = params.has('by') ? params.get('by') === 'task' : read(BY_KEY) === 'task'
  const hkey = [...hidden].sort().join(',')
  const toggle = useCallback((side: Side) => {
    const next = sidesOf(hkey)
    if (next.has(side)) next.delete(side)
    else next.add(side)
    const v = [...next].sort().join(',')
    keep(HIDE_KEY, v)
    setParams((p) => {
      const q = new URLSearchParams(p)
      if (v) q.set('hide', v)
      else q.delete('hide')
      return q
    }, { replace: true })
  }, [hkey, setParams])
  const group = useCallback((on: boolean) => {
    keep(BY_KEY, on ? 'task' : '')
    setParams((p) => {
      const q = new URLSearchParams(p)
      if (on) q.set('by', 'task')
      else q.delete('by')
      return q
    }, { replace: true })
  }, [setParams])
  return { list: !hidden.has('list'), rail: !hidden.has('rail'), toggle, byTask, group }
}

/**
 * The view, kept in the page's own state (so a move can be drawn in one
 * synchronous step, as the zoom's animation needs) and written to the
 * address; a Back or a link that changes the address brings it back.
 * `push` makes the move a step the browser's Back undoes; `explicit`
 * writes the view even when it is the first one (a link with a note would
 * otherwise open in reading).
 */
export function useView(first: View, explicit = false) {
  const [params, setParams] = useSearchParams()
  const fromUrl = params.get('view')
  const urlView: View = fromUrl === 'read' || fromUrl === 'tiles' ? fromUrl : first
  const [view, setLocal] = useState<View>(urlView)
  useEffect(() => { setLocal(urlView) }, [urlView])
  const setView = useCallback((v: View, extra: Record<string, string | null> = {}, push = false) => {
    setLocal(v)
    setParams((p) => {
      const q = new URLSearchParams(p)
      if (v === first && !explicit) q.delete('view')
      else q.set('view', v)
      for (const [k, x] of Object.entries(extra)) { if (x) q.set(k, x); else q.delete(k) }
      return q
    }, { replace: !push })
  }, [explicit, first, setParams])
  return [view, setView] as const
}

/** A media query, live. */
export function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (on) => {
      const m = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query) : null
      m?.addEventListener?.('change', on)
      return () => m?.removeEventListener?.('change', on)
    },
    () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : true),
    () => true,
  )
}

export const reducedMotion = () => {
  try { return !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches } catch { return false }
}

/** The page's scroller: the app's main column (the window in tests). */
export function scroller(): HTMLElement | null {
  return document.getElementById('main') ?? (document.scrollingElement as HTMLElement | null)
}

/** Where the reader is: the note and the section under the reading line, and how far the section's top sits from it. */
export interface Anchor { note: string; at?: string; offset: number }
export const LINE = 0.25

export function anchorOf(note: string | undefined, section: string | undefined): Anchor | null {
  if (!note) return null
  const el = (section && document.getElementById(section)) || document.querySelector<HTMLElement>(`[data-feed-note="${note}"]`)
  const line = window.innerHeight * LINE
  return { note, at: section, offset: el ? el.getBoundingClientRect().top - line : 0 }
}

/** Put the anchor back under the reading line. True when the note was there to scroll to. */
export function restore(a: Anchor): boolean {
  const art = document.querySelector<HTMLElement>(`[data-feed-note="${a.note}"]`)
  if (!art) return false
  const el = (a.at && art.querySelector<HTMLElement>(`[id="${a.at}"]`)) || art
  const s = scroller()
  const line = window.innerHeight * LINE
  const delta = el.getBoundingClientRect().top - line - a.offset
  if (s && typeof s.scrollBy === 'function') s.scrollBy({ top: delta, behavior: 'auto' })
  else el.scrollIntoView?.({ block: 'start' })
  return true
}
