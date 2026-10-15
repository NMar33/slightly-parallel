/**
 * A movement item begins with its kind and a colon: `New: …`, `Fixed: …`.
 * The list of kinds lives in the standup prompt, where the operator edits
 * it, so the page takes any capitalised word before a colon as the kind and
 * shows older items, which have none, as they are.
 */
const KIND_RE = /^([A-Z][a-z]+):\s+(.*)$/s

/** The kinds in the order the page groups them; unknown kinds follow, then items with none. */
const KIND_ORDER = ['New', 'Changed', 'Fixed', 'Architecture', 'Cleanup', 'Decided']

export function splitKind(item: string): { kind: string; text: string } {
  const m = KIND_RE.exec((item ?? '').trim())
  return m ? { kind: m[1]!, text: m[2]!.trim() } : { kind: '', text: (item ?? '').trim() }
}

/** Items grouped by kind, in KIND_ORDER, unknown kinds after, kindless last. */
export function groupByKind(items: string[]): { kind: string; items: string[] }[] {
  const groups = new Map<string, string[]>()
  for (const it of items) {
    const { kind, text } = splitKind(it)
    groups.set(kind, [...(groups.get(kind) ?? []), text])
  }
  const rank = (k: string) => (k === '' ? 1000 : KIND_ORDER.indexOf(k) >= 0 ? KIND_ORDER.indexOf(k) : 100)
  return [...groups.entries()].sort((a, b) => rank(a[0]) - rank(b[0])).map(([kind, items]) => ({ kind, items }))
}
