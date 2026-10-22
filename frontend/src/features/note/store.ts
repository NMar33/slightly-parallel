import { persistPref } from '../../lib/uiPrefs'

/**
 * The quick note's storage, shared by the note panel and anywhere that wants
 * to take the note away — the task window, for one.
 *
 * Both the note and its history live in the preference store, a flat
 * string→string file at the data root that syncs across origins, so they
 * survive a reload, a restart and a different port. That store caps a value
 * at 8192 characters, which shapes the design: the note itself is capped
 * below that, and the history is a budget rather than a count — ten versions
 * if they are short, fewer if they are long, oldest dropped first.
 *
 * A version is kept at the moments text would otherwise be destroyed:
 * clearing, handing the note to a task, and an edit that deletes most of
 * what was there (a select-all-and-type, the classic way to lose a note).
 */

const NOTE_KEY = 'sp-quick-note'
const HISTORY_KEY = 'sp-quick-note-history'
export const NOTE_LIMIT = 8000
const HISTORY_MAX = 10
const HISTORY_BUDGET = 7000

export type Version = { at: number; text: string }

const read = (key: string): string => {
  try { return localStorage.getItem(key) ?? '' } catch { return '' }
}

export const readNote = (): string => read(NOTE_KEY)

export function writeNote(text: string): void {
  persistPref(NOTE_KEY, text.slice(0, NOTE_LIMIT))
}

export function readHistory(): Version[] {
  try {
    const raw = read(HISTORY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((v) => v && typeof v.text === 'string' && typeof v.at === 'number')
      .slice(0, HISTORY_MAX)
  } catch {
    return []
  }
}

function writeHistory(versions: Version[]): void {
  // Newest first, then dropped from the back until the store will take it.
  let kept = versions.slice(0, HISTORY_MAX)
  let body = JSON.stringify(kept)
  while (kept.length > 1 && body.length > HISTORY_BUDGET) {
    kept = kept.slice(0, kept.length - 1)
    body = JSON.stringify(kept)
  }
  // A single version longer than the budget is trimmed rather than lost.
  if (kept.length === 1 && body.length > HISTORY_BUDGET) {
    kept = [{ ...kept[0]!, text: kept[0]!.text.slice(0, HISTORY_BUDGET - 200) }]
    body = JSON.stringify(kept)
  }
  persistPref(HISTORY_KEY, body)
}

/** Keep what is about to be destroyed. No-op for blank or unchanged text. */
export function snapshot(text: string): void {
  const body = text.trim()
  if (!body) return
  const versions = readHistory()
  if (versions[0]?.text.trim() === body) return
  writeHistory([{ at: Date.now(), text }, ...versions])
}

/** Take the note away: the caller gets the text, the note keeps the memory. */
export function consumeNote(): string {
  const text = readNote()
  if (!text.trim()) return ''
  snapshot(text)
  writeNote('')
  return text
}

/** True when an edit throws away most of what was written. */
export const isDestructiveEdit = (before: string, after: string): boolean =>
  before.trim().length >= 40 && after.trim().length < before.trim().length / 2
