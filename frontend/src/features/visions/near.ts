/**
 * Which rows of a kept page are worth their detail: the ones on screen or
 * about to be, the ones opened, and the ones a page asks for by name (a
 * search over the detail's text, Copy all). A page used to read every
 * row's detail on mount — one request per vision, rule, problem, skill or
 * artifact, most of them for rows nobody scrolled to.
 *
 * `watch(id)` is a ref for the row's element; once it comes within
 * `margin` of the screen the id is near, and it stays near. The margin is
 * measured in the box that scrolls the row (the app's main pane, a list's
 * own scroller): a margin on the window would stop at that box's edge.
 * Without an IntersectionObserver (an old browser, a test without one)
 * every row is.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface Near {
  /** The ids whose detail is read. */
  has: (id: string) => boolean
  /** A ref for the row's element. Stable per id. */
  watch: (id: string) => (el: Element | null) => void
  /** Read these details now, wherever their rows are. */
  want: (ids: readonly string[]) => void
}

const EVERY: Near = { has: () => true, watch: () => () => {}, want: () => {} }

/** The nearest ancestor that scrolls; null for the window. */
function scroller(el: Element): Element | null {
  for (let p = el.parentElement; p; p = p.parentElement) {
    const y = getComputedStyle(p).overflowY
    if (y === 'auto' || y === 'scroll') return p
  }
  return null
}

export function useNear(margin = '800px 0px'): Near {
  const [near, setNear] = useState<ReadonlySet<string>>(() => new Set())
  const supported = typeof IntersectionObserver !== 'undefined'
  const io = useRef(new Map<Element | null, IntersectionObserver>())
  const ids = useRef(new Map<Element, string>())
  const refs = useRef(new Map<string, (el: Element | null) => void>())
  const els = useRef(new Map<string, Element>())

  const add = useCallback((more: readonly string[]) => {
    setNear((cur) => {
      const fresh = more.filter((id) => !cur.has(id))
      if (!fresh.length) return cur
      const next = new Set(cur)
      for (const id of fresh) next.add(id)
      return next
    })
  }, [])

  const observer = useCallback((root: Element | null) => {
    let o = io.current.get(root)
    if (!o) {
      const made: IntersectionObserver = new IntersectionObserver((entries) => {
        const seen: string[] = []
        for (const e of entries) {
          if (!e.isIntersecting) continue
          const id = ids.current.get(e.target)
          if (id) seen.push(id)
          // Near once is near for good: the element needs no more watching.
          made.unobserve(e.target)
        }
        if (seen.length) add(seen)
      }, { root, rootMargin: margin })
      io.current.set(root, made)
      o = made
    }
    return o
  }, [add, margin])

  useEffect(() => {
    const all = io.current
    return () => { for (const o of all.values()) o.disconnect(); all.clear() }
  }, [])

  const watch = useCallback((id: string) => {
    let ref = refs.current.get(id)
    if (!ref) {
      ref = (el: Element | null) => {
        const was = els.current.get(id)
        if (was && was !== el) {
          for (const o of io.current.values()) o.unobserve(was)
          ids.current.delete(was)
          els.current.delete(id)
        }
        if (!el) return
        els.current.set(id, el)
        ids.current.set(el, id)
        observer(scroller(el)).observe(el)
      }
      refs.current.set(id, ref)
    }
    return ref
  }, [observer])

  const has = useCallback((id: string) => near.has(id), [near])
  return supported ? { has, watch, want: add } : EVERY
}
