import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react'

/** Place a point in the reader as a fraction of its full scroll height. */
export function readingMapOffset(top: number, rootTop: number, root: HTMLElement, total: number): number {
  return (top - rootTop + root.scrollTop) / total
}

export function readingMapViewport(root: HTMLElement, total = Math.max(1, root.scrollHeight)) {
  return { top: root.scrollTop / total, height: root.clientHeight / total, total }
}

export function centerReadingMapAt(root: HTMLElement, bounds: DOMRect, clientY: number) {
  const fraction = (clientY - bounds.top) / bounds.height
  root.scrollTop = fraction * root.scrollHeight - root.clientHeight / 2
}

export function dragReadingMap(event: ReactPointerEvent, scrollTo: (clientY: number) => void) {
  event.preventDefault()
  scrollTo(event.clientY)
  const move = (ev: PointerEvent) => scrollTo(ev.clientY)
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

export function navigateReadingMap(event: KeyboardEvent, count: number, current: () => number,
  preview: (index: number) => void, open: (index: number) => void,
) {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp' && event.key !== 'Enter' && event.key !== ' ') return
  if (!count) return
  event.preventDefault()
  const at = current()
  if (event.key === 'ArrowDown') preview(Math.min(count - 1, at + 1))
  else if (event.key === 'ArrowUp') preview(Math.max(0, at - 1))
  else open(Math.max(0, at))
}
