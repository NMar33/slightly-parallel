/**
 * The interface language: English or Russian.
 *
 * English is the source. Every user-facing string is written in English and
 * passed through `t()`; the Russian dictionary is keyed by that English text
 * (gettext style), so a string with no Russian entry shows in English rather
 * than as a key. A test lists every `t()` and `tn()` text in the code that has
 * no Russian entry (i18n/coverage.test.ts).
 *
 * The language is read once, when the app loads: a switch in Appearance
 * saves the choice and reloads the page. Module-level constants (catalogs,
 * guide texts) may therefore call `t()` at import time.
 *
 * Dictionaries live per area under `i18n/ru/*.json`, so parallel work on two
 * areas never edits one file. They are not in the main bundle: main.tsx
 * loads them (`loadDictionaries`) only for a Russian interface, before the
 * app's modules load, and falls back to English (`setLang`) when they fail. Docs: docs/wording.ru.md.
 */

export type Lang = 'en' | 'ru'

export const LANG_KEY = 'sp-lang'

type Plural = { one: string; few: string; many: string }
type Entry = string | Plural

const files = import.meta.glob<Record<string, Entry>>('./ru/*.json', { import: 'default' })
/** area name (the file's base name) → its dictionary; empty until `loadDictionaries`. */
export const DICTS: Record<string, Record<string, Entry>> = {}

/** Fetch every Russian dictionary into DICTS (each is its own chunk). */
export async function loadDictionaries(): Promise<void> {
  const loaded = await Promise.all(
    Object.entries(files).map(async ([path, load]) => [path.replace(/^.*\/(\w+)\.json$/, '$1'), await load()] as const),
  )
  for (const [area, d] of loaded) DICTS[area] = d
}

function detect(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    if (saved === 'ru' || saved === 'en') return saved
  } catch { /* private mode: fall through */ }
  try {
    if (typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('ru')) return 'ru'
  } catch { /* no navigator */ }
  return 'en'
}

let lang: Lang = detect()
/** The language chosen (saved), which tabs follow; `lang` differs only after a fallback (`setLang`). */
let chosen: Lang = lang

/** The language the app was loaded in. */
export const currentLang = (): Lang => lang

/**
 * Keep every open tab in the language last chosen. A tab reads the language
 * once, when it loads; a tab opened before the switch would go on showing
 * the old one (tk_363ccee7). So: another tab of this address changing the
 * choice reloads this one at once (`storage` event), and a tab coming back
 * into view asks the server for the choice — which also covers a tab opened
 * on another address (localhost against 127.0.0.1), whose storage is apart.
 * A tab never writes the language itself; only the pickers do.
 */
export function watchLanguage(): void {
  if (typeof window === 'undefined') return
  const follow = (v: string | null) => {
    if ((v === 'ru' || v === 'en') && v !== chosen) {
      try { localStorage.setItem(LANG_KEY, v) } catch { /* private mode */ }
      window.location.reload()
    }
  }
  // The language was read when this module loaded, before the server's copy
  // of the preferences reached storage: on an address that had an older
  // choice cached, the server's choice wins now, with one reload.
  try { follow(localStorage.getItem(LANG_KEY)) } catch { /* private mode */ }
  window.addEventListener('storage', (e) => { if (e.key === LANG_KEY) follow(e.newValue) })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return
    void fetch('/api/prefs').then((r) => (r.ok ? r.json() : null))
      .then((d: { prefs?: Record<string, string> } | null) => follow(d?.prefs?.[LANG_KEY] ?? null))
      .catch(() => { /* offline: keep what is shown */ })
  })
}

/**
 * Show the interface in another language than the one chosen, without
 * saving or reloading: for boot, when the Russian dictionaries fail to
 * arrive and the interface falls back to English. The choice stays as it
 * was, so watchLanguage does not reload the tab over it. Call it before the
 * app's modules load; a choice made in the interface goes through the
 * pickers, which save and reload.
 */
export function setLang(next: Lang): void { lang = next }

/** For tests: switch the chosen and the shown language, without a reload. */
export function setLangForTests(next: Lang): void { lang = next; chosen = next }

/** The locale for dates and numbers: `toLocaleDateString(locale(), …)`. */
export const locale = (): string => (lang === 'ru' ? 'ru-RU' : 'en-GB')

function fill(text: string, vars?: Record<string, string | number>): string {
  if (!vars) return text
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m))
}

/**
 * Where a key is looked up: the caller's area first (`i18n/scope/<area>.ts`
 * binds it), then `common.json`, then any dictionary. One English word can
 * mean different things in two areas ("open": a state, an action); each
 * area's own translation wins in its own files.
 */
function lookup<K extends 'string' | 'plural'>(key: string, area: string | undefined, kind: K): (K extends 'string' ? string : Plural) | undefined {
  const fits = (e: Entry | undefined) => (kind === 'string' ? typeof e === 'string' : !!e && typeof e === 'object')
  const order = [area ? DICTS[area] : undefined, DICTS.common, ...Object.values(DICTS)]
  for (const d of order) {
    const e = d?.[key]
    if (fits(e)) return e as K extends 'string' ? string : Plural
  }
  return undefined
}

function translate(area: string | undefined, text: string, vars?: Record<string, string | number>, context?: string): string {
  if (lang === 'ru') {
    const hit = (context ? lookup(`${context}|${text}`, area, 'string') : undefined) ?? lookup(text, area, 'string')
    if (hit !== undefined) return fill(hit, vars)
  }
  return fill(text, vars)
}

/**
 * A user-facing string. `{name}` placeholders are filled from `vars` after
 * the lookup, so the dictionary key keeps the placeholder:
 * `t('Removed {n} tasks.', { n })`.
 */
export function t(text: string, vars?: Record<string, string | number>): string {
  return translate(undefined, text, vars)
}

/**
 * A string whose English word has more than one meaning in one area:
 * the key `"context|text"` is tried first (`tc('action', 'Open')` →
 * «Открыть», `tc('state', 'Open')` → «Открыта»); English shows `text`.
 */
export function tc(context: string, text: string, vars?: Record<string, string | number>): string {
  return translate(undefined, text, vars, context)
}

const ruPlural = new Intl.PluralRules('ru-RU')

/**
 * A count with its noun, in the right plural form. English takes `one` and
 * `other`; the Russian entry under the `one` text holds the three forms
 * (one: 1, 21 · few: 2–4, 22–24 · many: 5–20, 0). `{n}` is the count:
 * `tn(n, '{n} task', '{n} tasks')`.
 */
export function tn(n: number, one: string, other: string, vars?: Record<string, string | number>): string {
  return plural(undefined, n, one, other, vars)
}

function plural(area: string | undefined, n: number, one: string, other: string, vars?: Record<string, string | number>): string {
  const all = { n, ...vars }
  if (lang === 'ru') {
    const hit = lookup(one, area, 'plural')
    if (hit) {
      const form = ruPlural.select(n)
      return fill(form === 'one' ? hit.one : form === 'few' ? hit.few : hit.many, all)
    }
  }
  return fill(n === 1 ? one : other, all)
}

/** The translators bound to one area's dictionary: `i18n/scope/<area>.ts`. */
export function scoped(area: string) {
  return {
    t: (text: string, vars?: Record<string, string | number>) => translate(area, text, vars),
    tc: (context: string, text: string, vars?: Record<string, string | number>) => translate(area, text, vars, context),
    tn: (n: number, one: string, other: string, vars?: Record<string, string | number>) => plural(area, n, one, other, vars),
  }
}
