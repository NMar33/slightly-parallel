/**
 * Typed reads of the snapshot and the lens tables, over the one fetch
 * client in getJson.ts.
 *
 * Response shapes are declared as TypeScript interfaces below; the backend
 * is the source of truth. If the OpenAPI schema shifts, adjust here.
 *
 * Behavior:
 *   - Same origin, always: the backend serves the built page and the dev
 *     server proxies /api, so every path is relative. The product runs on
 *     one machine; there is no other API host to point at.
 *   - A non-2xx answer throws getJson's ApiError (the server's sentence,
 *     the status, the body), as every other read does.
 *   - AbortSignal passthrough for TanStack Query cancellation.
 *   - No client-side ETag storage — the browser HTTP cache + backend 304
 *     short-circuit is enough. TanStack Query dedupes concurrent requests.
 */

import { answered } from './getJson'

// ---------- Types (mirror backend response shapes) ---------------------------

/**
 * SnapshotProject mirrors backend `ProjectSummary` (models.py).
 * Field names are 1:1 with the pydantic model — do not rename without a backend change.
 */
export interface SnapshotProject {
  code: string
  name: string
  l1_headline: string
  open_tasks: number
  tasks_total: number
  tasks_done_7d: number
  decisions_7d: number
  est_hours_30d: number
  active_agents: number
  last_activity: string
}

export interface SnapshotActivity {
  id: string
  project: string
  agent_id: string
  activity_type: string
  duration_min: number | null
  /** Of duration_min, the agent working. */
  agent_min?: number | null
  files_touched: string
  related_goal_id: string | null
  created_date: string
  summary: string
}

export interface SnapshotAgent {
  agent_id: string
  agent_name: string
  /** The name the user gave the chat in their tool; outranked by agent_name. */
  chat_title?: string
  project: string
  parent_agent_id: string | null
  created_date: string
  last_active: string
  message_count: number
  l1_headline: string
  files_touched: string[]
  tags: string[]
  /** The operator's group for this agent ('' for none). */
  agent_group?: string
}

/** A task as the overview and search name it — mirrors backend `TaskBrief`. */
export interface SnapshotTask {
  id: string
  project: string
  title: string
  status: string
  priority: string
  sprint_id: string
  created_date: string
  agent_id: string
}

export interface SnapshotDecision {
  id: string
  decision_text: string
  rationale: string
  source: string
  agent_id: string
  related_goal_id: string | null
  tags: string
  created_date: string
  project: string
}

export interface SnapshotCapabilities {
  terminal_enabled: boolean
}

export interface SnapshotResponse {
  view_mtime: number
  capabilities?: SnapshotCapabilities
  kpi: {
    projects: number
    agents: number
    open_tasks: number
    tasks_done_7d: number
    decisions_7d: number
    est_hours_30d: number
  }
  projects: SnapshotProject[]
  recent_activity: SnapshotActivity[]
  /** Cross-project open tasks, the ones in play first. */
  open_tasks: SnapshotTask[]
  recent_decisions: SnapshotDecision[]
  agents: SnapshotAgent[]
}

// ---------- Core fetch -------------------------------------------------------

interface FetchOpts {
  signal?: AbortSignal
  query?: Record<string, string | number | boolean | undefined | null>
}

function buildUrl(path: string, query?: FetchOpts['query']): string {
  const url = `${path.startsWith('/') ? '' : '/'}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue
    params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

async function request<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const res = await answered(buildUrl(path, opts.query), opts.signal, { Accept: 'application/json' })
  // An endpoint may answer in plain text.
  const ct = res.headers?.get('content-type') ?? ''
  if (ct.includes('application/json')) return (await res.json()) as T
  return (await res.text()) as unknown as T
}

// ---------- Public endpoints -------------------------------------------------

export const api = {
  snapshot: (signal?: AbortSignal) => request<SnapshotResponse>('/api/snapshot', { signal }),
}

// ---------- Lens endpoints (generic entity tables) ---------------------------

/**
 * One row of a lens table. The backend returns the full canonical column set
 * for each entity (see backend/backend/entities.py); lenses render a shared
 * subset and pass the rest through untouched.
 */
export interface LensRow {
  id: string
  created_date: string
  created_time?: string
  project?: string
  agent_id?: string
  md_ref?: string
  [key: string]: unknown
}

interface LensListResponse {
  total: number
  rows: LensRow[]
}

/** What a turn changed — the commits that landed in its window. */
export interface TurnWork {
  commits: Array<{
    sha: string
    at: string
    author: string
    subject: string
    files: Array<{ path: string; add: number; del: number }>
    files_n: number
    add: number
    del: number
  }>
  files_n: number
  add: number
  del: number
  /** Edits in the working tree when the turn ended, never committed there. */
  uncommitted?: {
    files_n: number
    add: number
    del: number
    paths: Array<{ path: string; add: number; del: number; new: boolean }>
  } | null
  /** True when the capture hook stamped the turn; false when attributed by the clock. */
  exact?: boolean
}

export interface SessionTurn {
  n: number
  at: string
  user: string
  agent: string
  work?: TurnWork
}

/** One annotated path on a file entry — mechanics from git, judgment from the agent. */
export interface FilePathRecord {
  path: string
  action?: string
  lines_add?: number
  lines_del?: number
  importance?: number
  blast_radius?: number
  novelty?: string
  test_coverage?: string
  security_surface?: boolean
  agent_confidence?: number
  tags?: string[]
  why?: string
}

interface LensDetailResponse {
  metadata: LensRow
  /** The entry's text by the names of its lens — read it with lib/entryText. */
  text?: Record<string, unknown>
  /** Storage slots, still sent for older readers. Pages read `text`. */
  l2: string
  l3: string[]
  l4: string
  /** Chats only: the history of the block, turn by turn. */
  turns?: SessionTurn[]
  /** Files only: the annotated path list and the git range behind it. */
  paths?: FilePathRecord[]
  commit_from?: string
  commit_to?: string
  dirty?: boolean
  /** filled | not-a-repo | no-path | '' (older entries) — whether git supplied the numbers. */
  git_status?: string
  range_basis?: string
  /** Entity-specific extras: library bodies. */
  body?: string
}

export const lensApi = {
  /** List rows of `/api/<base>`; unwraps the per-entity list key. */
  list: async (
    base: string,
    listKey: string,
    query: Record<string, string | number | undefined>,
    signal?: AbortSignal,
  ): Promise<LensListResponse> => {
    const raw = await request<Record<string, unknown>>(`/api/${base}`, {
      signal,
      query,
    })
    return {
      total: Number(raw.total ?? 0),
      rows: (raw[listKey] as LensRow[]) ?? [],
    }
  },

  detail: (base: string, id: string, signal?: AbortSignal) =>
    request<LensDetailResponse>(
      `/api/${base}/${encodeURIComponent(id)}`,
      { signal },
    ),
}

// ---------- TanStack Query key factory ---------------------------------------

/** Centralised query keys — one place to invalidate cross-cuttingly. */
export const qk = {
  snapshot: () => ['snapshot'] as const,
  lensList: (base: string, params: Record<string, string | number | undefined>) =>
    ['lens', base, params] as const,
  lensDetail: (base: string, id: string) => ['lens', base, 'detail', id] as const,
}
