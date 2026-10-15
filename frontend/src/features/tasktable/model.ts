/**
 * The task table's model: the rows (GET /api/stats/tasks, one per task), the
 * filter every version shares, and the query language it reads and writes.
 *
 * One filter state, three ways to set it (the versions): a toolbar and
 * builder, facets with counts, or a typed query. The state is written to
 * the address as its query text (`#tq=`), so a view is a link.
 */

import type { TaskStat } from '../stats/data'

import { t } from '../../i18n/scope/views'
export type Row = TaskStat & {
  priority: string
  assignee: string
  impact: string
  effort: string
  tags: string[]
  lane: string
  due: string
  starred: boolean
  archived: boolean
  age_days: number | null
  in_status_days: number | null
  status_since: string
  moves: number
  edits: number
  named_in: number
  activity: number[]
}

/** Lists: any of the values. Ranges: numbers. Flags: yes. Periods: days back. */
export interface Filter {
  q: string
  status: string[]
  priority: string[]
  assignee: string[]
  sprint: string[]
  tag: string[]
  agent: string[]
  closed: string[]
  ranges: Partial<Record<RangeKey, [number | null, number | null]>>
  is: Flag[]
  created: number | null
  done: number | null
}

export type ListKey = 'status' | 'priority' | 'assignee' | 'sprint' | 'tag' | 'agent' | 'closed'
export type RangeKey = 'messages' | 'minutes' | 'commits' | 'files' | 'age' | 'instatus' | 'lead' | 'moves' | 'chats'
export type Flag = 'open' | 'done' | 'stuck' | 'reopened' | 'starred' | 'exact' | 'estimated' | 'unworked' | 'archived'

export const EMPTY: Filter = {
  q: '', status: [], priority: [], assignee: [], sprint: [], tag: [], agent: [], closed: [],
  ranges: {}, is: [], created: null, done: null,
}

export const LIST_WORDS: Record<ListKey, string> = {
  status: t('Status'), priority: t('Priority'), assignee: t('Assignee'), sprint: t('Sprint'), tag: t('Tag'), agent: t('Agent'), closed: t('Closed'),
}
export const RANGE_WORDS: Record<RangeKey, string> = {
  messages: t('Messages'), minutes: t('Chat minutes'), commits: t('Commits'), files: t('Files'), age: t('Age (days)'),
  instatus: t('Days in status'), lead: t('Created → done (hours)'), moves: t('Moves'), chats: t('Chats'),
}
export const FLAG_WORDS: Record<Flag, string> = {
  open: t('open'), done: t('finished'), stuck: t('stuck 5+ days'), reopened: t('reopened'), starred: t('starred'),
  exact: t('exact stretch (#done)'), estimated: t('estimated stretch'), unworked: t('never in a chat'), archived: t('archived'),
}

/** The ranges that count whole things; the rest (days, hours) are measures. */
const WHOLE = new Set<RangeKey>(['messages', 'minutes', 'commits', 'files', 'moves', 'chats'])

export const isDone = (s: string) => ['done', 'done-archived'].includes(String(s).toLowerCase())

function rangeValue(r: Row, k: RangeKey): number | null {
  switch (k) {
    case 'messages': return r.stretch === 'none' ? null : r.messages
    case 'minutes': return r.stretch === 'none' ? null : r.minutes
    case 'commits': return r.commits
    case 'files': return r.files
    case 'age': return r.age_days
    case 'instatus': return r.in_status_days
    case 'lead': return r.lead_hours
    case 'moves': return r.moves
    case 'chats': return r.named_in
  }
}

function listValues(r: Row, k: ListKey): string[] {
  switch (k) {
    case 'status': return [r.status || 'unclassified']
    case 'priority': return [r.priority || '—']
    case 'assignee': return [r.assignee || '—']
    case 'sprint': return [r.sprint_id || '—']
    case 'tag': return r.tags.length ? r.tags : ['—']
    case 'agent': return r.agents.length ? r.agents : ['—']
    case 'closed': return [r.closed || '—']
  }
}

function hasFlag(r: Row, f: Flag): boolean {
  switch (f) {
    case 'open': return !isDone(r.status)
    case 'done': return isDone(r.status)
    case 'stuck': return !isDone(r.status) && (r.in_status_days ?? 0) >= 5
    case 'reopened': return r.reopened > 0
    case 'starred': return r.starred
    case 'exact': return r.stretch === 'done'
    case 'estimated': return r.stretch === 'estimated'
    case 'unworked': return r.stretch === 'none'
    case 'archived': return r.archived
  }
}

const within = (ts: string, days: number) => !!ts && Date.parse(ts.slice(0, 16)) >= Date.now() - days * 86400_000

/** Every cut but `skip` — the facets count with their own cut left out. */
export function apply(rows: Row[], f: Filter, skip?: ListKey): Row[] {
  const q = f.q.trim().toLowerCase()
  return rows.filter((r) => {
    if (q && !`${r.title} ${r.id}`.toLowerCase().includes(q)) return false
    for (const k of Object.keys(LIST_WORDS) as ListKey[]) {
      if (k === skip || !f[k].length) continue
      if (!listValues(r, k).some((v) => f[k].includes(v))) return false
    }
    for (const [k, [lo, hi]] of Object.entries(f.ranges) as Array<[RangeKey, [number | null, number | null]]>) {
      const v = rangeValue(r, k)
      if ((lo != null || hi != null) && v == null) return false
      if (lo != null && v! < lo) return false
      if (hi != null && v! > hi) return false
    }
    if (!f.is.every((x) => hasFlag(r, x))) return false
    if (f.created != null && !within(r.created, f.created)) return false
    if (f.done != null && !within(r.done_at, f.done)) return false
    return true
  })
}

/** Each value of a list with how many rows it would keep, the other cuts as they are. */
export function facet(rows: Row[], f: Filter, k: ListKey): Array<{ value: string; n: number }> {
  const base = apply(rows, f, k)
  const counts = new Map<string, number>()
  for (const r of rows) for (const v of listValues(r, k)) counts.set(v, counts.get(v) ?? 0)
  for (const r of base) for (const v of listValues(r, k)) counts.set(v, (counts.get(v) ?? 0) + 1)
  return [...counts.entries()].map(([value, n]) => ({ value, n })).sort((a, b) => b.n - a.n || a.value.localeCompare(b.value))
}

/* ------------------------------------------------------------ the query */

const quote = (v: string) => (/[\s,":]/.test(v) ? `"${v.replace(/"/g, '')}"` : v)
const RANGE_ORDER: RangeKey[] = ['messages', 'minutes', 'commits', 'files', 'age', 'instatus', 'lead', 'moves', 'chats']

/** The filter as query text: `status:doing,todo messages>5 is:stuck done:30d text`. */
export function toQuery(f: Filter): string {
  const parts: string[] = []
  for (const k of Object.keys(LIST_WORDS) as ListKey[]) if (f[k].length) parts.push(`${k}:${f[k].map(quote).join(',')}`)
  for (const k of RANGE_ORDER) {
    const r = f.ranges[k]
    if (!r) continue
    if (r[0] != null) parts.push(`${k}>=${r[0]}`)
    if (r[1] != null) parts.push(`${k}<=${r[1]}`)
  }
  for (const x of f.is) parts.push(`is:${x}`)
  if (f.created != null) parts.push(`created:${f.created}d`)
  if (f.done != null) parts.push(`done:${f.done}d`)
  if (f.q.trim()) parts.push(f.q.trim())
  return parts.join(' ')
}

const TOKEN = /(\w+)(:|>=|<=|>|<|=)("[^"]*"|[^\s]+)|("[^"]*"|\S+)/g

/** Query text back to a filter. Words it does not know are the free text. */
export function parseQuery(text: string): { filter: Filter; unknown: string[] } {
  const f: Filter = { ...EMPTY, ranges: {}, is: [], status: [], priority: [], assignee: [], sprint: [], tag: [], agent: [], closed: [] }
  const free: string[] = []
  const unknown: string[] = []
  for (const m of text.matchAll(TOKEN)) {
    const [, key, op, raw, word] = m
    if (word) { free.push(word.replace(/"/g, '')); continue }
    const k = key!.toLowerCase()
    const vals = raw!.split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/).map((v) => v.replace(/"/g, '')).filter(Boolean)
    if (op === ':' && k in LIST_WORDS) { f[k as ListKey] = [...new Set([...f[k as ListKey], ...vals])]; continue }
    if (op === ':' && k === 'is') {
      for (const v of vals) if (v in FLAG_WORDS) f.is.push(v as Flag); else unknown.push(`is:${v}`)
      continue
    }
    if (op === ':' && (k === 'created' || k === 'done')) {
      const n = parseInt(vals[0] ?? '', 10)
      if (Number.isFinite(n)) f[k] = n; else unknown.push(m[0])
      continue
    }
    if (k in RANGE_WORDS && op !== ':') {
      const n = Number(vals[0])
      if (!Number.isFinite(n)) { unknown.push(m[0]); continue }
      const cur = f.ranges[k as RangeKey] ?? [null, null]
      // A strict sign on a count reads as the next count (messages>5 is
      // messages>=6); on a measure in days or hours, the next hundredth —
      // lead>5 must keep a task at 5.5 hours.
      const step = WHOLE.has(k as RangeKey) ? 1 : 0.01
      if (op === '>=' || op === '>') cur[0] = op === '>' ? n + step : n
      else if (op === '<=' || op === '<') cur[1] = op === '<' ? n - step : n
      else { cur[0] = n; cur[1] = n }
      f.ranges[k as RangeKey] = cur
      continue
    }
    unknown.push(m[0])
  }
  f.q = free.join(' ')
  return { filter: f, unknown }
}

/** The views one click away. */
export const VIEWS: Array<{ id: string; name: string; query: string; hint: string }> = [
  { id: 'open', name: 'Open', query: 'is:open', hint: t('everything not finished') },
  { id: 'moving', name: 'Moving', query: 'status:doing,review', hint: t('in doing or in review') },
  { id: 'stuck', name: 'Stuck', query: 'is:stuck', hint: t('open and unmoved for five days or more') },
  { id: 'finished', name: t('Finished · 30 days'), query: 'is:done done:30d', hint: t('closed in the last month') },
  { id: 'heavy', name: 'Heavy', query: 'messages>=5', hint: t('five messages or more') },
  { id: 'reopened', name: 'Reopened', query: 'is:reopened', hint: t('moved back out of done') },
  { id: 'all', name: 'All', query: '', hint: t('every task') },
]
