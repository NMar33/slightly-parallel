import { useLayoutEffect, useRef, useState } from 'react'

export function useElementWidth<T extends HTMLElement>(initialWidth: number) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(initialWidth)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    const observer = new ResizeObserver(() => setWidth(element.clientWidth))
    observer.observe(element)
    setWidth(element.clientWidth)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}
