/**
 * Pure layout maths for the agent timeline: chart constants, date parsing,
 * lane / edge / group building, the time domain, tick picking, link
 * geometry (bezier + midpoint) and per-lane mark bucketing.
 * No React here — everything is a plain function of its inputs.
 */

import { max as maxOf, min as minOf } from 'd3-array'
import { timeMonday } from 'd3-time'

import { parseYYMMDD } from '../../utils/dateUtils'
import type {
  AgentMeta,
  DrawnLink,
  Edge,
  GroupBand,
  Lane,
  LaneMark,
  TimelineLink,
  XScale,
} from './types'

/** SVG stroke-dasharray per link style — one place, so legends match. */
export const LINK_DASH: Record<string, string | undefined> = {
  solid: undefined,
  dashed: '6 4',
  dotted: '1.5 3.5',
}

// ---------------------------------------------------------------------------
// Layout constants — kept here (not tokens.css) because they are chart-local
// invariants, not a design-system commitment.
// ---------------------------------------------------------------------------

export const MARGIN = { top: 32, right: 24, bottom: 28, left: 160 } as const
/** The label column grows when ✎ / 👁 share it with the names. */
export const LEFT_WITH_CONTROLS = 220
export const ROW_HEIGHT = 28
/** Drawn marks (renderMark) closer than this merge into one. */
const MARK_GAP = 22
export const BAR_HEIGHT = 16
export const BAR_RADIUS = 4
export const MIN_INNER_HEIGHT = 180
export const DEFAULT_WIDTH = 960 // fallback when ResizeObserver hasn't measured yet
const LANE_PALETTE = [
  'var(--lane-1)',
  'var(--lane-2)',
  'var(--lane-3)',
  'var(--lane-4)',
  'var(--lane-5)',
  'var(--lane-6)',
  'var(--lane-7)',
  'var(--lane-8)',
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Tolerant date parser. Accepts YYMM-DD, YYMM-DDTHH:MM:SS, ISO strings,
 * or empty. Returns null on failure so we can gracefully drop broken rows.
 */
export function safeParseDate(s: string | undefined | null): Date | null {
  if (!s) return null
  try {
    return parseYYMMDD(s)
  } catch {
    // Fall back to ISO / native parse for `last_active` timestamps that
    // came in as e.g. "2026-08-06T14:30:00Z" (post-migrate v2 format).
    const d = new Date(s)
    return isNaN(d.getTime()) ? null : d
  }
}

/**
 * Build lanes from the raw agents list — filters unparseable rows, sorts by
 * creation, ensures last_active ≥ created (some agents log only creation).
 * Grouped agents are pulled together at the position of the group's first
 * member, so a group reads as one block of lanes.
 */
function orderAgents<T extends { agent_group?: string; created_date: string }>(
  rows: T[],
  createdOf: (r: T) => number,
): T[] {
  const sorted = rows.slice().sort((x, y) => createdOf(x) - createdOf(y))
  const out: T[] = []
  const placed = new Set<string>()
  for (const r of sorted) {
    const g = r.agent_group || ''
    if (!g) {
      out.push(r)
      continue
    }
    if (placed.has(g)) continue
    placed.add(g)
    for (const m of sorted) if ((m.agent_group || '') === g) out.push(m)
  }
  return out
}

export function buildLanes(agents: AgentMeta[]): Lane[] {
  const rows: Lane[] = []
  for (const a of agents) {
    const created = safeParseDate(a.created_date)
    if (!created) continue
    const lastActive = safeParseDate(a.last_active) ?? created
    const effectiveLast =
      lastActive.getTime() < created.getTime() ? created : lastActive
    rows.push({
      agent: a,
      index: 0, // filled after sort
      created,
      lastActive: effectiveLast,
      color: '', // filled after sort
    })
  }
  const ordered = orderAgents(
    rows.map((r) => ({ ...r, agent_group: r.agent.agent_group, created_date: r.agent.created_date })),
    (r) => r.created.getTime(),
  )
  ordered.forEach((r, i) => {
    r.index = i
    r.color = LANE_PALETTE[i % LANE_PALETTE.length]
  })
  return ordered.map(({ agent, index, created, lastActive, color }) => ({ agent, index, created, lastActive, color }))
}

/** Build edges only when the parent is also in the visible set. */
export function buildEdges(lanes: Lane[]): Edge[] {
  const byId = new Map(lanes.map((l) => [l.agent.agent_id, l]))
  const edges: Edge[] = []
  for (const child of lanes) {
    const pid = child.agent.parent_agent_id
    if (!pid) continue
    const parent = byId.get(pid)
    if (!parent) continue
    edges.push({
      fromIndex: parent.index,
      toIndex: child.index,
      fromDate: parent.lastActive,
      toDate: child.created,
      color: parent.color,
    })
  }
  return edges
}

/** Contiguous runs of one group → one bracket each. */
export function buildGroups(lanes: Lane[]): GroupBand[] {
  const out: GroupBand[] = []
  for (const l of lanes) {
    const g = l.agent.agent_group || ''
    if (!g) continue
    const cur = out[out.length - 1]
    if (cur && cur.name === g && cur.last === l.index - 1) cur.last = l.index
    else out.push({ name: g, first: l.index, last: l.index, color: l.color })
  }
  return out
}

/**
 * Cubic-bezier path from (x1,y1) to (x2,y2) with horizontal handles.
 * Handle length = 40% of the horizontal delta (min 24px so verticals still curve).
 */
function handleLength(x1: number, x2: number): number {
  return Math.max(24, Math.abs(x2 - x1) * 0.4)
}

export function bezierPath(x1: number, y1: number, x2: number, y2: number): string {
  const dx = handleLength(x1, x2)
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

/** The point at t=0.5 of the same cubic — where a link's dot sits. */
export function bezierMidpoint(x1: number, y1: number, x2: number, y2: number): [number, number] {
  const dx = handleLength(x1, x2)
  // B(½) = (P0 + 3·P1 + 3·P2 + P3) / 8
  const mx = (x1 + 3 * (x1 + dx) + 3 * (x2 - dx) + x2) / 8
  const my = (y1 + 3 * y1 + 3 * y2 + y2) / 8
  return [mx, my]
}

/** Truncate long agent names for the left axis without breaking Cyrillic. */
export function truncate(s: string, max = 20): string {
  if (s.length <= max) return s
  // Array-based slice is code-point safe (handles surrogate pairs; Cyrillic
  // is BMP so plain slice would suffice, but this is future-proof).
  return Array.from(s).slice(0, max - 1).join('') + '…'
}

function clampDate(d: Date, lo: Date, hi: Date): Date {
  const t = Math.min(Math.max(d.getTime(), lo.getTime()), hi.getTime())
  return new Date(t)
}

// ---------------------------------------------------------------------------
// Domain, ticks, links, marks — the bodies of the component's memos
// ---------------------------------------------------------------------------

/** Full time extent of the lanes, padded a day and always including today. */
export function fullDomainOf(lanes: Lane[]): [Date, Date] | null {
  if (lanes.length === 0) return null
  const min = minOf(lanes, (l) => l.created) as Date
  const max = maxOf(lanes, (l) => l.lastActive) as Date
  // Pad by 1 day at each end + always include TODAY so the marker is visible.
  const today = new Date()
  const lo = new Date(Math.min(min.getTime(), today.getTime()) - 86_400_000)
  const hi = new Date(Math.max(max.getTime(), today.getTime()) + 86_400_000)
  return [lo, hi]
}

/** How many date ticks fit the chart's width. */
export function tickCountFor(innerWidth: number): number {
  return Math.min(10, Math.max(4, Math.floor(innerWidth / 100)))
}

/** Week grid: every Monday between domain endpoints (only when span reasonable). */
export function weekTicksFor(domain: [Date, Date] | null, spanDays: number): Date[] {
  if (!domain || spanDays > 400) return []
  return timeMonday.range(timeMonday.floor(domain[0]), domain[1])
}

/** Resolved geometry for every drawable link. */
export function resolveLinks(
  links: TimelineLink[] | undefined,
  laneById: Map<string, Lane>,
  xScale: XScale,
  yFor: (index: number) => number,
): DrawnLink[] {
  return (links ?? []).flatMap((lk) => {
    const from = laneById.get(lk.from_id)
    const to = laneById.get(lk.to_id)
    if (!from || !to) return []
    const toDate = safeParseDate(lk.to_at) ?? to.created
    const fromDate = safeParseDate(lk.from_at) ?? clampDate(toDate, from.created, from.lastActive)
    const x1 = xScale(fromDate)
    const y1 = yFor(from.index)
    const x2 = xScale(toDate)
    const y2 = yFor(to.index)
    const [mx, my] = bezierMidpoint(x1, y1, x2, y2)
    return [{ link: lk, from, to, x1, y1, x2, y2, mx, my }]
  })
}

/** Per-lane hour buckets (merged when marks are drawn), keyed by agent id. */
export function bucketMarks(
  marks: Record<string, LaneMark[]>,
  lanes: Lane[],
  mergeClose: boolean,
  xScale: XScale,
): Map<string, Array<[number, LaneMark[]]>> {
  const out = new Map<string, Array<[number, LaneMark[]]>>()
  for (const l of lanes) {
    const list = marks[l.agent.agent_id] ?? []
    if (list.length === 0) continue
    const buckets = new Map<number, LaneMark[]>()
    for (const mk of list) {
      const t = Date.parse(mk.at)
      if (!Number.isFinite(t)) continue
      const key = Math.floor(t / 3600e3)
      const b = buckets.get(key) ?? []
      b.push(mk)
      buckets.set(key, b)
    }
    // A drawn mark is wider than an hour at a month's zoom: hours
    // closer than one mark merge, so marks never pile up.
    let entries = [...buckets.entries()].sort((a, b) => a[0] - b[0])
    if (mergeClose) {
      const merged: Array<[number, LaneMark[]]> = []
      let lastX = -Infinity
      for (const [key, group] of entries) {
        const x = xScale(new Date(Date.parse(group[0]!.at)))
        const prev = merged[merged.length - 1]
        if (prev && x - lastX < MARK_GAP) prev[1] = [...prev[1], ...group]
        else { merged.push([key, group]); lastX = x }
      }
      entries = merged
    }
    out.set(l.agent.agent_id, entries)
  }
  return out
}
