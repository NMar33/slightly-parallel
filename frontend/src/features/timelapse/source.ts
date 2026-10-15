/**
 * The film's source: one read of a project's whole life.
 *
 * `GET /api/timelapse` returns cards with their moves, the river of agent
 * sessions, and the marks worth holding on. Everything downstream is pure —
 * a frame is a function of this payload and a timestamp.
 */
import { getJson } from '../../lib/getJson'


export type Move = { at: string; status: string }

export type Card = {
  id: string
  title: string
  lane: string
  born: string
  assignee: string
  tags: string
  sprint: string
  status0: string
  moves: Move[]
  archived_at: string
  evidence: boolean
}

export type Session = {
  id: string
  agent_id: string
  start: string
  end: string
  turns_n: number
  l1: string
}

export type Mark = { at: string; kind: string; task_id: string; actor: string }

type Commit = {
  at: string
  add: number
  del: number
  files: number
  areas: Record<string, number>
  touched: string[]
}

export type GraphNode = {
  name: string
  path: string
  /** Index into `dirs`, or -1 for a file at the repository root. */
  dir: number
  area: string
  churn: number
  born: string
}

type GraphDir = {
  path: string
  name: string
  /** Index of the parent directory, or -1 at the top. */
  parent: number
  depth: number
}

/** `[from, to, weight, firstTogether]` — how often, and since when. */
type GraphEdge = [number, number, number, string]

export type Git = {
  commits: Commit[]
  areas: string[]
  graph: { nodes: GraphNode[]; edges: GraphEdge[]; dirs: GraphDir[] }
}

/** Totals for the closing card. Git fields are absent when git had nothing. */
export type Stats = {
  turns: number
  commits?: number
  lines_add?: number
  lines_del?: number
  files?: number
}

export type Source = {
  project: string
  span: { start: string; end: string }
  cards: Card[]
  sessions: Session[]
  marks: Mark[]
  stats: Stats
  git?: Git
}

export async function loadSource(project: string, signal?: AbortSignal): Promise<Source> {
  return await getJson<Source>(`/api/timelapse?project=${encodeURIComponent(project)}`, signal)
}
