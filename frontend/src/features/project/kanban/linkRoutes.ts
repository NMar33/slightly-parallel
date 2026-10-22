/**
 * Where the lines between linked cards go. Pure: boxes in, paths out, so
 * the rules are tested without a browser.
 *
 * - Cards in different columns: from the side facing the other card to the
 *   side facing back, a horizontal S-curve.
 * - Cards in one column: both ends on the same side, a bracket that bulges
 *   out beside the column. Right side unless the left is emptier (fewer
 *   lines already leave there) or the right runs out of board. Longer
 *   brackets bulge further, so nested ones do not cross.
 * - Several lines on one side of a card get their own ports, spread along
 *   the side in the order of the cards they go to, so lines do not overlap
 *   and two links between the same pair stay two lines.
 * - A link whose other card is not on the board (folded column, hidden
 *   lane, closed stack, another project) keeps a short stub with an open
 *   end, so a link is never silently missing.
 */

import type { LinkKind, TaskLink } from './model'

export type Box = { left: number; top: number; right: number; bottom: number }
type Side = 'l' | 'r'
export type Route = {
  id: string
  kind: LinkKind
  from_id: string
  to_id: string
  d: string
  /** Set when one card is not on the board: which end is missing. */
  missing?: 'from' | 'to'
}

const STUB = 18
const BULGE_MIN = 16
const BULGE_MAX = 56

const cx = (b: Box) => (b.left + b.right) / 2
const cy = (b: Box) => (b.top + b.bottom) / 2

/** Same column: the boxes overlap over half the narrower one's width. */
export function sameColumn(a: Box, b: Box): boolean {
  const overlap = Math.min(a.right, b.right) - Math.max(a.left, b.left)
  return overlap > 0.5 * Math.min(a.right - a.left, b.right - b.left)
}

type End = { card: string; side: Side; other: number; key: string; y?: number }

export function routeLinks(
  links: TaskLink[],
  boxes: Map<string, Box>,
  bounds: { left: number; right: number },
): Route[] {
  type Plan = { link: TaskLink; a?: End; b?: End; same: boolean }
  const plans: Plan[] = []
  const used = new Map<string, number>() // `${card}:${side}` → lines leaving there
  const bump = (card: string, side: Side) => used.set(`${card}:${side}`, (used.get(`${card}:${side}`) ?? 0) + 1)

  // First pass: sides of the lines whose sides are forced.
  for (const link of links) {
    const A = boxes.get(link.from_id), B = boxes.get(link.to_id)
    if (!A && !B) continue
    if (!A || !B) {
      const box = (A ?? B)!, card = A ? link.from_id : link.to_id
      const side: Side = box.right + STUB + 8 > bounds.right ? 'l' : 'r'
      bump(card, side)
      const end: End = { card, side, other: cy(box), key: link.id }
      plans.push({ link, same: false, ...(A ? { a: end } : { b: end }) })
      continue
    }
    if (sameColumn(A, B)) { plans.push({ link, same: true }); continue }
    const right = cx(B) >= cx(A)
    const a: End = { card: link.from_id, side: right ? 'r' : 'l', other: cy(B), key: link.id }
    const b: End = { card: link.to_id, side: right ? 'l' : 'r', other: cy(A), key: link.id }
    bump(a.card, a.side); bump(b.card, b.side)
    plans.push({ link, a, b, same: false })
  }
  // Second pass: one column — the emptier side, as long as it fits.
  for (const p of plans) {
    if (!p.same) continue
    const A = boxes.get(p.link.from_id)!, B = boxes.get(p.link.to_id)!
    const load = (s: Side) => (used.get(`${p.link.from_id}:${s}`) ?? 0) + (used.get(`${p.link.to_id}:${s}`) ?? 0)
    let side: Side = load('l') < load('r') ? 'l' : 'r'
    const room = BULGE_MAX / 2
    if (side === 'r' && Math.max(A.right, B.right) + room > bounds.right) side = 'l'
    else if (side === 'l' && Math.min(A.left, B.left) - room < bounds.left) side = 'r'
    p.a = { card: p.link.from_id, side, other: cy(B), key: p.link.id }
    p.b = { card: p.link.to_id, side, other: cy(A), key: p.link.id }
    bump(p.link.from_id, side); bump(p.link.to_id, side)
  }

  // Ports: every end on one side of one card gets its own spot, in the
  // order of where its line goes, so lines leave without crossing.
  const bySide = new Map<string, End[]>()
  for (const p of plans) {
    for (const e of [p.a, p.b]) {
      if (!e) continue
      const k = `${e.card}:${e.side}`
      ;(bySide.get(k) ?? bySide.set(k, []).get(k)!).push(e)
    }
  }
  for (const ends of bySide.values()) {
    ends.sort((x, y) => x.other - y.other || (x.key < y.key ? -1 : x.key > y.key ? 1 : 0))
    const box = boxes.get(ends[0]!.card)!
    const h = box.bottom - box.top
    const pad = Math.min(8, h / 4)
    ends.forEach((e, i) => { e.y = box.top + pad + ((h - 2 * pad) * (i + 1)) / (ends.length + 1) })
  }

  const x = (e: End) => { const b = boxes.get(e.card)!; return e.side === 'r' ? b.right : b.left }
  const dir = (s: Side) => (s === 'r' ? 1 : -1)
  const n = (v: number) => Math.round(v * 10) / 10
  const out: Route[] = []
  for (const p of plans) {
    const base = { id: p.link.id, kind: p.link.kind, from_id: p.link.from_id, to_id: p.link.to_id }
    if (!p.a || !p.b) {
      const e = (p.a ?? p.b)!
      const x1 = x(e), y = e.y!
      out.push({ ...base, missing: p.a ? 'to' : 'from', d: `M ${n(x1)} ${n(y)} L ${n(x1 + dir(e.side) * STUB)} ${n(y)}` })
      continue
    }
    const x1 = x(p.a), y1 = p.a.y!, x2 = x(p.b), y2 = p.b.y!
    let d: string
    if (p.same) {
      const k = dir(p.a.side)
      const bulge = Math.min(BULGE_MAX, Math.max(BULGE_MIN, BULGE_MIN + Math.abs(y2 - y1) * 0.12))
      d = `M ${n(x1)} ${n(y1)} C ${n(x1 + k * bulge)} ${n(y1)}, ${n(x2 + k * bulge)} ${n(y2)}, ${n(x2)} ${n(y2)}`
    } else {
      const dx = Math.max(24, Math.abs(x2 - x1) / 2)
      d = `M ${n(x1)} ${n(y1)} C ${n(x1 + dir(p.a.side) * dx)} ${n(y1)}, ${n(x2 + dir(p.b.side) * dx)} ${n(y2)}, ${n(x2)} ${n(y2)}`
    }
    out.push({ ...base, d })
  }
  return out
}
