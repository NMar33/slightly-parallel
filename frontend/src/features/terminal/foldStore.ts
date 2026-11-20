/**
 * Which messages are collapsed, per terminal (fold.ts), kept in this
 * browser's localStorage: `sp-term-folds` = { [terminal id]: { ids, at } }.
 *
 * Why here and not in the server's ui prefs: it is a view of one terminal's
 * history in one window, changed by a click and read on every reader made;
 * nothing on the server or on another machine reads it, and a terminal's
 * id outlives a reload (tmux keeps it), which is all it needs. Left out of
 * the server's copy of `sp-*` keys (lib/uiPrefs EXCLUDE_PREFIXES): hydrated
 * from there, a reload brought back an old map over the live one. A message is
 * named by its text (fold.ts), so a collapse holds as the history grows.
 * Bounded: 400 messages a terminal, terminals unused for 60 days dropped.
 */

const KEY = 'sp-term-folds'
const MAX_IDS = 400
const MAX_AGE_MS = 60 * 24 * 3600 * 1000

type Kept = Record<string, { ids: string[]; at: number }>

let cache: Kept | null = null
type Listener = (sid: string, origin: unknown) => void
const listeners = new Set<Listener>()

function read(): Kept {
  if (cache) return cache
  let got: Kept = {}
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '{}') as unknown
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const [sid, e] of Object.entries(v as Record<string, unknown>)) {
        const x = e as { ids?: unknown; at?: unknown }
        if (Array.isArray(x?.ids)) got[sid] = { ids: x.ids.filter((i): i is string => typeof i === 'string'), at: typeof x.at === 'number' ? x.at : 0 }
      }
    }
  } catch { got = {} }
  cache = got
  return got
}

function write(k: Kept) {
  const now = Date.now()
  for (const [sid, e] of Object.entries(k)) if (!e.ids.length || now - e.at > MAX_AGE_MS) delete k[sid]
  cache = k
  try { localStorage.setItem(KEY, JSON.stringify(k)) } catch { /* private window: kept for this page only */ }
}

/** The collapsed message ids of terminal `sid`. */
export function foldIds(sid: string): ReadonlySet<string> {
  return new Set(read()[sid]?.ids ?? [])
}

export const hasFolds = (sid: string) => (read()[sid]?.ids.length ?? 0) > 0

/** Collapse (`on`) or expand messages of terminal `sid`. `origin`: who did it (its own listener is not told). */
export function setFolds(sid: string, ids: string[], on: boolean, origin?: unknown): void {
  const k = { ...read() }
  const now = new Set(k[sid]?.ids ?? [])
  for (const id of ids) { if (on) { now.delete(id); now.add(id) } else now.delete(id) }
  // The newest kept when over the bound.
  k[sid] = { ids: [...now].slice(-MAX_IDS), at: Date.now() }
  write(k)
  for (const l of listeners) l(sid, origin)
}

/** Expand every message of terminal `sid`. */
export function clearFolds(sid: string, origin?: unknown): void {
  const k = { ...read() }
  delete k[sid]
  write(k)
  for (const l of listeners) l(sid, origin)
}

/** Told of every change: the terminal it was in and who made it. */
export function onFolds(l: Listener): () => void {
  listeners.add(l)
  return () => { listeners.delete(l) }
}

/** Another window changed them (the storage event): read again. */
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== KEY) return
    const before = cache ?? {}
    cache = null
    const after = read()
    for (const sid of new Set([...Object.keys(before), ...Object.keys(after)])) {
      if ((before[sid]?.ids ?? []).join() !== (after[sid]?.ids ?? []).join()) for (const l of listeners) l(sid, null)
    }
  })
}

/** For tests: forget what was read. */
export function resetFoldsForTests(): void { cache = null }
