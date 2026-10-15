import { stampMs } from '../../utils/dateUtils'
import { entryText, type EntryDetailLike } from '../../lib/entryText'
import { keepPreviousData, useQueries, useQuery } from '@tanstack/react-query'

import { api, qk, type SnapshotAgent } from '../../lib/api'
import { getJson } from '../../lib/getJson'
import { agentLabel } from '../../utils/agentLabel'

/**
 * Standups — what the pages read.
 *
 * A standup holds a summary (yesterday, then today), the deviation (what was
 * planned against what happened), the movement (one item per task) and a
 * longer detail. The list carries the summary; the rest comes from each
 * standup's own document. The server sends the text under `text` by name;
 * an older server sends the storage keys, so both are read.
 */

export interface StandupRow {
  id: string
  created_date: string
  created_time: string
  project: string
  agent_id: string
  l1: string
  for_date?: string
}

const str = (v: string | string[] | undefined): string => (typeof v === 'string' ? v : '')
const asList = (v: string | string[] | undefined): string[] | undefined => (Array.isArray(v) ? v : undefined)

/** Beside a standup's text, from the record: GET /api/standups/day. */
export interface DayRecord {
  tasks: Array<{ id: string; title: string; status: string; moves: Array<{ from: string; to: string; at: string; actor: string }>; agents: string[] }>
  agents: Array<{ agent_id: string; chat: string; from: string; to: string; turns_n: number; commits_n: number; agent_min: number; tasks: string[]; tool: string; cwd: string; session_ref: string }>
  created: Array<{ kind: string; id: string; title: string }>
}

export function useDayRecord(project: string, day: string, on: boolean) {
  return useQuery({
    queryKey: ['standups-page', 'day', project, day],
    queryFn: ({ signal }) => getJson<DayRecord>(`/api/standups/day?project=${encodeURIComponent(project)}&date=${encodeURIComponent(day)}`, signal),
    staleTime: 60_000,
    enabled: on && !!project && !!day,
  })
}

export interface Standup {
  row: StandupRow
  /** Milliseconds, for ordering. 0 when the date does not read. */
  at: number
  day: string
  summary: string
  deviation: string
  movement: string[]
  detail: string
  /** The day told (one to three paragraphs); empty on standups written before it existed. */
  story: string
  decisions: string[]
  forgotten: string[]
  /** The day it covers (for_date), else the day before it was written. */
  covers: string
  /** The agent's name as the rest of the product shows it. */
  who: string
  loaded: boolean
}

type Detail = EntryDetailLike

const EVERY = () => true

/** What a name is made from: the snapshot's agent, or just the id of one it does not hold. */
type AgentLite = Pick<SnapshotAgent, 'agent_id'> & Partial<Pick<SnapshotAgent, 'agent_name' | 'chat_title' | 'created_date'>>

export function matches(s: Standup, q: string): boolean {
  if (!q) return true
  const hay = `${s.summary} ${s.deviation} ${s.movement.join(' ')} ${s.who} ${s.row.agent_id} ${s.row.project}`.toLowerCase()
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))
}

const TASK_RE = /\btk_[0-9a-f]{8}\b/

/** Split a movement line on the task ids it names, keeping them. */
export function splitTasks(line: string): { text: string; task?: string }[] {
  const out: { text: string; task?: string }[] = []
  let rest = line
  for (;;) {
    const m = TASK_RE.exec(rest)
    if (!m) break
    if (m.index > 0) out.push({ text: rest.slice(0, m.index) })
    out.push({ text: m[0], task: m[0] })
    rest = rest.slice(m.index + m[0].length)
  }
  if (rest) out.push({ text: rest })
  return out
}

/**
 * Every standup. The list carries each one's summary; `want` says which
 * of them are on show and so need their own document (deviation, movement,
 * detail). The rest are drawn from the row until they are wanted.
 */
export function useStandups(want: (row: StandupRow) => boolean = EVERY): { standups: Standup[]; loading: boolean; error: boolean } {
  const list = useQuery<StandupRow[]>({
    queryKey: ['standups-page', 'list'],
    queryFn: ({ signal }) =>
      getJson<{ standups?: StandupRow[] }>('/api/standups?limit=1000', signal).then((d) => d.standups ?? []),
    placeholderData: keepPreviousData,
  })
  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal), staleTime: 30_000 })
  const rows = list.data ?? []
  const details = useQueries({
    queries: rows.map((r) => ({
      queryKey: ['standups-page', 'detail', r.id],
      queryFn: ({ signal }: { signal: AbortSignal }) => getJson<Detail>(`/api/standups/${encodeURIComponent(r.id)}`, signal),
      staleTime: 60_000,
      enabled: want(r),
    })),
  })

  const agents = new Map<string, AgentLite>(
    (snapshot.data?.agents ?? []).map((a) => [a.agent_id, a]),
  )
  const standups = rows.map((row, i): Standup => {
    const d = details[i]?.data
    const held = entryText(d)
    return {
      row,
      at: stampMs(row.created_date, row.created_time),
      day: row.created_date,
      summary: held.line || (row.l1 ?? ''),
      // By name: a standup has more text fields than the generic four.
      deviation: str(held.byName.deviation) || held.text,
      movement: asList(held.byName.movement) ?? held.list,
      detail: 'detail' in held.byName ? str(held.byName.detail) : held.long,
      story: str(held.byName.story),
      decisions: asList(held.byName.decisions) ?? [],
      forgotten: asList(held.byName.forgotten) ?? [],
      covers: row.for_date || row.created_date,
      who: agentLabel(agents.get(row.agent_id) ?? { agent_id: row.agent_id }),
      loaded: d !== undefined,
    }
  })
  // First load only: a refetch keeps what is on the page.
  return { standups, loading: list.isLoading && !list.data, error: list.isError }
}
