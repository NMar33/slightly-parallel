/**
 * uiPrefs — UI preferences that survive origin changes.
 *
 * localStorage is per-origin: localhost vs 127.0.0.1, :5173 vs :8123, or a
 * Vite port bump each read a different store, which looks like "the
 * dashboard forgot my settings" after a restart. The server's
 * `ui_prefs.json` is the durable copy; localStorage is only a cache:
 *
 * - `hydratePrefs()` runs before the app mounts — server values are written
 *   into localStorage (so every existing synchronous read keeps working),
 *   then local keys the server has never seen are pushed up once, which
 *   rescues preferences stranded on whichever origin you open first.
 * - `persistPref(key, value)` replaces `localStorage.setItem` at pref call
 *   sites — writes the cache and debounce-syncs syncable keys to the server.
 *
 * What syncs: `sp-*` keys, minus per-browser state — drafts (local
 * safety nets) and live terminal session lists.
 *
 * Every key is `sp-a-b`. Until 2026-10-14 the prefix was the working title
 * (`merkhet-a-b`), and until 2026-09-23 the spelling was `merkhet.a.b`;
 * `readPref` answers with the new key and, the first time, with the old
 * one, which it then copies under the new name — nobody loses a saved
 * choice. Pages that read localStorage directly get the same through
 * `adoptOldKeys()`, which `hydratePrefs()` runs before the app mounts.
 */

import { useState } from 'react'

import { getJson, postJson } from './getJson'

const PREFIX = 'sp-'
const OLD_PREFIX = 'merkhet-'

const EXCLUDE_PREFIXES = [
  'sp-note-draft:',
  'sp-note-edit:',
  'sp-task-draft:',
  'sp-doc-block-draft:',
  'sp-release-draft:',
]

export function isSyncable(key: string): boolean {
  if (!key.startsWith(PREFIX)) return false
  return !EXCLUDE_PREFIXES.some((p) => key.startsWith(p))
}

let pending: Record<string, string | null> = {}
let timer: ReturnType<typeof setTimeout> | null = null

/**
 * Send what is queued now. A page that reloads right after a change (the
 * language switch) calls this first: the 400 ms wait would outlive the page,
 * the server would keep the old value, and the next load would bring it back
 * (tk_363ccee7). Leaving the page flushes too.
 */
export function flushPrefs(): void { if (timer) clearTimeout(timer); flush() }

/**
 * Save one preference and wait until the server has it — for a change the
 * page reloads on: the reloaded page reads the server's copy first, so it
 * must already hold the new value. Resolves either way (offline: the local
 * copy still holds it).
 */
export async function savePrefNow(key: string, value: string): Promise<void> {
  delete pending[key]
  await fetch('/api/prefs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values: { [key]: value } }), keepalive: true,
  }).catch(() => { /* offline */ })
  // Written locally only now: other tabs reload on this write, and must find
  // the server already holding it.
  try { localStorage.setItem(key, value) } catch { /* private mode */ }
}

if (typeof window !== 'undefined') window.addEventListener('pagehide', () => flushPrefs())

function flush(): void {
  const values = pending
  pending = {}
  timer = null
  if (Object.keys(values).length === 0) return
  void fetch('/api/prefs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
    keepalive: true, // survives tab close mid-debounce
  }).catch(() => { /* offline backend — the local cache still holds it */ })
}

function queue(key: string, value: string | null): void {
  if (!isSyncable(key)) return
  pending[key] = value
  if (timer) clearTimeout(timer)
  timer = setTimeout(flush, 400)
}

/**
 * Tell the open page that a preference changed.
 *
 * Two panels can share one decision — bringing the guide back on a page
 * (its "About this page" button) also brings back the link to that page's
 * tour, after ✕ on the link put it away. They are separate components, so
 * the change has to travel.
 */
function announce(key: string, value: string | null): void {
  try {
    window.dispatchEvent(new CustomEvent('sp:pref', { detail: { key, value } }))
  } catch { /* no window: tests, SSR */ }
}

/** Drop-in for localStorage.setItem at preference call sites. */
export function persistPref(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* private mode */ }
  queue(key, value)
  announce(key, value)
}

/** Drop-in for localStorage.removeItem at preference call sites. */
export function removePref(key: string): void {
  try { localStorage.removeItem(key) } catch { /* fine */ }
  queue(key, null)
  announce(key, null)
}

/**
 * Server → localStorage, then seed local-only keys back up. Bounded: a dead
 * backend must never blank the UI, so the fetch races a short timeout and
 * every failure resolves to "use the cache as-is".
 */
export async function hydratePrefs(timeoutMs = 1500): Promise<void> {
  adoptOldKeys()
  try {
    const data = await Promise.race([
      getJson<{ prefs?: Record<string, string> }>('/api/prefs'),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), timeoutMs)),
    ])
    if (!data) return
    const server = data?.prefs && typeof data.prefs === 'object' ? data.prefs : {}
    for (const [k, v] of Object.entries(server)) {
      try { localStorage.setItem(k, String(v)) } catch { /* quota */ }
    }
    // The server's copy may still be under the old prefix: adopted now,
    // the new keys go up with the orphans below.
    adoptOldKeys()
    // Rescue: local prefs this server has never seen (first boot after the
    // feature, or a preference set while the backend was down).
    const orphans: Record<string, string> = {}
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i)
        if (!k || !isSyncable(k) || k in server) continue
        const v = localStorage.getItem(k)
        if (v !== null) orphans[k] = v
      }
    } catch { /* fine */ }
    if (Object.keys(orphans).length > 0) {
      void postJson('/api/prefs', { values: orphans }).catch(() => { /* next boot retries */ })
    }
  } catch { /* cache-only session */ }
}


/**
 * The spellings a key had before, newest first: `sp-a-b` was `merkhet-a-b`
 * until 2026-10-14 and `merkhet.a.b` until 2026-09-23.
 */
function legacyKeys(key: string): string[] {
  if (!key.startsWith(PREFIX)) return []
  const rest = key.slice(PREFIX.length)
  return [OLD_PREFIX + rest, `merkhet.${rest.replace(/-/g, '.')}`]
}

/**
 * Copy a value kept under an old spelling of `key` to `key`, once: the first
 * read of a renamed key finds what the browser held before. The old copy
 * stays where it is — a checkout from before the rename still reads it.
 */
function adoptOldKey(key: string): string | null {
  for (const old of legacyKeys(key)) {
    const kept = localStorage.getItem(old)
    if (kept === null) continue
    persistPref(key, kept)
    return kept
  }
  return null
}

/**
 * Every `merkhet-*` key in this browser whose `sp-*` twin is absent gets
 * copied under the new name. Pages that read localStorage directly (not
 * through `readPref`) find their value after this; it runs before the app
 * mounts and again when the server's copy has landed.
 */
export function adoptOldKeys(): void {
  try {
    const olds: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith(OLD_PREFIX)) olds.push(k)
    }
    for (const old of olds) {
      const key = PREFIX + old.slice(OLD_PREFIX.length)
      if (localStorage.getItem(key) === null) adoptOldKey(key)
    }
  } catch { /* no storage */ }
}

/**
 * Read a stored preference. Falls back once to the spellings the key had
 * before, and writes the value under the new name.
 */
export function readPref(key: string): string | null {
  try {
    const now = localStorage.getItem(key)
    if (now !== null) return now
    return adoptOldKey(key)
  } catch {
    return null
  }
}

/** A preference that is a value, not a word: stored as JSON, the fallback when absent or unreadable. */
export function readJsonPref<T>(key: string, fallback: T): T {
  try {
    const raw = readPref(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

export function persistJsonPref(key: string, value: unknown): void {
  try { persistPref(key, JSON.stringify(value)) } catch { /* fine */ }
}

/**
 * A remembered choice that belongs to a key (a project, a board): read
 * again when the key changes. A page reused for the next project would
 * otherwise carry the last project's choice over, and write it under the
 * new key on the next click.
 */
export function useKeyedPref<T>(
  key: string,
  read: (key: string) => T,
  write: (key: string, value: T) => void = (k, v) => persistPref(k, JSON.stringify(v)),
): [T, (next: T) => void] {
  const [held, setHeld] = useState(() => ({ key, value: read(key) }))
  let value = held.value
  if (held.key !== key) {
    value = read(key)
    setHeld({ key, value })
  }
  const set = (next: T) => {
    setHeld({ key, value: next })
    write(key, next)
  }
  return [value, set]
}
