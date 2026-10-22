import { t } from '../i18n/scope/shell'
/**
 * An entry's text, by what the entry holds.
 *
 * Every entry detail answer carries `text`: the entry's text under the names
 * of its lens (a decision's `why` and `alternatives`, a scan's `deltas`), in
 * the lens's order — the line, the text, the list, the long part. The server
 * still sends the storage slots beside it for older readers. This is the one
 * place in the pages that knows the slots exist: it reads `text`, and falls
 * back to the slots only when an answer has none (an older cached answer, a
 * mock).
 */

export interface EntryDetailLike {
  text?: Record<string, unknown> | null
  l2?: string | null
  l3?: string[] | null
  l4?: string | null
}

interface EntryPart {
  /** The field's name as the agent wrote it: `why`, `per_file`. */
  name: string
  /** The name for a reader: "Why", "Per file". */
  label: string
}

interface EntryText {
  /** The one line (the headline); '' when the answer does not carry it. */
  line: string
  /** The paragraph. */
  text: string
  /** The list, one item each. */
  list: string[]
  /** The long part: an excerpt, a diff, output. */
  long: string
  /** The same, by the lens's own names. */
  byName: Record<string, string | string[]>
  /** Name and label of each position; generic labels when only slots came. */
  parts: { line: EntryPart; text: EntryPart; list: EntryPart; long: EntryPart }
}

export function labelOf(name: string): string {
  const words = name.replace(/_/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : ''
}

// The label is shown as a heading: in the interface language (field names have entries in the dictionary).
const part = (name: string, fallback: string): EntryPart => ({ name, label: t(name ? labelOf(name) : fallback) })

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => String(x ?? '')) : [])

export function entryText(detail: EntryDetailLike | null | undefined): EntryText {
  const slots = {
    text: String(detail?.l2 ?? ''),
    list: strings(detail?.l3),
    long: String(detail?.l4 ?? ''),
  }
  const named = detail?.text && typeof detail.text === 'object' ? detail.text : null
  if (!named || Object.keys(named).length === 0) {
    return {
      line: '', ...slots, byName: {},
      parts: { line: part('', 'Headline'), text: part('', 'Summary'), list: part('', 'Details'), long: part('', 'More') },
    }
  }
  const keys = Object.keys(named)
  const byName: Record<string, string | string[]> = {}
  for (const k of keys) byName[k] = Array.isArray(named[k]) ? strings(named[k]) : String(named[k] ?? '')
  // The order is the lens's: the line first, then the text, the list, the
  // long part. A lens may lack one of them; the list is the array.
  const lineKey = keys[0]
  const listKey = keys.slice(1).find((k) => Array.isArray(named[k])) ?? ''
  const rest = keys.slice(1).filter((k) => k !== listKey)
  let textKey = rest[0] ?? ''
  let longKey = rest[1] ?? ''
  if (rest.length === 1 && listKey && keys.indexOf(rest[0]) > keys.indexOf(listKey)) {
    textKey = ''
    longKey = rest[0]
  }
  return {
    line: String(byName[lineKey] ?? ''),
    text: textKey ? String(byName[textKey]) : '',
    list: listKey ? (byName[listKey] as string[]) : [],
    long: longKey ? String(byName[longKey]) : '',
    byName,
    parts: {
      line: part(lineKey, 'Headline'), text: part(textKey, 'Summary'),
      list: part(listKey, 'Details'), long: part(longKey, 'More'),
    },
  }
}
