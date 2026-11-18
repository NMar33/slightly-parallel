/**
 * Round 4: which feature K's compare view shows, kept in the address
 * (`&compare=tabs|strip|plus|msgmenu|scheme|health`), so a link opens it.
 */

import { useSearchParams } from 'react-router-dom'

export const FEATURES = ['tabs', 'strip', 'plus', 'msgmenu', 'scheme', 'health'] as const
export type Feature = (typeof FEATURES)[number]
export const isFeature = (v: string | null): v is Feature => (FEATURES as readonly string[]).includes(v ?? '')

/** The feature in the compare view, or null; `open(f)` shows it, `open(null)` closes the view. */
export function useCompare(): [Feature | null, (f: Feature | null, also?: Record<string, string>) => void] {
  const [params, setParams] = useSearchParams()
  const f = params.get('compare')
  const open = (next: Feature | null, also: Record<string, string> = {}) => setParams((prev) => {
    const p = new URLSearchParams(prev)
    if (next) p.set('compare', next)
    else p.delete('compare')
    for (const [k, v] of Object.entries(also)) p.set(k, v)
    return p
  }, { replace: true })
  return [isFeature(f) ? f : null, open]
}
