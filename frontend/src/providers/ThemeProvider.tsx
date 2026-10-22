import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { persistPref, readPref, removePref } from '../lib/uiPrefs'

/**
 * ThemeProvider — light-default with prefers-color-scheme fallback and
 * localStorage override.
 *
 * Architecture §6: light is DEFAULT (aesthetic critic §2). Dark activates on
 * `:root[data-theme="dark"]` (explicit toggle) OR `@media (prefers-color-scheme: dark)`
 * when no explicit override set.
 *
 * The initial theme is pre-applied by an inline script in index.html to avoid
 * a paint flash. This provider takes over state management once React mounts.
 */

type Theme = 'light' | 'dark'
export type ThemeMode = Theme | 'system'

interface ThemeCtx {
  /** Current resolved theme (never 'system'). */
  theme: Theme
  /** User's preference — 'system' means "follow OS". */
  mode: ThemeMode
  /** Set explicit preference; persists to localStorage. */
  setMode: (mode: ThemeMode) => void
  /** Toggle between light and dark; forces off 'system' mode. */
  toggle: () => void
}

const STORAGE_KEY = 'sp-theme'
// Pre-rename key, migrated on first read.
const LEGACY_STORAGE_KEY = 'pdr.theme'
const ThemeContext = createContext<ThemeCtx | null>(null)

function readSystemTheme(): Theme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function readStoredMode(): ThemeMode {
  if (typeof window === 'undefined') return 'system'
  try {
    const raw =
      readPref(STORAGE_KEY) ?? localStorage.getItem(LEGACY_STORAGE_KEY)
    if (raw === 'light' || raw === 'dark') return raw
    return 'system'
  } catch {
    return 'system'
  }
}

function applyThemeAttr(theme: Theme) {
  if (typeof document === 'undefined') return
  document.documentElement.setAttribute('data-theme', theme)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => readStoredMode())
  const [systemTheme, setSystemTheme] = useState<Theme>(() => readSystemTheme())

  // Track OS scheme changes so 'system' users stay in sync.
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e: MediaQueryListEvent) => setSystemTheme(e.matches ? 'dark' : 'light')
    // Safari <14 uses addListener; modern browsers use addEventListener.
    if (mq.addEventListener) mq.addEventListener('change', onChange)
    else mq.addListener(onChange)
    return () => {
      if (mq.removeEventListener) mq.removeEventListener('change', onChange)
      else mq.removeListener(onChange)
    }
  }, [])

  const theme: Theme = mode === 'system' ? systemTheme : mode

  useEffect(() => {
    applyThemeAttr(theme)
  }, [theme])

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next)
    // Back to the system: the server's copy goes too, or the next start
    // would read the old choice back from it.
    if (next === 'system') removePref(STORAGE_KEY)
    else persistPref(STORAGE_KEY, next)
  }, [])

  const toggle = useCallback(() => {
    setMode(theme === 'dark' ? 'light' : 'dark')
  }, [theme, setMode])

  const value = useMemo<ThemeCtx>(() => ({ theme, mode, setMode, toggle }), [theme, mode, setMode, toggle])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within <ThemeProvider>')
  return ctx
}
