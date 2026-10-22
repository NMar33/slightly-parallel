import { describe, expect, it } from 'vitest'

/**
 * Every text the code passes to t(), tn() or tc() has a Russian entry in its
 * area's dictionary or in common.json. A file names its area by the scope it
 * imports from (`i18n/scope/<area>`); aliases (`import { t as tr }`) count.
 * Only literal arguments are checked: a t(variable) is the caller's job.
 */
const sources = import.meta.glob<string>(['../**/*.ts', '../**/*.tsx', '!../**/*.test.*', '!../i18n/**'], {
  eager: true, query: '?raw', import: 'default',
})
const files = import.meta.glob<Record<string, unknown>>('./ru/*.json', { eager: true, import: 'default' })
const DICTS: Record<string, Record<string, unknown>> = Object.fromEntries(
  Object.entries(files).map(([p, d]) => [p.replace(/^.*\/(\w+)\.json$/, '$1'), d]),
)
const COMMON = DICTS.common ?? {}

const IMPORT = /import\s*\{([^}]*)\}\s*from\s*['"](?:\.\.?\/)+i18n(?:\/scope\/(\w+))?['"]/
const SCOPED = /import\s*\{([^}]*)\}\s*from\s*['"](?:\.\.?\/)+i18n\/scope\/(\w+)['"]/

function unescape(s: string): string {
  return s.replace(/\\(['"`\\])/g, '$1').replace(/\\n/g, '\n')
}

/** Names this file uses for t, tn and tc. */
function names(spec: string): { t: string[]; tn: string[]; tc: string[] } {
  const out = { t: [] as string[], tn: [] as string[], tc: [] as string[] }
  for (const part of spec.split(',')) {
    const m = part.trim().match(/^(t|tn|tc)(?:\s+as\s+(\w+))?$/)
    if (m) out[m[1] as 't' | 'tn' | 'tc'].push(m[2] ?? m[1])
  }
  return out
}

function keysIn(src: string, spec: string): string[] {
  const n = names(spec)
  const keys: string[] = []
  const lit = String.raw`(['"\x60])((?:\\.|(?!\1).)*?)\1`
  const add = (q: string, raw: string, ctx?: string) => {
    const text = unescape(raw)
    if (q === '`' && text.includes('${')) return   // a template with code inside is not a key
    keys.push(ctx !== undefined ? `${ctx}|${text}` : text)
  }
  for (const fn of n.t) for (const m of src.matchAll(new RegExp(String.raw`(?<![\w.])${fn}\(\s*${lit}`, 'g'))) add(m[1], m[2])
  for (const fn of n.tn) for (const m of src.matchAll(new RegExp(String.raw`(?<![\w.])${fn}\(\s*[^,()]+,\s*${lit}`, 'g'))) add(m[1], m[2])
  for (const fn of n.tc) {
    const re = new RegExp(String.raw`(?<![\w.])${fn}\(\s*['"]([^'"]+)['"]\s*,\s*(['"\x60])((?:\\.|(?!\2).)*?)\2`, 'g')
    for (const m of src.matchAll(re)) add(m[2], m[3], m[1])
  }
  return keys
}

describe('the Russian dictionary', () => {
  it('has an entry for every t(), tn() and tc() text in the code, in its area or common', () => {
    const missing: string[] = []
    for (const [file, src] of Object.entries(sources)) {
      // The scope import names the area; a plain `from '../i18n'` (locale, setLang) may come first.
      const imp = src.match(SCOPED) ?? src.match(IMPORT)
      if (!imp) continue
      const own = imp[2] ? DICTS[imp[2]] ?? {} : {}
      for (const key of keysIn(src, imp[1])) {
        const bare = key.includes('|') ? key.slice(key.indexOf('|') + 1) : key
        if (!(key in own) && !(key in COMMON) && !(bare in own) && !(bare in COMMON)) {
          missing.push(`${file.replace('../', 'src/')}: ${key.slice(0, 80)}`)
        }
      }
    }
    expect(missing, `${missing.length} texts without a Russian entry`).toEqual([])
  })

  it('gives a plural entry its three forms', () => {
    const bad = Object.values(DICTS).flatMap((d) => Object.entries(d)).filter(([, v]) => v && typeof v === 'object'
      && !['one', 'few', 'many'].every((k) => typeof (v as Record<string, unknown>)[k] === 'string'))
    expect(bad.map(([k]) => k)).toEqual([])
  })

  it('keeps a key in common.json out of the area files, so one word reads one way', () => {
    const twice: string[] = []
    for (const [area, d] of Object.entries(DICTS)) {
      if (area === 'common') continue
      for (const k of Object.keys(d)) if (k in COMMON) twice.push(`${area}: ${k}`)
    }
    expect(twice).toEqual([])
  })

  it('sends no toast a bare string: every toast text goes through t() or tn()', () => {
    const bare: string[] = []
    // The first argument a literal, or a literal in a ternary's branch or an option.
    const first = /(?<![\w.])toast(?:\.\w+)?\(\s*(['"\x60])/g
    const branch = /(?<![\w.])toast(?:\.\w+)?\([^()\n]*?[?:]\s*(['"\x60])/g
    for (const [file, src] of Object.entries(sources)) {
      for (const m of [...src.matchAll(first), ...src.matchAll(branch)]) {
        const line = src.slice(0, m.index).split('\n').length
        bare.push(`${file.replace('../', 'src/')}:${line}`)
      }
    }
    expect(bare, `${bare.length} toasts with an untranslated literal`).toEqual([])
  })
})

