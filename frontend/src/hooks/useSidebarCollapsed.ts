import { useCallback, useEffect, useState } from 'react'

import { persistPref, readPref } from '../lib/uiPrefs'
import { isTypingTarget } from '../lib/typing'

/** The pref key; syncs through ui_prefs like every other `sp-*` key. */
export const SIDEBAR_PREF = 'sp-sidebar-collapsed'
/** The key that flips the sidebar when no field has focus. */
export const SIDEBAR_KEY = '['

function readSidebarCollapsed(): boolean {
  try { return readPref(SIDEBAR_PREF) === '1' } catch { return false }
}

/**
 * useSidebarCollapsed — the sidebar's one bit of state.
 *
 * Collapsed is a preference, not a per-visit whim: it survives reloads and
 * follows the operator across origins through ui_prefs. `[` toggles it from
 * anywhere on the page except inside a field, and the modifier keys are
 * left alone so browser shortcuts keep working.
 */
export function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState<boolean>(readSidebarCollapsed)
  const toggle = useCallback(() => {
    setCollapsed((c) => {
      persistPref(SIDEBAR_PREF, c ? '0' : '1')
      return !c
    })
  }, [])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== SIDEBAR_KEY || e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return
      if (isTypingTarget(e)) return
      e.preventDefault()
      toggle()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])
  return [collapsed, toggle]
}
