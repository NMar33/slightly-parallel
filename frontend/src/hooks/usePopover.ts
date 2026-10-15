import { useEffect, useRef, useState } from 'react'

/**
 * A small popover's open state: a click outside its root closes it, and so
 * does Escape — unless the panel owns Escape itself (a dialog hook mounted
 * with it), then pass `{ escape: false }`. Put `rootRef` on the element
 * that holds both the trigger and the panel.
 */
export function usePopover<T extends HTMLElement = HTMLSpanElement>({ escape = true }: { escape?: boolean } = {}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<T>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    if (escape) window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      if (escape) window.removeEventListener('keydown', onKey)
    }
  }, [open, escape])
  return { open, setOpen, rootRef }
}
