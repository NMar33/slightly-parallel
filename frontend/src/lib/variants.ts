import { readPref } from '../lib/uiPrefs'
import { useSyncExternalStore } from 'react'
import { persistPref, removePref } from '../lib/uiPrefs'
import { t } from '../i18n/scope/shell'

/**
 * The appearance choices — skin, interface scale, accent: switchable
 * options the operator picks on the Appearance page. Each choice is kept
 * as a UI preference (`sp-variant-<set>`, lib/uiPrefs).
 */

interface VariantOption {
  id: string
  label: string
  description: string
}

interface VariantSet {
  key: string          // storage key suffix and registry id
  title: string
  /** What this set changes, in one sentence. */
  scope: string
  /** Where to see it — route the gallery's "view" button navigates to. */
  exampleRoute: string
  options: VariantOption[]
  defaultOption: string
  /**
   * Ids this set used to publish, mapped to the id that replaced them. A
   * rename is a removal from the operator's point of view: the choice they
   * made is stored under the old id, and a resolver that does not know it
   * silently hands them the default. Every rename adds a line here.
   */
  aliases?: Record<string, string>
}

export const VARIANT_SETS: VariantSet[] = [
  {
    key: 'skin',
    title: t('App skin'),
    scope:
      t('A complete look for the app: fonts, background, text colour and corner shape. A skin sets its own background and accent, so the theme and accent settings apply only to the default skin.'),
    exampleRoute: '/',
    defaultOption: 'none',
    options: [
      {
        id: 'none',
        label: t('Default'),
        description: t('Sans-serif text, rounded corners, teal accent. Follows the theme and accent settings.'),
      },
      {
        id: 'terminal',
        label: t('Terminal phosphor'),
        description:
          t('Monospace text, green on black, scan lines, square corners. Always dark.'),
      },
      {
        id: 'broadsheet',
        label: t('Broadsheet'),
        description:
          t('Serif text on cream, thin rules, square corners, red accent. Always light.'),
      },
      {
        id: 'mission',
        label: t('Dark blue'),
        description:
          t('Blue-black background, cyan figures, amber warnings, uppercase headings. Always dark.'),
      },
      {
        id: 'rams',
        label: t('Rams'),
        description:
          t('Plain sans-serif text on warm grey, thin rules, one orange accent. Always light.'),
      },
    ],
  },
  {
    key: 'scale',
    title: t('Interface scale'),
    scope: t('The size of the whole interface: text, spacing and charts together.'),
    exampleRoute: '/settings/appearance',
    defaultOption: '100',
    options: [
      { id: '90', label: t('Compact · 90%'), description: t('More rows on screen.') },
      { id: '100', label: t('Default · 100%'), description: t('The size the pages were designed for.') },
      { id: '110', label: t('Comfortable · 110%'), description: t('Slightly larger.') },
      { id: '125', label: t('Large · 125%'), description: t('For presentations and large screens.') },
    ],
  },
  {
    key: 'accent',
    title: t('Accent color'),
    scope: t('The colour of active items, links and highlights. A skin sets its own.'),
    exampleRoute: '/settings/appearance',
    defaultOption: 'meridian',
    options: [
      { id: 'meridian', label: t('Teal'), description: t('Green-teal. The default.') },
      { id: 'indigo', label: t('Indigo'), description: t('Blue-violet.') },
      { id: 'violet', label: t('Violet'), description: t('Purple.') },
      { id: 'ember', label: t('Ember'), description: t('Amber-orange.') },
    ],
  },
]

const SET_BY_KEY = new Map(VARIANT_SETS.map((s) => [s.key, s]))

const storageKey = (setKey: string) => `sp-variant-${setKey}`

const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}

export function getVariant(setKey: string): string {
  const set = SET_BY_KEY.get(setKey)
  if (!set) return ''
  try {
    const stored = readPref(storageKey(setKey))
    const raw = stored && set.aliases?.[stored] ? set.aliases[stored] : stored
    if (raw && set.options.some((o) => o.id === raw)) return raw
  } catch {
    /* storage unavailable (SSR, privacy mode) — fall through to default */
  }
  return set.defaultOption
}

export function setVariant(setKey: string, optionId: string): void {
  const set = SET_BY_KEY.get(setKey)
  if (!set || !set.options.some((o) => o.id === optionId)) return
  try {
    if (optionId === set.defaultOption) {
      // Clear the server copy too — otherwise the next hydration would
      // resurrect the old choice on every reload.
      removePref(storageKey(setKey))
    } else {
      persistPref(storageKey(setKey), optionId)
    }
  } catch {
    /* ignore */
  }
  emit()
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb)
  const onStorage = (e: StorageEvent) => {
    if (e.key?.startsWith('sp-variant-')) cb()
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(cb)
    window.removeEventListener('storage', onStorage)
  }
}

/** The active option id for a variant set; re-renders on change. */
export function useVariant(setKey: string): string {
  return useSyncExternalStore(subscribe, () => getVariant(setKey))
}
