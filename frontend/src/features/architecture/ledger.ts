import { getJson } from '../../lib/getJson'
import { useMemo } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'

import type { Change, ScanAnswer, State } from './state'
import { t } from '../../i18n/scope/system'
import { dayMonth } from '../../lib/months'

/**
 * The architecture ledger, folded into the things pages read.
 *
 * The API gives a stream of typed changes (op · type · name · paths ·
 * fields) hung off the scans that produced them. Everything a page wants
 * — what stands, what each type holds, how the repo is covered, how much
 * of the history was ever answered — is a fold of that stream, computed
 * here once so no page invents its own arithmetic.
 *
 * The vocabulary (eight groups, twenty-four types) arrives with the
 * payload: the server owns it, and an empty type is as real a fact as a
 * full one — nobody has declared a queue, so the cell stands empty.
 */

export type { Change, ScanAnswer,  } from './state'

/** One colour per group, fixed order, from the validated lane palette. */
const GROUP_TONE: Record<string, string> = {
  does: 'var(--lane-3)',
  owes: 'var(--lane-2)',
  runs: 'var(--lane-1)',
  stores: 'var(--lane-5)',
  talks: 'var(--lane-6)',
  'built with': 'var(--lane-4)',
  faces: 'var(--lane-7)',
  holds: 'var(--lane-8)',
}

export const OP_GLYPH: Record<string, string> = { add: '+', change: '~', remove: '−' }
export const OP_TONE: Record<string, string> = {
  add: 'var(--status-green)',
  change: 'var(--status-amber)',
  remove: 'var(--status-red)',
}

export const groupTone = (group: string) => GROUP_TONE[group] ?? 'var(--text-tertiary)'

/** A named thing, folded from every change that spoke about it. */
export interface Entity {
  /** `type:name` — the identity a change addresses. */
  key: string
  type: string
  group: string
  name: string
  /** Every path any change gave it, most recent first. */
  paths: string[]
  /** The latest note that said anything. */
  note: string
  /** The type's own fields, latest value per field. */
  fields: Record<string, string>
  task: string
  /** Oldest first. */
  changes: Change[]
  first: Change
  last: Change
  /** Its last word was `remove`. */
  gone: boolean
  scans: string[]
}

interface TypeCell {
  type: string
  group: string
  entities: Entity[]
  live: number
  gone: number
  changes: number
}

interface GroupBlock {
  group: string
  types: TypeCell[]
  live: number
  changes: number
}

export interface PathNode {
  name: string
  path: string
  kind: 'dir' | 'file'
  children: PathNode[]
  /** Entities that named this exact path. */
  entities: Entity[]
  /** Symbols named after a colon on this file. */
  symbols: string[]
  /** Entities at or under this node. */
  total: number
  /** The groups present at or under this node, for the colour bar. */
  groups: Record<string, number>
}

interface Day {
  date: string
  add: number
  change: number
  remove: number
  total: number
}

export interface Model {
  project: string
  /** The vocabulary, in the server's order. */
  groups: string[]
  typeOf: Record<string, string>
  entities: Entity[]
  byKey: Map<string, Entity>
  blocks: GroupBlock[]
  cells: TypeCell[]
  scans: ScanAnswer[]
  loose: Change[]
  owes: Change[]
  days: Day[]
  tree: PathNode
  paths: number
  answered: number
  /** The newest scan that carries an answer, if any. */
  lastAnswer: ScanAnswer | null
  /** The newest change of any kind. */
  lastChange: Change | null
  totalChanges: number
}

const stamp = (c: { created_date: string; created_time: string; id: string }) =>
  `${c.created_date} ${c.created_time} ${c.id}`

/** `dir/file.py:Symbol` → `['dir/file.py', 'Symbol']`; no colon → no symbol. */
export function splitSymbol(entry: string): [string, string] {
  const i = entry.lastIndexOf(':')
  if (i <= 0) return [entry, '']
  const tail = entry.slice(i + 1)
  if (!tail || tail.includes('/')) return [entry, '']
  return [entry.slice(0, i), tail]
}

function foldEntities(changes: Change[], typeOf: Record<string, string>): Entity[] {
  const by = new Map<string, Entity>()
  for (const c of [...changes].sort((a, b) => stamp(a).localeCompare(stamp(b)))) {
    const key = `${c.type}:${c.name}`
    const e = by.get(key)
    if (!e) {
      by.set(key, {
        key,
        type: c.type,
        group: c.group || typeOf[c.type] || '',
        name: c.name,
        paths: [...c.path],
        note: c.note,
        fields: { ...c.fields },
        task: c.task,
        changes: [c],
        first: c,
        last: c,
        gone: c.op === 'remove',
        scans: c.trigger_id ? [c.trigger_id] : [],
      })
      continue
    }
    e.changes.push(c)
    e.last = c
    e.gone = c.op === 'remove'
    if (c.note) e.note = c.note
    if (c.task) e.task = c.task
    e.fields = { ...e.fields, ...c.fields }
    // Newest paths first, without losing the ones an older change named.
    e.paths = [...c.path, ...e.paths.filter((p) => !c.path.includes(p))]
    if (c.trigger_id && !e.scans.includes(c.trigger_id)) e.scans.push(c.trigger_id)
  }
  return [...by.values()]
}

function buildTree(entities: Entity[]): { tree: PathNode; paths: number } {
  const root: PathNode = { name: '', path: '', kind: 'dir', children: [], entities: [], symbols: [], total: 0, groups: {} }
  const seen = new Set<string>()
  for (const e of entities) {
    for (const raw of e.paths) {
      const [file, symbol] = splitSymbol(raw.trim().replace(/\/+$/, ''))
      if (!file) continue
      seen.add(file)
      const segs = file.split('/').filter(Boolean)
      let node = root
      segs.forEach((seg, i) => {
        const last = i === segs.length - 1
        const path = segs.slice(0, i + 1).join('/')
        let next = node.children.find((c) => c.name === seg)
        if (!next) {
          next = {
            name: seg,
            path,
            // A leaf with a dot is a file; anything else is a folder.
            kind: last && seg.includes('.') ? 'file' : 'dir',
            children: [], entities: [], symbols: [], total: 0, groups: {},
          }
          node.children.push(next)
        }
        if (last) {
          if (!next.entities.includes(e)) next.entities.push(e)
          if (symbol && !next.symbols.includes(symbol)) next.symbols.push(symbol)
        }
        node = next
      })
    }
  }
  const count = (n: PathNode): number => {
    const own = new Set(n.entities.map((e) => e.key))
    for (const c of n.children) {
      count(c)
      for (const e of c.entities) own.add(e.key)
      for (const [g, v] of Object.entries(c.groups)) n.groups[g] = (n.groups[g] ?? 0) + v
    }
    for (const e of n.entities) n.groups[e.group] = (n.groups[e.group] ?? 0) + 1
    n.children.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === 'dir' ? -1 : 1))
    n.total = own.size + n.children.reduce((s, c) => s + c.total, 0) - n.children.reduce((s, c) => s + c.entities.filter((e) => own.has(e.key)).length, 0)
    return n.total
  }
  count(root)
  return { tree: root, paths: seen.size }
}

function buildModel(state: State): Model {
  const groups = Object.keys(state.groups)
  const typeOf: Record<string, string> = {}
  for (const [g, types] of Object.entries(state.groups)) for (const t of types) typeOf[t] = g

  const all = [...state.scans.flatMap((s) => s.changes), ...state.loose]
  const entities = foldEntities(all, typeOf).sort((a, b) => stamp(b.last).localeCompare(stamp(a.last)))
  const byKey = new Map(entities.map((e) => [e.key, e]))

  const cells: TypeCell[] = []
  const blocks: GroupBlock[] = groups.map((group) => {
    const types = (state.groups[group] ?? []).map((type) => {
      const mine = entities.filter((e) => e.type === type)
      const cell: TypeCell = {
        type, group, entities: mine,
        live: mine.filter((e) => !e.gone).length,
        gone: mine.filter((e) => e.gone).length,
        changes: mine.reduce((n, e) => n + e.changes.length, 0),
      }
      cells.push(cell)
      return cell
    })
    return {
      group, types,
      live: types.reduce((n, t) => n + t.live, 0),
      changes: types.reduce((n, t) => n + t.changes, 0),
    }
  })

  const dayMap = new Map<string, Day>()
  for (const c of all) {
    const d = dayMap.get(c.created_date) ?? { date: c.created_date, add: 0, change: 0, remove: 0, total: 0 }
    if (c.op === 'add' || c.op === 'change' || c.op === 'remove') d[c.op] += 1
    d.total += 1
    dayMap.set(c.created_date, d)
  }
  const days = [...dayMap.values()].sort((a, b) => a.date.localeCompare(b.date))

  const { tree, paths } = buildTree(entities)
  const sorted = [...all].sort((a, b) => stamp(b).localeCompare(stamp(a)))

  return {
    project: state.project,
    groups, typeOf, entities, byKey, blocks, cells,
    scans: state.scans,
    loose: state.loose,
    owes: state.owes,
    days, tree, paths,
    answered: state.scans.filter((s) => s.answered).length,
    lastAnswer: state.scans.find((s) => s.answered) ?? null,
    lastChange: sorted[0] ?? null,
    totalChanges: state.total_changes,
  }
}

async function fetchState(project: string, signal?: AbortSignal): Promise<State> {
  return getJson<State>(`/api/architecture/state?project=${encodeURIComponent(project)}&limit=200`, signal)
}

/** The ledger of one project, folded. */
export function useLedger(project: string) {
  const q = useQuery({
    queryKey: ['architecture', 'state', project],
    queryFn: ({ signal }) => fetchState(project, signal),
    enabled: Boolean(project),
    staleTime: 10_000,
  })
  const model = useMemo(() => (q.data ? buildModel(q.data) : null), [q.data])
  return { model, loading: q.isLoading, error: q.isError ? String(q.error) : null }
}

/** The ledgers' answers; recombined only when one of the reads changes. */
const ledgerReads = (results: Array<{ data?: State; isLoading: boolean; isError: boolean }>) => ({
  data: results.map((r) => r.data),
  loading: results.some((r) => r.isLoading),
  error: results.some((r) => r.isError),
})

/**
 * Every project's ledger at once — so a page can open on the one that
 * has something to read instead of the first one alphabetically, and
 * say in the picker which projects have a ledger at all.
 */
export function useLedgers(codes: string[]) {
  const reads = useQueries({
    queries: codes.map((code) => ({
      queryKey: ['architecture', 'state', code],
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchState(code, signal),
      staleTime: 10_000,
    })),
    combine: ledgerReads,
  })
  // The codes by value: a caller's new array of the same codes is no change.
  const codeKey = codes.join('|')
  const models = useMemo(() => {
    const map = new Map<string, Model>()
    const list = codeKey ? codeKey.split('|') : []
    list.forEach((code, i) => {
      const data = reads.data[i]
      if (data) map.set(code, buildModel(data))
    })
    return map
  }, [codeKey, reads.data])
  /** The project with the most changes — where a reader should land. */
  const busiest = [...models.entries()]
    .sort((a, b) => b[1].totalChanges - a[1].totalChanges)[0]?.[0] ?? ''
  return {
    models,
    busiest,
    loading: reads.loading,
    error: reads.error ? t('The changes could not be read') : null,
  }
}

/** `2609-01` → `1 Sep`; anything else is passed through. */
export function fmtDate(d: string): string {
  const m = /^(\d{2})(\d{2})-(\d{2})$/.exec(d)
  if (!m) return d
  return dayMonth(new Date(2000 + Number(m[1]), Number(m[2]) - 1, Number(m[3])))
}
