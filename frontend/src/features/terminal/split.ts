/**
 * How a terminal surface is split: a small tree. A leaf is one terminal; a
 * split lays its children side by side ('row') or stacked ('col'), each
 * with its share of the room. Splitting divides only the pane in focus —
 * split right, then split that one down, and the first keeps its full
 * height. Pure: the Deck draws it, the tests drive it.
 */

type Leaf = { id: string }
export type Split = { dir: 'row' | 'col'; kids: Node[]; sizes: number[] }
export type Node = Leaf | Split

export const MAX_PANES = 4

export const isLeaf = (n: Node): n is Leaf => 'id' in n
const even = (k: number) => Array.from({ length: k }, () => 1 / k)

export function leaves(n: Node | null): string[] {
  if (!n) return []
  return isLeaf(n) ? [n.id] : n.kids.flatMap(leaves)
}

/** Only the terminals that still exist; a split left with one child is that child. */
export function prune(n: Node | null, keep: Set<string>): Node | null {
  if (!n) return null
  if (isLeaf(n)) return keep.has(n.id) ? n : null
  const pairs = n.kids.map((k, i) => [prune(k, keep), n.sizes[i] ?? 0] as const).filter(([k]) => k)
  if (!pairs.length) return null
  if (pairs.length === 1) return pairs[0]![0]
  const total = pairs.reduce((a, [, s]) => a + s, 0) || 1
  return { dir: n.dir, kids: pairs.map(([k]) => k!), sizes: pairs.map(([, s]) => (s || 1 / pairs.length) / total) }
}

/** `fresh` beside `target` (row: to its right, col: under it). */
export function splitAt(n: Node, target: string, fresh: string, dir: 'row' | 'col'): Node {
  if (isLeaf(n)) {
    return n.id === target ? { dir, kids: [n, { id: fresh }], sizes: [0.5, 0.5] } : n
  }
  const i = n.kids.findIndex((k) => isLeaf(k) && k.id === target)
  if (i >= 0 && n.dir === dir) {
    // Same direction: a sibling, taking half of the target's share.
    const kids = [...n.kids]
    kids.splice(i + 1, 0, { id: fresh })
    const sizes = [...n.sizes]
    const half = (sizes[i] ?? 1 / n.kids.length) / 2
    sizes.splice(i, 1, half, half)
    return { ...n, kids, sizes }
  }
  return { ...n, kids: n.kids.map((k) => splitAt(k, target, fresh, dir)) }
}

/** Another terminal in `target`'s place. */
export function replace(n: Node, target: string, other: string): Node {
  if (isLeaf(n)) return n.id === target ? { id: other } : n
  return { ...n, kids: n.kids.map((k) => replace(k, target, other)) }
}

export function remove(n: Node | null, target: string): Node | null {
  if (!n) return null
  return prune(n, new Set(leaves(n).filter((id) => id !== target)))
}

/** New shares for the split at `path` (child indexes from the root). */
export function resize(n: Node, path: number[], sizes: number[]): Node {
  if (isLeaf(n)) return n
  if (!path.length) return { ...n, sizes }
  const [i, ...rest] = path
  return { ...n, kids: n.kids.map((k, j) => (j === i ? resize(k, rest, sizes) : k)) }
}

export function parse(raw: unknown): Node | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  if (typeof r.id === 'string') return { id: r.id }
  if ((r.dir === 'row' || r.dir === 'col') && Array.isArray(r.kids)) {
    const kids = r.kids.map(parse).filter((k): k is Node => !!k)
    if (kids.length < 2) return kids[0] ?? null
    const sizes = Array.isArray(r.sizes) && r.sizes.length === kids.length ? r.sizes.map(Number) : even(kids.length)
    return { dir: r.dir, kids, sizes }
  }
  return null
}
