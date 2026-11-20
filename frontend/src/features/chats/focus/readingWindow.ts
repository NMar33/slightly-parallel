import { useCallback, useEffect, useRef, type Dispatch, type RefObject, type SetStateAction } from 'react'

const READING_PAGE_ITEMS = 3
const READING_EDGE_MARGIN = '1200px 0px'

export function useReadingWindow({ scroller, range, setRange, count, active, shown }: {
  scroller: RefObject<HTMLDivElement>
  range: [number, number]
  setRange: Dispatch<SetStateAction<[number, number]>>
  count: number
  active: boolean
  shown: number
}) {
  const anchor = useRef<{ height: number; top: number } | null>(null)
  const topEdge = useRef<HTMLDivElement>(null)
  const bottomEdge = useRef<HTMLDivElement>(null)
  const more = useCallback((side: 'up' | 'down') => {
    const root = scroller.current
    if (side === 'up') {
      if (range[0] <= 0) return
      if (root) anchor.current = { height: root.scrollHeight, top: root.scrollTop }
      setRange(([a, b]) => [Math.max(0, a - READING_PAGE_ITEMS), b])
    } else if (range[1] < count) {
      setRange(([a, b]) => [a, Math.min(count, b + READING_PAGE_ITEMS)])
    }
  }, [range, count, scroller, setRange])
  useEffect(() => {
    const root = scroller.current
    if (!root || !active) return
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) more(entry.target === topEdge.current ? 'up' : 'down')
      }
    }, { root, rootMargin: READING_EDGE_MARGIN })
    if (topEdge.current) observer.observe(topEdge.current)
    if (bottomEdge.current) observer.observe(bottomEdge.current)
    return () => observer.disconnect()
  }, [active, more, scroller, shown])

  const restoreAnchor = useCallback((root: HTMLDivElement | null) => {
    if (!root || !anchor.current) return
    root.scrollTop = anchor.current.top + (root.scrollHeight - anchor.current.height)
    anchor.current = null
  }, [])

  return { topEdge, bottomEdge, restoreAnchor }
}
