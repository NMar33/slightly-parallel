import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'

import { type Entry, type Payload, type Row, buildRows } from './rows'

/**
 * The fleet read: every project's file activity in one payload.
 *
 * The project tab answers "what happened to this codebase". The lens page
 * has to answer the question no single project can — where the work went,
 * which repo is being rewritten and which has gone quiet, and what the last
 * checkpoint anywhere actually shipped. Same endpoint, no project filter.
 */

export type FleetEntry = Entry & { project: string }

/** Payload with the project stamped on every checkpoint, which the
 *  unfiltered endpoint always does. */
export type FleetPayload = Omit<Payload, 'entries'> & { entries: FleetEntry[] }

type Fleet = {
  data: FleetPayload | null
  err: string | null
}

export function useFleet(): Fleet {
  // The project tab's key with no project: the same area (scans) moves it.
  const q = useQuery({
    queryKey: ['lens', 'files', 'heatmap', ''],
    queryFn: ({ signal }) => getJson<FleetPayload>('/api/files/heatmap?limit_files=500', signal),
  })
  return {
    data: q.data ?? null,
    err: q.error ? String((q.error as Error).message || q.error) : null,
  }
}

/** What one project looks like, summed from its files and its checkpoints. */
type ProjectStat = {
  project: string
  files: number
  churn: number
  add: number
  del: number
  checkpoints: number
  lastDate: string
  topImportance: number
  /** Where its churn concentrated: the two heaviest folders. */
  hotFolders: Array<{ folder: string; churn: number }>
  /** The files themselves, ranked as the page asks. */
  rows: Row[]
}

const folderOf = (path: string): string => {
  const bits = path.split('/')
  return bits.length <= 1 ? '(root)' : bits.slice(0, Math.min(3, bits.length - 1)).join('/')
}

export function byProject(data: NonNullable<Fleet['data']>, weight: number): ProjectStat[] {
  const rows = buildRows(data, weight)
  const groups = new Map<string, Row[]>()
  for (const r of rows) {
    const key = String((r as Row & { project?: string }).project || 'unknown')
    const list = groups.get(key) ?? []
    list.push(r)
    groups.set(key, list)
  }
  return [...groups.entries()].map(([project, list]) => {
    const folders = new Map<string, number>()
    for (const r of list) folders.set(folderOf(r.path), (folders.get(folderOf(r.path)) ?? 0) + r.churn)
    const entries = data.entries.filter((e) => e.project === project)
    return {
      project,
      files: list.length,
      churn: list.reduce((a, r) => a + r.churn, 0),
      add: list.reduce((a, r) => a + r.lines_add, 0),
      del: list.reduce((a, r) => a + r.lines_del, 0),
      checkpoints: entries.length,
      lastDate: entries.reduce((a, e) => (e.date > a ? e.date : a), ''),
      topImportance: Math.max(0, ...list.map((r) => r.semantic_score ?? 0)),
      hotFolders: [...folders.entries()]
        .map(([folder, churn]) => ({ folder, churn }))
        .sort((a, b) => b.churn - a.churn)
        .slice(0, 2),
      rows: list,
    }
  }).sort((a, b) => b.churn - a.churn)
}

/** The paths one checkpoint touched, with what the agent said about each. */
export function pathsOf(data: NonNullable<Fleet['data']>, entryId: string) {
  const out: Array<{ path: string; add: number; del: number; why: string; action: string; score: number }> = []
  for (const [key, cell] of Object.entries(data.cells)) {
    const [path, id] = key.split('||')
    if (id !== entryId || !path) continue
    out.push({
      path,
      add: cell.lines_add,
      del: cell.lines_del,
      why: cell.why ?? '',
      action: cell.action ?? 'modified',
      score: cell.semantic_score ?? 0,
    })
  }
  return out.sort((a, b) => (b.score - a.score) || (b.add + b.del - a.add - a.del))
}

/* ---------------------------------------------------------------------------
 * One file, everything the ledger knows about it.
 * ------------------------------------------------------------------------- */

export type Dossier = {
  path: string
  project: string
  touches: number
  checkpoints: number
  add: number
  del: number
  score: number
  tags: string[]
  first: string
  last: string
  /** Every sentence written about it, newest first. */
  story: Array<{ date: string; time: string; agent: string; why: string; add: number; del: number; score: number; action: string; entryId: string; l1: string }>
  /** Files that appear in the same checkpoints — coupling by behaviour. */
  travels: Array<{ path: string; n: number; of: number }>
  /** Who touched it, and how often. */
  agents: Array<{ agent: string; n: number }>
  /** Where it sits in its project by lines changed. */
  rankChurn: number
  rankOf: number
}

export function fileDossier(data: FleetPayload, path: string): Dossier | null {
  const file = data.files.find((f) => f.path === path)
  const mine = data.entries.filter((e) => data.cells[`${path}||${e.id}`])
  if (!file || mine.length === 0) return null

  // Which paths ride along in the same checkpoints. 8/8 means it has never
  // once changed alone, which is a stronger claim than any import graph.
  const together = new Map<string, number>()
  for (const e of mine) {
    for (const key of Object.keys(data.cells)) {
      const [p, id] = key.split('||')
      if (id !== e.id || !p || p === path) continue
      together.set(p, (together.get(p) ?? 0) + 1)
    }
  }

  const agents = new Map<string, number>()
  for (const e of mine) agents.set(e.agent_id, (agents.get(e.agent_id) ?? 0) + 1)

  const sorted = [...mine].sort((a, b) => `${b.date} ${b.time}`.localeCompare(`${a.date} ${a.time}`))
  const project = String((file as typeof file & { project?: string }).project || '')
  const peers = data.files
    .filter((f) => String((f as typeof f & { project?: string }).project || '') === project)
    .sort((a, b) => (b.lines_add + b.lines_del) - (a.lines_add + a.lines_del))

  return {
    path,
    project,
    touches: file.total,
    checkpoints: mine.length,
    add: file.lines_add,
    del: file.lines_del,
    score: file.semantic_score ?? 0,
    tags: file.tags ?? [],
    first: sorted[sorted.length - 1]?.date ?? '',
    last: sorted[0]?.date ?? '',
    story: sorted.map((e) => {
      const cell = data.cells[`${path}||${e.id}`]!
      return {
        date: e.date, time: e.time, agent: e.agent_id, why: cell.why ?? '',
        add: cell.lines_add, del: cell.lines_del, score: cell.semantic_score ?? 0,
        action: cell.action ?? 'modified', entryId: e.id, l1: e.l1,
      }
    }),
    travels: [...together.entries()]
      .map(([p, n]) => ({ path: p, n, of: mine.length }))
      .sort((a, b) => b.n - a.n)
      .slice(0, 6),
    agents: [...agents.entries()].map(([agent, n]) => ({ agent, n })).sort((a, b) => b.n - a.n),
    rankChurn: peers.findIndex((f) => f.path === path) + 1,
    rankOf: peers.length,
  }
}
