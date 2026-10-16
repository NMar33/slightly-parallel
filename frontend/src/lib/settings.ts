import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { getJson, postJson } from './getJson'

export interface SettingSpec {
  key: string
  label: string
  description: string
  type: 'int' | 'bool' | 'choice' | 'text'
  default: number | boolean | string
  group: string
  unit: string
  minimum: number | null
  maximum: number | null
  options: string[]
  /** A choice whose options are suggestions: a typed value is accepted too. */
  free?: boolean
  value: number | boolean | string
}

interface EnvEntry {
  key: string
  label: string
  value: string
}

interface SettingsPayload {
  groups: Array<{ name: string; settings: SettingSpec[] }>
  environment: EnvEntry[]
  file: string
}

export async function fetchSettings(signal?: AbortSignal): Promise<SettingsPayload> {
  return getJson<SettingsPayload>('/api/settings', signal)
}

export async function saveSettings(
  values: Record<string, number | boolean | string>,
): Promise<void> {
  await postJson('/api/settings', { values })
}

export const SETTINGS_QUERY_KEY = ['settings'] as const

/** All settings as a flat key→value map (undefined while loading). */
export function useSettingsValues(): Record<string, number | boolean | string> | undefined {
  const { data } = useQuery({
    queryKey: SETTINGS_QUERY_KEY,
    queryFn: ({ signal }) => fetchSettings(signal),
    staleTime: 30_000,
  })
  if (!data) return undefined
  const out: Record<string, number | boolean | string> = {}
  for (const g of data.groups) for (const s of g.settings) out[s.key] = s.value
  return out
}

/** One integer setting with a fallback used until settings load. */
export function useIntSetting(key: string, fallback: number): number {
  const values = useSettingsValues()
  const v = values?.[key]
  return typeof v === 'number' ? v : fallback
}

/** One string (choice) setting with a fallback used until settings load. */
export function useStrSetting(key: string, fallback: string): string {
  const values = useSettingsValues()
  const v = values?.[key]
  return typeof v === 'string' ? v : fallback
}

/**
 * The freshness poll: /api/health every `ui.poll_seconds`, and when the
 * server's data stamp moves, the active queries of the areas that moved
 * are asked again — once, together.
 *
 * Nothing that lives under the data root polls for itself. The stamp is
 * `view_mtime`, bumped whenever a file under the data root changes, so a
 * change on disk shows within one poll and a quiet server costs one small
 * request per interval. What the stamp cannot see keeps a poll of its own:
 * the terminal list, the monitor, capture health, backups, the smart
 * timer's state (away notices) and the top bar's minutes for today, which
 * grow with the clock and not with a write.
 */
export function useFreshness(fallbackMs: number): void {
  const queryClient = useQueryClient()
  const seconds = useIntSetting('ui.poll_seconds', fallbackMs / 1000)
  const health = useQuery({
    queryKey: FRESHNESS_QUERY_KEY,
    queryFn: ({ signal }) =>
      getJson<{ fs_mtime: number | string; stamps?: Record<string, number> }>('/api/health', signal),
    refetchInterval: Math.max(1, seconds) * 1000,
    refetchIntervalInBackground: false,
    staleTime: 0,
  })
  const stamp = health.data?.fs_mtime
  const stamps = health.data?.stamps
  const seen = useRef<{ stamp: number | string; stamps: Record<string, number> } | undefined>(undefined)
  useEffect(() => {
    if (stamp === undefined) return
    const before = seen.current
    seen.current = { stamp, stamps: stamps ?? {} }
    if (before === undefined || before.stamp === stamp) return
    const moved = new Set(Object.keys(stamps ?? {}).filter((a) => stamps![a] !== before.stamps[a]))
    // Without the areas — an older server — every page is asked again.
    const all = moved.size === 0
    void queryClient.invalidateQueries({
      predicate: (q) => {
        if (q.queryKey[0] === FRESHNESS_QUERY_KEY[0]) return false
        if (all) return true
        const areas = areasOf(q.queryKey)
        return areas === null || areas.some((a) => moved.has(a))
      },
    })
  }, [queryClient, stamp, stamps])
}

const FRESHNESS_QUERY_KEY = ['freshness'] as const

/**
 * Which areas a query reads, from its key — the pages whose keys are known
 * here reload only for a change in their own area. Null is "any": a key
 * this list does not know reloads on every change, which is never wrong.
 */
export function areasOf(key: readonly unknown[]): string[] | null {
  const [head, second] = key
  if (head === 'session-turns' || head === 'chat') return ['chats']
  if (head === 'scans-page') return ['scans']
  if (head === 'lens') {
    if (second === 'sessions') return ['chats']
    if (second === 'scans' || second === 'files' || second === 'architecture') return ['scans']
    // A task's rows carry what the chats said about it.
    if (second === 'tasks') return ['tasks', 'chats']
    // The kept pages and the day books: their ledgers land in "rest".
    if (second === 'visions' || second === 'rules' || second === 'problems' || second === 'entrypoints' || second === 'skills'
      || second === 'artifacts' || second === 'decisions' || second === 'standups' || second === 'prompts') return ['rest']
  }
  // The board and everything task-shaped (sprints, milestones, time, evidence).
  // What the board draws on its cards beside the chat mentions (time in the
  // column, notes, evidence, links) is task data alone: a chat moving every
  // few seconds does not ask for those again.
  if (head === 'tasks' && second === 'board'
    && (key[2] === 'since' || key[2] === 'notes' || key[2] === 'evidence' || key[2] === 'links')) return ['tasks']
  // The plain lists of tasks and links (features/tasks/data.ts): titles,
  // statuses, sprints — nothing a chat changes.
  if (head === 'tasks' && (second === 'project' || second === 'all' || second === 'links')) return ['tasks']
  if (head === 'tasks') return ['tasks', 'chats']
  // Every `time-…` key (entries, running, summary, sprints, the smart
  // timer's state) by its prefix: a new one must not fall to "any" and
  // re-read five thousand entries whenever a chat moves.
  if (head === 'sprints' || head === 'milestones' || head === 'boards' || head === 'evidence-prompts'
    || (typeof head === 'string' && head.startsWith('time-'))) return ['tasks']
  if (head === 'visions' || head === 'rules' || head === 'problems' || head === 'entrypoints' || head === 'skills'
    || head === 'artifacts' || head === 'standups-page' || head === 'standups-calendar' || head === 'standups'
    || head === 'decisions-page' || head === 'prompt-library' || head === 'integrate' || head === 'reason'
    || head === 'tour') return ['rest']
  // Constants of the server's code: no write ever changes them.
  if (head === 'story-templates') return []
  // The home page's year of chats (up to 5000 rows) asks again every
  // minute by itself; a chat moving every few seconds must not re-read it.
  if (head === 'overview' && second === 'year') return []
  if (head === 'overview' && second === 'standups') return ['rest']
  // A film is read once per project; a reload mid-film would restart it.
  if (head === 'timelapse') return []
  if (head === 'architecture-page') return ['scans']
  if (head === 'calendar' || head === 'milestone-tasks') return ['tasks', 'rest']
  // Not the data root at all: these poll for themselves and the stamp never moves for them.
  if (head === 'monitor' || head === 'terminal' || head === 'logs' || head === 'backups' || head === 'backup'
    || head === 'capture') return []
  return null
}
