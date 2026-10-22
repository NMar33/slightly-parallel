/**
 * Agent profiles — the one read behind every agent page.
 *
 * `GET /api/agents/profiles?project=` joins, per agent, everything it left
 * behind: captured sessions (minutes, turns, by day, by hour), the scans it
 * posted (files, +/− lines), its file / architecture / problem / rule
 * entries, its decisions, the tasks named in its turns, the links drawn
 * to other lanes, its group. Pages only render.
 */

import { hMin } from '../../utils/format'
import { getJson } from '../../lib/getJson'
import { useQuery } from '@tanstack/react-query'

import { agentLabel } from '../../utils/agentLabel'
import type { AgentLink } from './links'

import { locale, t } from '../../i18n/scope/views'
interface ProfileAgent {
  agent_id: string
  agent_name: string
  chat_title?: string
  tool?: string
  session_ref?: string
  cwd?: string
  agent_group?: string
  project: string
  parent_agent_id?: string | null
  created_date: string
  last_active: string
  message_count: number
  l1_headline?: string
  files_touched: string[]
}

export interface ProfileTotals {
  sessions_n: number
  /** The chat busy for you: the agent or any of its helpers active. */
  minutes: number
  /** First prompt → last answer, over every session. */
  session_minutes?: number
  /** Each answer's end to your next message, less helpers still working. */
  waiting_minutes?: number
  /** The helpers the agent started, their own minutes added up: the work done. */
  helper_minutes?: number
  /** Some answer's end was not known (an old chat): minutes are an estimate. */
  minutes_approx?: boolean
  turns: number
  days_active: number
  scans_n: number
  files_n: number
  lines_add: number
  lines_del: number
  file_entries_n: number
  decisions_n: number
  architecture_n: number
  features_n: number
  problems_n: number
  bugs_resolved_n: number
  rules_n: number
  standups_n: number
  tasks_n: number
  tasks_handed_n: number
  tasks_done_n: number
  links_n: number
}

export interface ProfileSession {
  id: string
  created_date: string
  start_time: string
  end_time: string
  duration_min: number
  /** Of duration_min, the agent working, and the agent waiting on you. */
  agent_min?: number
  waiting_min?: number
  helper_min?: number
  timed?: 'exact' | 'approx'
  turns_n: number
  l1: string
  /** The chat's last line in chat.md — grows with every captured line. */
  chat_end_line?: number
}

interface ProfileScan {
  id: string
  created_date: string
  created_time: string
  l1: string
  files_n: number
  lines_add: number
  lines_del: number
  decisions_n: number
  scope: string
}

interface ProfileEntry {
  id: string
  created_date: string
  created_time?: string
  l1: string
  kind?: string
  op?: string
  area?: string
  status?: string
  severity?: string
  resolved_date?: string
  contributions_n?: number
  turns_since_prev?: number
  files_important_n?: number
}

interface ProfileDecision {
  id: string
  created_date: string
  created_time?: string
  decision_text: string
  rationale?: string
  source?: string
}

export interface ProfileTask {
  id: string
  title: string
  status: string
  first_at: string
  last_at: string
  handed_n: number
  replied_n: number
  turn_max: number
}

export interface AgentBrief {
  agent_id: string
  agent_name?: string
  chat_title?: string
  agent_group?: string
  created_date?: string
  last_active?: string
}

export interface AgentProfile {
  agent: ProfileAgent
  origin: { tool: string; cwd: string; session_ref: string; capture: string; chat_path: string }
  totals: ProfileTotals
  by_day: Array<{ date: string; turns: number; minutes: number; sessions: number }>
  by_hour: number[]
  architecture_kinds: Record<string, number>
  sessions: ProfileSession[]
  scans: ProfileScan[]
  files: ProfileEntry[]
  decisions: ProfileDecision[]
  architecture: ProfileEntry[]
  problems: ProfileEntry[]
  rules: ProfileEntry[]
  tasks: ProfileTask[]
  links: AgentLink[]
  parent: AgentBrief | null
  children: AgentBrief[]
  group: { name: string; members: AgentBrief[] }
}

export async function fetchProfiles(project: string, signal?: AbortSignal): Promise<AgentProfile[]> {
  const d = await getJson<{ profiles?: AgentProfile[] }>(`/api/agents/profiles?project=${encodeURIComponent(project)}`, signal)
  return Array.isArray(d?.profiles) ? d.profiles : []
}

async function fetchProfile(agentId: string, signal?: AbortSignal): Promise<AgentProfile> {
  return await getJson<AgentProfile>(`/api/agents/${encodeURIComponent(agentId)}/profile`, signal)
}

export function useAgentProfiles(project: string, fetcher = fetchProfiles) {
  return useQuery({
    queryKey: ['agents', 'profiles', project],
    queryFn: ({ signal }) => fetcher(project, signal),
    enabled: !!project,
    staleTime: 15_000,
  })
}

export function useAgentProfile(agentId: string, fetcher = fetchProfile) {
  return useQuery({
    queryKey: ['agents', 'profile', agentId],
    queryFn: ({ signal }) => fetcher(agentId, signal),
    enabled: !!agentId,
    staleTime: 15_000,
  })
}

// ---------------------------------------------------------------------------
// Pure helpers — shared by every roster variant and the personal page
// ---------------------------------------------------------------------------

/** "1h 05m" / "45m" / "—" — wall clock, never fractional hours. */
export const fmtMinutes = (min: number): string => hMin(min)

/** "+1,700 / −85" with thin figures; "—" when nothing was reported. */
export function fmtLines(add: number, del: number): string {
  if (!add && !del) return '—'
  return `+${add.toLocaleString(locale())} / −${del.toLocaleString(locale())}`
}

/** Display name for a profile's agent — the same rule as everywhere else. */
export function profileLabel(p: AgentProfile): string {
  return agentLabel({
    agent_id: p.agent.agent_id,
    agent_name: p.agent.agent_name,
    chat_title: p.agent.chat_title,
    created_date: p.agent.created_date,
  })
}

export const TOOL_LABEL: Record<string, string> = {
  'claude-code': 'Claude Code',
  codex: 'Codex',
  opencode: 'OpenCode',
  cursor: 'Cursor',
}

/** The tool an agent ran in — from its meta, else from the id prefix. */
export function toolOfProfile(p: AgentProfile): string {
  const tv = p.origin.tool || p.agent.tool || ''
  if (tv) return tv
  const id = p.agent.agent_id
  return id.startsWith('cc-') ? 'claude-code' : id.startsWith('codex-') ? 'codex' : id.startsWith('oc-') ? 'opencode' : id.startsWith('cursor-') ? 'cursor' : ''
}

/** One line that says what the agent did, from the best source it has. */
export function profileHeadline(p: AgentProfile): string {
  if (p.agent.l1_headline) return p.agent.l1_headline
  const last = p.sessions[p.sessions.length - 1]?.l1
  return last || ''
}

/**
 * Sort profiles into groups: grouped agents sit together in the order the
 * group first appeared; ungrouped keep their own order. Returns sections.
 */
export function groupProfiles(
  profiles: AgentProfile[],
): Array<{ name: string; members: AgentProfile[] }> {
  const order: string[] = []
  const buckets = new Map<string, AgentProfile[]>()
  for (const p of profiles) {
    const g = p.agent.agent_group || ''
    if (!buckets.has(g)) {
      buckets.set(g, [])
      order.push(g)
    }
    buckets.get(g)!.push(p)
  }
  return order.map((name) => ({ name, members: buckets.get(name)! }))
}

/** Fleet-wide sums — the strip above every roster. */
export function sumTotals(profiles: AgentProfile[]): ProfileTotals {
  const keys = Object.keys(
    profiles[0]?.totals ?? {
      sessions_n: 0, minutes: 0, turns: 0, days_active: 0, scans_n: 0, files_n: 0,
      lines_add: 0, lines_del: 0, file_entries_n: 0, decisions_n: 0,
      architecture_n: 0, features_n: 0, problems_n: 0, bugs_resolved_n: 0, rules_n: 0,
      standups_n: 0, tasks_n: 0, tasks_handed_n: 0, tasks_done_n: 0, links_n: 0,
    },
  ) as Array<keyof ProfileTotals>
  const out = {} as ProfileTotals
  for (const k of keys) {
    if (k === 'minutes_approx') continue
    ;(out as unknown as Record<string, number>)[k] = profiles.reduce((s, p) => s + (Number(p.totals[k]) || 0), 0)
  }
  out.minutes_approx = profiles.some((p) => p.totals.minutes_approx)
  return out
}

/** "≈" in front of a number that is partly an estimate. */
export const approx = (on: boolean | undefined) => (on ? '≈' : '')

/** The session's other two numbers, for under the agent's time. */
export function sessionLine(session: number | undefined, waiting: number | undefined, helpers?: number): string {
  if (!session) return ''
  const work = helpers ? ` · helpers ${fmtMinutes(helpers)}` : ''
  return t('of {fmtMinutes} in session · {fmtMinutes2} waiting on you{work}', { fmtMinutes: fmtMinutes(session), fmtMinutes2: fmtMinutes(waiting ?? 0), work })
}

/** Task status → a tone word the parts can colour. */
export function taskTone(status: string): 'done' | 'doing' | 'open' {
  if (status === 'done' || status === 'done-archived') return 'done'
  if (status === 'doing' || status === 'review') return 'doing'
  return 'open'
}
