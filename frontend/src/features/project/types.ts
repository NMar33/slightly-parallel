/**
 * Shared types for the Per-Project page (/project/:code) plus the payload
 * normalizer that bridges the backend /api/project/{code} response to the
 * typed shapes the page renders.
 *
 * Types mirror the backend Pydantic models; the normalizer is the single
 * place where raw payload quirks (CSV-string arrays, `summary` sub-object,
 * legacy status aliases) are smoothed out.
 */

import type { AgentMeta } from '../../components/AgentTimeline/AgentTimeline'

export type DecisionSource = 'explicit' | 'auto'

/**
 * Actor recorded on mutations made from this dashboard (task edits, library
 * items, snippets). A single constant so the audit trail stays consistent.
 */
export const OPERATOR_ACTOR = 'operator'


export interface Decision {
  id: string
  decision_text: string
  rationale: string | null
  source: DecisionSource
  agent_id: string | null
  related_goal_id: string | null
  tags: string[]
  created_date: string
  created_time?: string
  files_affected_n?: number
  alternatives_n?: number
}

export interface Activity {
  id: string
  agent_id: string | null
  activity_type: string
  duration_min: number
  /** Of duration_min, the agent working. */
  agent_min?: number
  files_touched: string[]
  related_goal_id: string | null
  created_date: string
  // SCAN-parallel mutual-activity fields — optional so legacy per-project
  // payloads (which lack them) still normalize cleanly.
  summary?: string
  start_time?: string
  end_time?: string
  goal_id?: string | null
  files_touched_n?: number
}

export interface Agent {
  id: string
  agent_name: string
  chat_title?: string
  tool?: string
  session_ref?: string
  cwd?: string
  agent_group?: string
  l1_headline: string | null
  parent_agent_id: string | null
  created_date: string
  last_active: string | null
  message_count: number
  files_touched: string[]
}


/** The task numbers the backend sums for the project (mirrors ProjectSummary). */
interface ProjectTaskSummary {
  open_tasks: number
  tasks_total: number
  tasks_done_7d: number
  decisions_7d: number
  est_hours_30d: number
}

export interface ProjectPayload {
  code: string
  name: string
  color: string          // hex OR CSS var reference; consumed as backgroundColor
  l1_headline: string
  summary: ProjectTaskSummary
  decisions: Decision[]
  activity: Activity[]
  agents: Agent[]
}

/**
 * Split a CSV-ish string coming from the backend into a clean string[].
 * The backend serializes `files_touched` / `tags` as raw strings (mirror of
 * the CSV column); the UI wants arrays. Empty / whitespace collapses to [].
 */
function splitCsv(v: unknown): string[] {
  if (Array.isArray(v)) return v.filter((x) => typeof x === 'string' && x.length > 0) as string[]
  if (typeof v !== 'string') return []
  return v
    .split(/[,;\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

/**
 * "YYMM-DD" + "HH:MM" stamps for the current moment, matching the backend's
 * CSV date conventions. Used when creating tasks / library items / snippets.
 */
export function nowStamp(now: Date = new Date()): { dateStr: string; timeStr: string } {
  const yy = String(now.getFullYear()).slice(-2)
  const dateStr = `${yy}${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  return { dateStr, timeStr }
}

/** An agent as the backend's `Agent` model sends it (models.py). */
export interface AgentRecord {
  agent_id: string
  agent_name?: string
  chat_title?: string
  tool?: string
  session_ref?: string
  cwd?: string
  agent_group?: string
  project?: string
  parent_agent_id?: string | null
  created_date?: string
  last_active?: string | null
  message_count?: number
  l1_headline?: string | null
  files_touched?: string[] | string
  tags?: string[]
}

/** `/api/agent/{id}` (backend `AgentDetail`). */
export interface AgentDetailAnswer {
  agent: AgentRecord
  chat_lines?: number
  chat_available?: boolean
}

/** `/api/project/{code}` (backend `ProjectBundle`, models.py). Every part is
 *  read as optional: the normalizer below fills what is missing. */
interface ProjectBundleAnswer {
  code?: string
  name?: string
  color?: string
  l1_headline?: string
  summary?: {
    code?: string; name?: string; l1_headline?: string
    open_tasks?: number; tasks_total?: number; tasks_done_7d?: number; decisions_7d?: number; est_hours_30d?: number
  }
  decisions?: Array<{
    id?: string; decision_text?: string; rationale?: string | null; source?: string; agent_id?: string | null
    related_goal_id?: string | null; tags?: string | string[]; created_date?: string; created_time?: string | null
    files_affected_n?: number | null; alternatives_n?: number | null
  }>
  activity?: Array<{
    id?: string; agent_id?: string | null; activity_type?: string; duration_min?: number | null; agent_min?: number | null
    files_touched?: string | string[]; files_touched_n?: number | null; goal_id?: string | null; related_goal_id?: string | null
    created_date?: string; start_time?: string | null; end_time?: string | null; summary?: string | null
  }>
  agents?: Array<AgentRecord & { id?: string }>
}

/**
 * Normalize the backend /api/project/{code} payload into the shape this page
 * expects. The backend groups project metadata into a `summary` sub-object,
 * uses `agent_id` (not `id`) for agents, serializes `files_touched` / `tags`
 * as CSV strings. Keeping this normalization in one place means the render
 * layer can rely on typed shapes without null-guards.
 */
export function normalizeProjectPayload(code: string, answer: unknown): ProjectPayload {
  const raw = (answer ?? {}) as ProjectBundleAnswer
  const summary = raw.summary ?? {}
  const toNumOrNull = (v: unknown): number | null => {
    if (v == null || v === '') return null
    const n = typeof v === 'number' ? v : Number(v)
    return Number.isFinite(n) ? n : null
  }
  const decisions: Decision[] = Array.isArray(raw?.decisions)
    ? raw.decisions.map((d) => ({
        id: String(d?.id ?? ''),
        decision_text: String(d?.decision_text ?? ''),
        rationale: d?.rationale ?? null,
        source: (d?.source === 'auto' ? 'auto' : 'explicit') as DecisionSource,
        agent_id: d?.agent_id ?? null,
        related_goal_id: d?.related_goal_id ?? null,
        tags: splitCsv(d?.tags),
        created_date: String(d?.created_date ?? ''),
        created_time: d?.created_time != null ? String(d.created_time) : undefined,
        files_affected_n: toNumOrNull(d?.files_affected_n) ?? undefined,
        alternatives_n: toNumOrNull(d?.alternatives_n) ?? undefined,
      }))
    : []

  const activity: Activity[] = Array.isArray(raw?.activity)
    ? raw.activity.map((a) => {
        const files = splitCsv(a?.files_touched)
        const filesN = toNumOrNull(a?.files_touched_n)
        return {
          id: String(a?.id ?? ''),
          agent_id: a?.agent_id ?? null,
          activity_type: String(a?.activity_type ?? ''),
          duration_min: Number(a?.duration_min) || 0,
          agent_min: a?.agent_min == null ? undefined : Number(a.agent_min) || 0,
          files_touched: files,
          related_goal_id: a?.related_goal_id ?? null,
          created_date: String(a?.created_date ?? ''),
          summary: a?.summary != null ? String(a.summary) : undefined,
          start_time: a?.start_time != null ? String(a.start_time) : undefined,
          end_time: a?.end_time != null ? String(a.end_time) : undefined,
          goal_id: a?.goal_id ?? null,
          // Prefer the server-provided count; fall back to CSV cardinality so
          // the microstat still shows something on legacy rows.
          files_touched_n: filesN ?? files.length,
        }
      })
    : []

  const agents: Agent[] = Array.isArray(raw?.agents)
    ? raw.agents.map((a) => ({
        id: String(a?.id ?? a?.agent_id ?? ''),
        agent_name: String(a?.agent_name ?? ''),
        chat_title: String(a?.chat_title ?? ''),
        tool: String(a?.tool ?? ''),
        session_ref: String(a?.session_ref ?? ''),
        cwd: String(a?.cwd ?? ''),
        agent_group: String(a?.agent_group ?? ''),
        l1_headline: a?.l1_headline ?? null,
        parent_agent_id: a?.parent_agent_id ?? null,
        created_date: String(a?.created_date ?? ''),
        last_active: a?.last_active ?? null,
        message_count: Number(a?.message_count) || 0,
        files_touched: splitCsv(a?.files_touched),
      }))
    : []

  return {
    code: String(raw?.code ?? summary?.code ?? code),
    name: String(raw?.name ?? summary?.name ?? code),
    color: String(raw?.color ?? ''),
    l1_headline: String(raw?.l1_headline ?? summary?.l1_headline ?? ''),
    summary: {
      open_tasks: Number(summary?.open_tasks) || 0,
      tasks_total: Number(summary?.tasks_total) || 0,
      tasks_done_7d: Number(summary?.tasks_done_7d) || 0,
      decisions_7d: Number(summary?.decisions_7d) || 0,
      est_hours_30d: Number(summary?.est_hours_30d) || 0,
    },
    decisions,
    activity,
    agents,
  }
}

/**
 * Adapt the Project payload's `Agent` shape (which uses `id`, and nullable
 * `last_active` / `l1_headline`) to the `AgentMeta` contract expected by
 * `<AgentTimeline />`. Nullable `last_active` falls back to `created_date`
 * so the lane still renders as a same-day tick.
 */
export function toAgentMeta(agents: Agent[]): AgentMeta[] {
  return agents.map((a) => ({
    agent_id: a.id,
    agent_name: a.agent_name,
    chat_title: a.chat_title,
    agent_group: a.agent_group,
    tool: a.tool,
    cwd: a.cwd,
    parent_agent_id: a.parent_agent_id,
    created_date: a.created_date,
    last_active: a.last_active ?? a.created_date,
    message_count: a.message_count,
    l1_headline: a.l1_headline ?? undefined,
  }))
}
