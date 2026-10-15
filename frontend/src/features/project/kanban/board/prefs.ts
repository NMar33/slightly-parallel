/*
 * A board's remembered choices are read with `useKeyedPref` (lib/uiPrefs):
 * one value per board key, read again when the key changes.
 */

import { readJsonPref } from '../../../../lib/uiPrefs'

/** A stored JSON object, or {} when absent, unreadable or not an object. */
export function readRecord<V>(key: string): Record<string, V> {
  const raw = readJsonPref<unknown>(key, {})
  return raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, V>) : {}
}

/** A stored list of strings, or [] when absent or unreadable. */
export function readStrings(key: string): string[] {
  const raw = readJsonPref<unknown>(key, [])
  return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === 'string') : []
}
