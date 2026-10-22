/**
 * One keydown listener per page — the calendar and milestone pages all
 * walk with the keyboard (arrows, t, j, k) and all skip the same things:
 * a modifier chord, an open window, and typing in a field. Escape inside
 * a field leaves the field; the page's own Escape comes on the next press.
 */
import { useEffect, useRef } from 'react'

import { isTypingTarget } from '../../lib/typing'

/** A window (the task window, an entry, a milestone, the month picker) owns its keys. */
function dialogOpen(): boolean {
  return typeof document !== 'undefined' && !!document.querySelector('[role="dialog"]')
}

/** The handler is read at the key press, so it always sees the page as drawn. */
export function usePageKeys(onKey: (e: KeyboardEvent) => void): void {
  const latest = useRef(onKey)
  useEffect(() => { latest.current = onKey })
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (dialogOpen()) return
      if (isTypingTarget(e)) {
        if (e.key === 'Escape') (e.target as HTMLElement).blur()
        return
      }
      latest.current(e)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])
}
