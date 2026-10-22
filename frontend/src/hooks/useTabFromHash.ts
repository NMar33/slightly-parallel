import { useCallback, useEffect, useState } from 'react'

/**
 * Tab state mirrored into `location.hash` (`#agents`, `#tasks`, …) so tab
 * position survives reloads and is shareable. Uses replaceState so switching
 * tabs does not spam browser history.
 */
export function useTabFromHash<Id extends string>(
  isValid: (raw: string) => raw is Id,
  defaultTab: Id,
): [Id, (id: Id) => void] {
  const readHash = useCallback((): Id => {
    if (typeof window === 'undefined') return defaultTab
    // A tab may carry state after it — `#agents&agent=cc-x&sec=chats` —
    // the part before the first `&` is the tab.
    const raw = window.location.hash.replace(/^#/, '').split('&')[0] ?? ''
    return isValid(raw) ? raw : defaultTab
  }, [isValid, defaultTab])

  const [tab, setTab] = useState<Id>(readHash)

  // Re-derive on hash changes AND when the default changes (the operator's
  // configured default tab loads asynchronously from settings).
  useEffect(() => {
    setTab(readHash())
    const onHash = () => setTab(readHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [readHash])

  const select = useCallback((id: Id) => {
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.hash = id
      window.history.replaceState(window.history.state, '', url.toString())
    }
    setTab(id)
  }, [])

  return [tab, select]
}
