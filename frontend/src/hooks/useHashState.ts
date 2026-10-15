import { useCallback, useEffect, useState } from 'react'

type HashState = Record<string, string>

/** A hand-typed or truncated link (`#q=100%`) must not throw: keep the text as typed. */
function decodeSafe(s: string): string {
  try { return decodeURIComponent(s) } catch { return s }
}

function parseHash(): HashState {
  if (typeof window === 'undefined') return {}
  const raw = window.location.hash.replace(/^#/, '')
  if (!raw) return {}
  const out: HashState = {}
  for (const pair of raw.split('&')) {
    if (!pair) continue
    const eq = pair.indexOf('=')
    if (eq === -1) continue
    const k = decodeSafe(pair.slice(0, eq))
    const v = decodeSafe(pair.slice(eq + 1))
    if (k) out[k] = v
  }
  return out
}

/** Bare tokens — a project tab's `#calendar` in front of its `&view=week`
 *  — are not state; they are kept where they were. */
function bareTokens(): string[] {
  if (typeof window === 'undefined') return []
  return window.location.hash.replace(/^#/, '').split('&').filter((p) => p && !p.includes('='))
}

function serializeHash(state: HashState, bare: string[] = []): string {
  const parts = [
    ...bare,
    ...Object.entries(state)
      .filter(([, v]) => v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`),
  ]
  return parts.length ? `#${parts.join('&')}` : ''
}

/**
 * Filter/selection state serialized into `location.hash` as `#k=v&k2=v2`,
 * making every filtered lens view shareable and bookmarkable.
 *
 * Uses replaceState — filter tweaks don't spam browser history — and listens
 * to `hashchange` so externally-navigated hashes (links, back button) apply.
 */
/** replaceState fires no hashchange, so instances tell each other. */
const HASH_EVENT = 'sp:hash'

export function useHashState(): [HashState, (patch: HashState) => void] {
  const [state, setState] = useState<HashState>(parseHash)

  useEffect(() => {
    const onHash = () => setState(parseHash())
    window.addEventListener('hashchange', onHash)
    window.addEventListener(HASH_EVENT, onHash)
    return () => {
      window.removeEventListener('hashchange', onHash)
      window.removeEventListener(HASH_EVENT, onHash)
    }
  }, [])

  const update = useCallback((patch: HashState) => {
    // Merge onto the URL, not onto this instance's copy: several hooks on
    // one page (the tab's view, the page's filters) share the one hash.
    const next = { ...parseHash(), ...patch }
    for (const k of Object.keys(next)) {
      if (next[k] === '') delete next[k]
    }
    const url = new URL(window.location.href)
    url.hash = serializeHash(next, bareTokens())
    window.history.replaceState(window.history.state, '', url.toString())
    setState(next)
    window.dispatchEvent(new Event(HASH_EVENT))
  }, [])

  return [state, update]
}
