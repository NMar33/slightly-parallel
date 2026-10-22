import { useSyncExternalStore } from 'react'

import { persistPref, readPref } from '../../lib/uiPrefs'
import { t } from '../../i18n/scope/pages'

/**
 * The project page's tabs, and which of them the operator shows
 * (Settings › Project tabs). One list for the page and the settings card.
 *
 * Kept as the operator's choices only, `{id: on}`: a tab with no choice
 * shows as its `on` says, so a tab added later arrives as it was meant to
 * (off, for the ones that only some projects need).
 */
export const PROJECT_TABS = [
  { id: 'overview',  label: t('Overview'),  on: true, fixed: true },
  { id: 'agents',    label: t('Agents'),    on: true },
  { id: 'tasks',     label: t('Tasks'),     on: true },
  { id: 'sprints',   label: t('Sprints'),   on: true },
  { id: 'calendar',  label: t('Calendar'),  on: true },
  { id: 'terminals', label: t('Terminals'), on: true },
  { id: 'decisions', label: t('Decisions'), on: true },
  { id: 'standups',  label: t('Standups'),  on: false },
  { id: 'scans',     label: t('Scans'),     on: false },
  { id: 'activity',  label: t('Chats'),     on: true },
  { id: 'files',     label: t('Files'),     on: true },
  { id: 'architecture', label: t('Architecture'), on: true },
  // The project's kept messages, the same books as their pages, this project only.
  { id: 'visions',   label: t('Visions'),   on: false },
  { id: 'entrypoints', label: t('Entry points'), on: false },
  { id: 'problems',  label: t('Problems'),  on: false },
  { id: 'rules',     label: t('Rules'),     on: false },
  // The id is what links and the saved default tab hold, so it stays.
  { id: 'tools',     label: t('Timer'),     on: true },
] as const satisfies readonly { id: string; label: string; on: boolean; fixed?: boolean }[]

export type ProjectTabId = typeof PROJECT_TABS[number]['id']

export function isProjectTabId(x: string): x is ProjectTabId {
  return PROJECT_TABS.some((tab) => tab.id === x)
}

const PREF = 'sp-project-tabs'
const listeners = new Set<() => void>()
let cached: { raw: string | null; choices: Record<string, boolean> } | null = null

function choices(): Record<string, boolean> {
  const raw = readPref(PREF)
  if (cached && cached.raw === raw) return cached.choices
  let parsed: Record<string, boolean> = {}
  try {
    const got: unknown = raw ? JSON.parse(raw) : {}
    if (got && typeof got === 'object' && !Array.isArray(got)) {
      parsed = Object.fromEntries(Object.entries(got).filter(([, v]) => typeof v === 'boolean')) as Record<string, boolean>
    }
  } catch { /* a value we cannot read is no choice */ }
  cached = { raw, choices: parsed }
  return parsed
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  const onStorage = (e: StorageEvent) => { if (e.key === PREF) fn() }
  window.addEventListener('storage', onStorage)
  return () => { listeners.delete(fn); window.removeEventListener('storage', onStorage) }
}

/** Shown or not, by the operator's choice, else by the tab's own default. */
export function tabShown(id: string, from: Record<string, boolean> = choices()): boolean {
  const tab = PROJECT_TABS.find((x) => x.id === id)
  if (!tab) return false
  if ('fixed' in tab && tab.fixed) return true
  return from[id] ?? tab.on
}

export function setTabShown(id: ProjectTabId, on: boolean): void {
  persistPref(PREF, JSON.stringify({ ...choices(), [id]: on }))
  for (const fn of listeners) fn()
}

/** The operator's choices, live: this tab's changes and another tab's. */
export function useTabChoices(): Record<string, boolean> {
  return useSyncExternalStore(subscribe, choices, choices)
}
