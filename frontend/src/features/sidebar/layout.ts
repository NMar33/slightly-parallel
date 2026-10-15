import { CATALOG, CATALOG_BY_KEY, DEFAULT_GROUPS } from './catalog'

/**
 * The sidebar layout — which pages show, in which groups, in what order.
 *
 * Pure functions over a small value. Every operation returns a new layout
 * and never touches the catalogue: a key the catalogue no longer knows is
 * dropped on read, a key it has gained is slotted into its home group. So
 * a layout arranged today still reads correctly after pages come and go.
 *
 * `hidden` is the operator's "not for me" list. The sidebar shows it as
 * one folded group at the end, so nothing is ever lost — only put away.
 */
export interface Group {
  id: string
  label: string
  items: string[]
}

export interface Layout {
  v: 1
  groups: Group[]
  hidden: string[]
  /** Group ids folded shut in the sidebar; `hidden` folds the hidden group. */
  folded: string[]
}

export const HIDDEN_GROUP = 'hidden'
const MAX_LABEL = 32

export function defaultLayout(): Layout {
  return normalize({ v: 1, groups: [], hidden: [], folded: [HIDDEN_GROUP] })
}

function str(x: unknown): string | null {
  return typeof x === 'string' ? x : null
}

function cleanLabel(x: unknown, fallback: string): string {
  const s = (str(x) ?? '').replace(/\s+/g, ' ').trim().slice(0, MAX_LABEL)
  return s || fallback
}

/** Any value → a layout the sidebar can render. Never throws. */
export function normalize(raw: unknown): Layout {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const seen = new Set<string>()
  const groups: Group[] = []
  const usedIds = new Set<string>()
  for (const g of Array.isArray(r.groups) ? r.groups : []) {
    if (!g || typeof g !== 'object') continue
    const go = g as Record<string, unknown>
    const id = str(go.id)?.trim()
    if (!id || usedIds.has(id) || id === HIDDEN_GROUP) continue
    usedIds.add(id)
    const items: string[] = []
    for (const k of Array.isArray(go.items) ? go.items : []) {
      if (typeof k !== 'string' || seen.has(k) || !CATALOG_BY_KEY.has(k)) continue
      seen.add(k)
      items.push(k)
    }
    groups.push({ id, label: cleanLabel(go.label, DEFAULT_GROUPS.find((d) => d.id === id)?.label ?? 'Group'), items })
  }
  const hidden: string[] = []
  for (const k of Array.isArray(r.hidden) ? r.hidden : []) {
    if (typeof k !== 'string' || seen.has(k) || !CATALOG_BY_KEY.has(k)) continue
    seen.add(k)
    hidden.push(k)
  }
  // Pages the layout has never met go to their home group, created on demand.
  for (const e of CATALOG) {
    if (seen.has(e.key)) continue
    let g = groups.find((x) => x.id === e.home)
    if (!g) {
      g = { id: e.home, label: DEFAULT_GROUPS.find((d) => d.id === e.home)?.label ?? e.home, items: [] }
      groups.push(g)
    }
    g.items.push(e.key)
    seen.add(e.key)
  }
  const ids = new Set([...groups.map((g) => g.id), HIDDEN_GROUP])
  const folded = Array.isArray(r.folded)
    ? r.folded.filter((x): x is string => typeof x === 'string' && ids.has(x))
    : [HIDDEN_GROUP]
  return { v: 1, groups, hidden, folded: [...new Set(folded)] }
}

export function parseLayout(json: string | null | undefined): Layout {
  if (!json) return defaultLayout()
  try { return normalize(JSON.parse(json)) } catch { return defaultLayout() }
}

export function serialize(l: Layout): string {
  return JSON.stringify(l)
}

/** Where a key lives: a group id, `hidden`, or undefined when unknown. */
export function groupOf(l: Layout, key: string): string | undefined {
  if (l.hidden.includes(key)) return HIDDEN_GROUP
  return l.groups.find((g) => g.items.includes(key))?.id
}

function without(l: Layout, key: string): Layout {
  return {
    ...l,
    groups: l.groups.map((g) => (g.items.includes(key) ? { ...g, items: g.items.filter((k) => k !== key) } : g)),
    hidden: l.hidden.filter((k) => k !== key),
  }
}

function insertAt<T>(arr: T[], item: T, index: number | undefined): T[] {
  const i = index === undefined ? arr.length : Math.max(0, Math.min(index, arr.length))
  return [...arr.slice(0, i), item, ...arr.slice(i)]
}

/**
 * Put `key` into `groupId` (or `hidden`) at `index`. The index counts
 * positions in the destination *after* the key has left its old place,
 * which is what a drop target means.
 */
export function moveItem(l: Layout, key: string, groupId: string, index?: number): Layout {
  if (!CATALOG_BY_KEY.has(key)) return l
  const base = without(l, key)
  if (groupId === HIDDEN_GROUP) return { ...base, hidden: insertAt(base.hidden, key, index) }
  if (!base.groups.some((g) => g.id === groupId)) return l
  return {
    ...base,
    groups: base.groups.map((g) => (g.id === groupId ? { ...g, items: insertAt(g.items, key, index) } : g)),
  }
}

export function hideItem(l: Layout, key: string): Layout {
  return moveItem(l, key, HIDDEN_GROUP)
}

/** Back from hidden — to its home group, or the first group when home is gone. */
export function showItem(l: Layout, key: string, groupId?: string, index?: number): Layout {
  const home = groupId ?? CATALOG_BY_KEY.get(key)?.home
  const target = l.groups.some((g) => g.id === home) ? (home as string) : l.groups[0]?.id
  if (!target) return l
  return moveItem(l, key, target, index)
}

export function renameGroup(l: Layout, id: string, label: string): Layout {
  return { ...l, groups: l.groups.map((g) => (g.id === id ? { ...g, label: cleanLabel(label, g.label) } : g)) }
}

export function newGroupId(): string {
  return `g_${Math.random().toString(36).slice(2, 8)}`
}

export function addGroup(l: Layout, label: string, id = newGroupId(), index?: number): Layout {
  if (l.groups.some((g) => g.id === id) || id === HIDDEN_GROUP) return l
  return { ...l, groups: insertAt(l.groups, { id, label: cleanLabel(label, 'New group'), items: [] }, index) }
}

/** Remove a group; its pages join the group above (or below, for the first). */
export function removeGroup(l: Layout, id: string): Layout {
  const i = l.groups.findIndex((g) => g.id === id)
  if (i < 0 || l.groups.length < 2) return l
  const gone = l.groups[i]
  const into = i > 0 ? i - 1 : 1
  const groups = l.groups
    .map((g, j) => (j === into ? { ...g, items: [...g.items, ...gone.items] } : g))
    .filter((_, j) => j !== i)
  return { ...l, groups, folded: l.folded.filter((f) => f !== id) }
}

export function moveGroup(l: Layout, id: string, index: number): Layout {
  const g = l.groups.find((x) => x.id === id)
  if (!g) return l
  return { ...l, groups: insertAt(l.groups.filter((x) => x.id !== id), g, index) }
}

export function toggleFold(l: Layout, id: string): Layout {
  return { ...l, folded: l.folded.includes(id) ? l.folded.filter((f) => f !== id) : [...l.folded, id] }
}

/** Same arrangement as the default (folds do not count). */
export function isDefault(l: Layout): boolean {
  const d = defaultLayout()
  return JSON.stringify({ g: l.groups, h: l.hidden }) === JSON.stringify({ g: d.groups, h: d.hidden })
}

export function summary(l: Layout): { groups: number; shown: number; hidden: number } {
  return {
    groups: l.groups.length,
    shown: l.groups.reduce((n, g) => n + g.items.length, 0),
    hidden: l.hidden.length,
  }
}
