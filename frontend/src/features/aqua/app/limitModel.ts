import { TERMINAL_AGENT_KINDS, type TerminalAgentKind, type TerminalLimitSession, type TerminalMemory } from '../../../lib/terminalLimit'

const DAY_SECONDS = 86400

export type SortColumn = 'label' | 'project' | 'agent_kind' | 'created' | 'last_opened' | 'last_activity' | 'activity' | 'memory_bytes'
export type GroupMode = '' | 'project' | 'date'
export type FilterState = '' | 'attached' | 'running' | 'idle'
export interface Triage {
  project: string
  agent: '' | TerminalAgentKind
  state: FilterState
  inactiveDays: number
  sort: SortColumn
  descending: boolean
  group: GroupMode
}
interface TerminalGroup {
  key: string
  rows: TerminalLimitSession[]
}

export function limitChoices(current: number, maximum: number): number[] {
  const finite = [1, 32, 64, 128, maximum, current].filter((value) => value > 0 && value <= maximum)
  return [...new Set(finite)].sort((a, b) => a - b).concat(0)
}

export function projectedMemory(kinds: TerminalMemory['kinds'], limit: number): number | null {
  if (limit === 0) return null
  let equivalentBytes = 0
  let count = 0
  for (const key of TERMINAL_AGENT_KINDS) {
    const { count: running, measured, bytes } = kinds[key]
    if (running && !measured) return null
    if (measured) equivalentBytes += bytes / measured * running
    count += running
  }
  return count ? equivalentBytes / count * limit : null
}

export const needsCloseConfirmation = (row: TerminalLimitSession) =>
  row.attachment_known === false || row.foreground_known === false || row.attached || row.running || row.recent_output

function matchesState(row: TerminalLimitSession, state: FilterState): boolean {
  switch (state) {
    case 'attached': return row.attached
    case 'running': return row.recent_output
    case 'idle': return !row.attached && !row.recent_output
    default: return true
  }
}

function compare(a: TerminalLimitSession, b: TerminalLimitSession, sort: SortColumn, descending: boolean): number {
  const left = a[sort]
  const right = b[sort]
  if (left == null) return right == null ? 0 : 1
  if (right == null) return -1
  const result = typeof left === 'number' && typeof right === 'number' ? left - right : String(left).localeCompare(String(right))
  return descending ? -result : result
}

export function triageTerminals(rows: TerminalLimitSession[], filters: Triage, now: number): TerminalGroup[] {
  const { project, agent, state, inactiveDays, sort, descending, group } = filters
  const filtered = rows.filter((row) => {
    const last = row.last_activity ?? Date.parse(row.created) / 1000
    return (!project || row.project === project) && (!agent || row.agent_kind === agent)
      && matchesState(row, state) && (!inactiveDays || now - last > inactiveDays * DAY_SECONDS)
  }).sort((a, b) => compare(a, b, sort, descending))
  if (!group) return [{ key: '', rows: filtered }]

  const day = new Date(now * 1000)
  day.setHours(0, 0, 0, 0)
  const week = new Date(day)
  week.setDate(day.getDate() - (day.getDay() + 6) % 7)
  const grouped = new Map<string, TerminalLimitSession[]>()
  for (const row of filtered) {
    const created = Date.parse(row.created)
    const key = group === 'project' ? row.project : created >= day.getTime() ? 'today' : created >= week.getTime() ? 'week' : 'older'
    const entries = grouped.get(key) ?? []
    entries.push(row)
    grouped.set(key, entries)
  }
  const keys = group === 'date' ? ['today', 'week', 'older'] : [...grouped.keys()].sort()
  return keys.flatMap((key) => {
    const entries = grouped.get(key)
    return entries?.length ? [{ key, rows: entries }] : []
  })
}
