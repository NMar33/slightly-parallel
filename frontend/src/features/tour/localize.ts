import { DICTS, currentLang } from '../../i18n'

/**
 * A beat names its subject by the English words on the page
 * (`[aria-label="Open now"]`). In Russian the page shows the Russian words,
 * so the selector is widened to match either: every aria-label value in it
 * is looked up in all the dictionaries, as a whole text, as a template the
 * code filled (`Unfold the {label} column`), or, for a prefix match (`^=`),
 * as the start of a template (`From problem {id}`).
 */
const cache = new Map<string, string>()

function plain(text: string): string[] {
  const out: string[] = []
  for (const d of Object.values(DICTS)) {
    const hit = d[text]
    if (typeof hit === 'string') out.push(hit)
  }
  return out
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function variants(value: string, prefix: boolean): string[] {
  const out = new Set<string>([value, ...plain(value)])
  for (const d of Object.values(DICTS)) {
    for (const [key, ru] of Object.entries(d)) {
      if (typeof ru !== 'string' || !key.includes('{')) continue
      if (prefix) {
        if (key.startsWith(value) && key.length > value.length) {
          const head = ru.split('{')[0]!
          if (head.trim()) out.add(head)
        }
        continue
      }
      const names: string[] = []
      const re = new RegExp('^' + key.split(/\{(\w+)\}/).map((part, i) => {
        if (i % 2) { names.push(part); return '(.+)' }
        return escapeRe(part)
      }).join('') + '$')
      const m = re.exec(value)
      if (!m) continue
      let filled = ru
      names.forEach((name, i) => {
        const word = m[i + 1]!
        filled = filled.split(`{${name}}`).join(plain(word)[0] ?? word)
      })
      out.add(filled)
    }
  }
  return [...out]
}

export function localizeSelector(selector: string): string {
  if (currentLang() === 'en') return selector
  const known = cache.get(selector)
  if (known !== undefined) return known
  // A control with no label of its own is named by its title (a switch
  // chip on the board): widened the same way.
  const m = /(aria-label|title)(\^?)="([^"]*)"/.exec(selector)
  let out = selector
  if (m) {
    const all = variants(m[3]!, m[2] === '^')
    out = all.map((v) => selector.replace(m[0], `${m[1]}${m[2]}="${v.replace(/"/g, '\\"')}"`)).join(', ')
  }
  cache.set(selector, out)
  return out
}
