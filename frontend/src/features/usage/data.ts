import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { getJson, postJson } from '../../lib/getJson'

/**
 * Usage: the tokens agents used, per turn, per chat, per task, and the plan
 * limits (backend usagelib.py, routers/usage.py). The wire shapes and the
 * reads. Recording is always on; the page and the viewer only show it.
 */

export type UsageRange = 'today' | '7d' | '30d'
export type UsageTool = 'claude-code' | 'codex' | 'opencode' | string

/** One turn's tokens, summed over its API messages; helpers apart. */
export interface TurnUsage {
  /** Read for the first time, cache written included. */
  new: number
  /** Written by the model, thinking included. */
  output: number
  /** Read again from cache. */
  cache: number
  cache_write: number
  thinking: number
  /** cache ÷ (cache + new), as the server rounded it. */
  share?: number | null
  model: string
  models?: string[]
  messages: number
  helpers?: Helpers | null
  /** `kind`: expired · model · compacted · tool · unknown — the word on the line. */
  rebuild?: { cause: string; kind?: string } | null
  limit?: { five_hour?: number; seven_day?: number } | null
  /** The F1 line the server built: "→ 1.9k ↑ 512 ↓ (108k)", with its event words. */
  line?: string
  /** The cache TTL of the turn's writes: "5m" | "1h" | "". */
  ttl?: string
  /** Context fill, when the status line gave it. */
  context?: { used: number; size: number } | null
}

/** Helper agents' tokens, apart from the main agent's. Older answers sent a bare number (tokens). */
export interface Helpers { n?: number; new_output: number; cache?: number }

export interface LimitWindow {
  /** Percent used, 0–100; null when the tool did not give it. */
  used: number | null
  /** Local ISO seconds. */
  resets_at: string
  /** The server's "1 h 52 min" until the reset, shown as given. */
  in?: string
  expired?: boolean
  /** The window's length in seconds (5 h, 7 days; Codex says its own). */
  span_s?: number
  /** The server's words for the reset: "16:40", "Thu 09:00". */
  resets_text?: string
  /** "Reset at 16:40. No reading since." once the reset passed. */
  expired_text?: string
}

export interface LimitReading {
  five_hour?: LimitWindow | null
  seven_day?: LimitWindow | null
  read_at: string
  /** The server's clock words for read_at: "14:02", or "Sat 14:02" on another day. */
  read_at_text?: string
  stale: boolean
  expired: boolean
  plan?: string
  source?: string
}

/** One series of a tool's limits: the limits are an account's, whatever the model. */
export interface LimitSeries extends LimitReading {
  /** 12 hex characters naming the tool's config folder; '' on lines written before. */
  account: string
  /** The model id of the reading it was read at (data only); '' when not named. */
  model: string
  /** The first characters of the session that sent it (for diagnosis). */
  session?: string
}

/** A tool's limits: its own fields are the newest series' (older answers had only these). */
export interface ToolLimits extends LimitReading {
  /** What each account holds, newest first. */
  series?: LimitSeries[]
  accounts_n?: number
  /** The models the series' lines named (information only). */
  models_n?: number
}

export type Limits = Record<UsageTool, ToolLimits>

/** The background reading of Codex's limits (codex app-server): is Codex on this machine, when it was read, why not. */
export interface CodexPoll {
  found: boolean
  exe?: string
  home?: string
  enabled: boolean
  every_hours: number
  last_attempt: string
  last_success: string
  next_attempt: string
  cause: string
  failures: number
}

export interface LimitsAnswer { limits: Limits; codex_poll?: CodexPoll }

export interface UsageCounts {
  new: number
  output: number
  cache: number
  share: number | null
  turns: number
  helpers?: number | Helpers | null
  /** Tokens written to the cache; part of `new`. */
  cache_write?: number
  /** Of them, an estimate of old context written again; part of `new`. */
  rebuilt?: number
  /** The row at API prices, helpers included. */
  cost_usd?: number
  /** The same by kind: the main agent's tokens, and the helpers apart. */
  cost?: { new: number; rebuilt: number; warm: number; output: number; helpers: number }
  /** Cache rebuilds over 20k tokens (chats and tasks). */
  rebuilds?: number
  /** Tokens of models with no price, not in `cost_usd`. */
  unpriced?: number
}

export interface ApiPrice { model: string; input: number; write_5m: number | null; write_1h: number | null; read: number; output: number; over_tokens?: number | null }
export interface ApiPrices { as_of: string; sources?: string[]; models: ApiPrice[]; missing?: string[] }
/** The part of the server's analysis (usageanalysis.py) this page reads. The
 *  answer holds more (history, chats, resumes, context; see docs/api.md):
 *  the feed of insights and the MCP usage tool read those on the server. */
export interface UsageAnalysis {
  window_now: { used: number; resets_at: string; runs_out_at: string | null; lasts: boolean } | null
  units: { models: { model: string; pct_per_usd: number }[] }
  /** Where the range's use of the window went, in percent of one window. */
  mix?: { total_pct: number; windows: number; parts: { key: string; pct: number }[]; helpers_n: number }
  /** What one occurrence of each pattern takes of the window, dearest first. */
  prices?: { key: string; model?: string; each_pct: number; times: number; total_pct: number }[]
}

/** Why old context was written to the cache again, summed over the range. */
export interface CauseUsage { cause: string; rebuilt: number; cost_usd: number; events: number; chats: number }

export interface ModelUsage extends UsageCounts { model: string }
export interface ToolUsage extends UsageCounts { tool: UsageTool; models: ModelUsage[] }

export interface ChatUsage extends Partial<UsageCounts> {
  agent_id: string
  title: string
  tool: UsageTool
  project?: string
  model: string
  /** The main agent's new + output; helpers apart. */
  new_output: number
  cache: number
  turns: number
  helpers_n?: number
  helpers?: number | Helpers | null
  task_id: string
  /** Every model the chat used (main and helpers); '' is a model not named. */
  models?: string[]
  /** Every tool of its records. */
  tools?: string[]
}

export interface TaskUsage extends Partial<UsageCounts> {
  id: string
  title: string
  new_output: number
  chats: number
  helpers?: number | Helpers | null
  status: string
  done_at: string
  project?: string
  /** The tools and models of its turns. */
  tools?: string[]
  models?: string[]
}

export interface UsageSummary {
  api_prices?: ApiPrices
  by_cause?: CauseUsage[]
  analysis?: UsageAnalysis
  range: UsageRange
  project?: string
  days: string[]
  limits: Limits
  usual: { new_output: number; cache: number; share: number | null; days_used: number } | null
  totals: {
    new: number; output: number; cache: number; cache_write: number; share: number | null
    turns: number; chats: number; helpers?: Helpers | null
    rebuilt?: number; cost_usd?: number; cost?: UsageCounts['cost']; unpriced?: number
  }
  by_tool: ToolUsage[]
  chats: ChatUsage[]
  /** How many chats used tokens in the range; `chats` holds the top ones. */
  chats_total?: number
  tasks: TaskUsage[]
  tasks_total?: number
  coverage: { chats_recorded: number; chats_without_usage: number; chats_from_log?: number; unreadable: string[] }
}

export const usageKey = (project: string, range: UsageRange) => ['usage', project || 'all', range] as const

/** GET /api/usage?project=<code|all>&range=… — the page's summary. */
export function useUsage(project: string, range: UsageRange) {
  return useQuery({
    queryKey: usageKey(project, range),
    queryFn: ({ signal }) => getJson<UsageSummary>(
      `/api/usage?project=${encodeURIComponent(project || 'all')}&range=${range}`, signal),
    placeholderData: keepPreviousData,
    // The totals move slowly; the limits have their own, faster read.
    refetchInterval: 5 * 60_000,
    refetchOnWindowFocus: true,
  })
}

/** GET /api/usage/limits — the plan limits alone, read more often; with the Codex poll's state. */
export function useUsageLimits() {
  return useQuery({
    queryKey: ['usage', 'limits'],
    queryFn: ({ signal }) => getJson<LimitsAnswer>('/api/usage/limits', signal)
      .then((r) => ({ limits: r.limits ?? {}, codex_poll: r.codex_poll })),
    refetchInterval: 60_000,
  })
}

/** POST /api/usage/limits/refresh — the page asks for Codex's limits now; the server decides whether it is due. */
export function refreshLimits(): Promise<{ refreshed: boolean; why?: string }> {
  return postJson<{ refreshed: boolean; why?: string }>('/api/usage/limits/refresh', {})
}

/** Helpers of a row as {n, new_output}: an older answer's bare number is tokens, with
 *  the count from `helpers_n` when the row has one. */
export function helpersOf(h: number | Helpers | null | undefined, n?: number): { n: number; new_output: number; cache?: number } {
  if (h == null) return { n: n ?? 0, new_output: 0 }
  if (typeof h === 'number') return { n: n ?? 0, new_output: Number.isFinite(h) ? h : 0 }
  return { n: h.n ?? n ?? 0, new_output: h.new_output ?? 0, cache: h.cache }
}

/** The colour of a tool: its lane hue (tokens.css --lane-*). */
export function toolColor(tool: string): string {
  if (tool === 'claude-code') return 'var(--lane-1)'
  if (tool === 'codex') return 'var(--lane-2)'
  if (tool === 'opencode') return 'var(--lane-3)'
  return 'var(--text-secondary)'
}

/** The tool's name as people say it. */
export function toolName(tool: string): string {
  if (tool === 'claude-code') return 'Claude Code'
  if (tool === 'codex') return 'Codex'
  if (tool === 'opencode') return 'OpenCode'
  return tool
}

/** The order tools are listed in. */
export const TOOL_ORDER = ['claude-code', 'codex', 'opencode']
