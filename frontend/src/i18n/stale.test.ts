import { describe, expect, it } from 'vitest'

/**
 * The dictionary follows the English. A key is the English text, so when the
 * English changes, the old entry stays behind unused and the new text shows
 * untranslated. These tests catch both sides of that:
 *
 * - every entry's English still appears somewhere it can come from: the
 *   frontend source, the texts the server sends (backend/backend), or the
 *   keys the code builds at run time (runtime-keys.json) — an entry nothing
 *   can show is stale;
 * - every settings text the server sends has a Russian entry: the Settings
 *   page translates them with t(variable), which the coverage test cannot see.
 */
const sources = import.meta.glob<string>(['../**/*.ts', '../**/*.tsx', '!../**/*.test.*', '!../i18n/**'], {
  eager: true, query: '?raw', import: 'default',
})
const backend = import.meta.glob<string>('../../../backend/backend/app_settings.py', {
  eager: true, query: '?raw', import: 'default',
})
const backendAll = import.meta.glob<string>('../../../backend/backend/**/*.py', {
  eager: true, query: '?raw', import: 'default',
})
const files = import.meta.glob<Record<string, unknown>>('./ru/*.json', { eager: true, import: 'default' })
import runtimeKeys from './runtime-keys.json'

const SRC = Object.values(sources).join('\n')
const SETTINGS_PY = Object.values(backend)[0] ?? ''
const BACKEND = Object.values(backendAll).join('\n')
/** Keys the code builds at run time (a field name made readable, a unit put
 *  into a template): listed by hand in runtime-keys.json, with where. */
const RUNTIME = new Set(Object.keys((runtimeKeys as { keys: Record<string, string> }).keys))

function pyStrings(field: string): string[] {
  const out: string[] = []
  const lit = String.raw`"((?:[^"\\]|\\.)*)"`
  for (const m of SETTINGS_PY.matchAll(new RegExp(String.raw`\b${field}=(?:\(\s*((?:${lit}\s*)+)\)|${lit})`, 'g'))) {
    const block = m[1] ?? `"${m[3]}"`
    const parts = [...block.matchAll(new RegExp(lit, 'g'))].map((p) => p[1]!.replace(/\\"/g, '"').replace(/\\\\/g, '\\'))
    out.push(parts.join(''))
  }
  return out
}

const SERVER = [...new Set([...pyStrings('label'), ...pyStrings('description'), ...pyStrings('group')])]

describe('the dictionary and the English it translates', () => {
  it('reads the server settings file', () => {
    expect(SERVER.length).toBeGreaterThan(20)
  })

  it('keeps no entry whose English nothing can show any more', () => {
    const stale: string[] = []
    for (const [path, dict] of Object.entries(files)) {
      for (const key of Object.keys(dict)) {
        const body = key.includes('|') ? key.slice(key.indexOf('|') + 1) : key
        // A runtime key built as "prefix:" + value: the prefix is in the source.
        const prefix = /^[\w-]+:/.exec(body)?.[0]
        const seen = SRC.includes(body) || SRC.includes(body.replace(/'/g, "\\'"))
          || SRC.includes(JSON.stringify(body).slice(1, -1)) || SERVER.includes(body)
          || BACKEND.includes(body) || RUNTIME.has(body)
          || (prefix !== undefined && SRC.includes(prefix))
        if (!seen) stale.push(`${path.replace('./ru/', '')}: ${body.slice(0, 70)}`)
      }
    }
    expect(stale, `${stale.length} entries nothing shows`).toEqual([])
  })

  it('translates every settings text the server sends', () => {
    const all: Record<string, unknown> = Object.assign({}, ...Object.values(files))
    const missing = SERVER.filter((s) => !(s in all))
    expect(missing, `${missing.length} server texts without Russian`).toEqual([])
  })
})
