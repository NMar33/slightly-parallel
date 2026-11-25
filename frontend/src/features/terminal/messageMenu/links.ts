/**
 * The link under a right click in the terminal (tk_b3edbd84, the operator:
 * «при щелчке правой клавишей мыши по ссылке нет варианта скопировать»):
 * a web address (what xterm's web-links addon underlines), a printed path
 * that Ctrl+click opens in the editor, or a record of Slightly Parallel the
 * layer underlines (ids.ts). The menu offers to copy it, as printed, above
 * the message's own items.
 */

import { findPaths, type PrintedPath } from '../printedPaths'
import { findIds, type FoundId } from './ids'

export type TermLink =
  | { kind: 'url'; text: string; start: number; length: number }
  | { kind: 'path'; text: string; start: number; length: number; path: PrintedPath }
  | { kind: 'id'; text: string; start: number; length: number; id: FoundId }

// http(s) up to a space or a quote; the punctuation that ends a sentence is not the address's.
const URL_RE = /\bhttps?:\/\/[^\s"'<>`]+/gi
const RELATIVE_ADDRESS_RE = /(?<![\w/])\/(?=[a-z0-9#?])[^\s"'<>`]+/gi

export function findUrls(text: string): Array<{ text: string; start: number; length: number }> {
  const out: Array<{ text: string; start: number; length: number }> = []
  for (const m of text.matchAll(URL_RE)) {
    let s = m[0]
    for (;;) {
      const last = s.at(-1)!
      if ('.,;:!?'.includes(last)) { s = s.slice(0, -1); continue }
      // A closing bracket the address never opened: the sentence's.
      const pair: Record<string, string> = { ')': '(', ']': '[', '}': '{' }
      if (pair[last] && s.split(pair[last]).length <= s.split(last).length - 1) { s = s.slice(0, -1); continue }
      break
    }
    if (s.length > 'https://'.length) out.push({ text: s, start: m.index!, length: s.length })
  }
  return out
}

export function findRecordLinks(text: string, urls = findUrls(text)): FoundId[] {
  const addresses = [...urls, ...[...text.matchAll(RELATIVE_ADDRESS_RE)].map((m) => ({ start: m.index!, length: m[0].length }))]
  return findIds(text).filter((id) => !addresses.some(({ start, length }) => id.start >= start && id.start < start + length))
}

/**
 * The link at character `at` of a row: an id first (a commit only when
 * `commitOk` says it is one), then a web address, then a printed path
 * (only when the terminal has an editor to open it in).
 */
export function linkAt(text: string, at: number, opts: { commitOk: (sha: string) => boolean; paths: boolean }): TermLink | null {
  const on = (f: { start: number; length: number }) => at >= f.start && at < f.start + f.length
  const urls = findUrls(text)
  const id = findRecordLinks(text, urls).find((f) => on(f) && (f.kind !== 'commit' || opts.commitOk(f.id)))
  if (id) return { kind: 'id', text: id.id, start: id.start, length: id.length, id }
  const url = urls.find(on)
  if (url) return { kind: 'url', ...url }
  if (opts.paths) {
    const p = findPaths(text).find(on)
    if (p) return { kind: 'path', text: p.text, start: p.start, length: p.length, path: p }
  }
  return null
}
