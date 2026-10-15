
import { entryText, type EntryDetailLike } from '../../lib/entryText'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'
import { mentionLabel, type MentionAgent } from '../project/mentions'
import { t, tn } from '../../i18n/scope/system'

interface ScanRow {
  id: string
  created_date: string
  created_time: string
  project: string
  agent_id: string
  /** The summary line. */
  l1: string
  files_n: number
  lines_add: number
  lines_del: number
  decisions_n: number
  scope: string
}

interface ScanDetail extends EntryDetailLike {
  metadata: ScanRow
  files_entry?: string | null
  architecture_entry?: string | null
  warnings?: string[]
}

export interface TouchedFile {
  path: string
  action?: string
  lines_add?: number
  lines_del?: number
  importance?: number
  blast_radius?: number
  test_coverage?: string
  security_surface?: boolean
  why?: string
}

export interface Landed {
  id: string
  op: string
  type: string
  name: string
  note: string
  path: string[]
  trigger_id: string
}

export interface Scan {
  row: ScanRow
  summary: string
  why: string
  deltas: string[]
  proof: string
  /** The files the file entry judged, the ones that matter first. */
  touched: TouchedFile[]
  /** How many files the entry set aside as not worth a line. */
  ignored: number
  landed: Landed[]
  /** The file entry or the architecture form is still to come. */
  waiting: string[]
  agent: MentionAgent | null
  who: string
}

/** The architecture groups, in the form's own order. */
export const GROUPS: Array<[string, string[]]> = [
  ['does', ['feature', 'fix']],
  ['owes', ['debt', 'action-needed']],
  ['runs', ['service', 'runtime', 'config', 'deploy']],
  ['stores', ['database', 'files', 'cache', 'queue']],
  ['talks', ['endpoint', 'integration', 'hook', 'command']],
  ['built with', ['framework', 'library', 'module']],
  ['faces', ['surface', 'auth', 'job']],
  ['holds', ['rule', 'tests']],
]

export function groupOf(type: string): string {
  return GROUPS.find(([, types]) => types.includes(type))?.[0] ?? 'other'
}

function paths(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map(String)
  try {
    const v = JSON.parse(String(raw ?? '[]'))
    return Array.isArray(v) ? v.map(String) : []
  } catch {
    return raw ? [String(raw)] : []
  }
}

interface ScansPage {
  scans: Array<ScanDetail & { file: { metadata: Record<string, unknown>; paths?: TouchedFile[] } | null }>
  architecture: Array<Record<string, unknown>>
  agents: MentionAgent[]
}

export function useScans(): { scans: Scan[]; loading: boolean; error: boolean } {
  // The whole page in one answer: the scans with their text and file
  // entries, the architecture rows, the agents. It was one request for the
  // list and then two per scan.
  const page = useQuery({
    queryKey: ['scans-page', 'all'],
    queryFn: ({ signal }) => getJson<ScansPage>('/api/scans/page?limit=500', signal),
    placeholderData: keepPreviousData,
  })

  const agents = new Map((page.data?.agents ?? []).map((a) => [a.agent_id, a]))
  const landedBy = new Map<string, Landed[]>()
  for (const a of page.data?.architecture ?? []) {
    const tid = String(a.trigger_id ?? '')
    // A 'check' row is the form's receipt for a group with no change: not something that landed.
    if (!tid || !a.type || a.op === 'check') continue
    const item: Landed = {
      id: String(a.id), op: String(a.op ?? ''), type: String(a.type ?? ''), name: String(a.name ?? ''),
      note: String(a.note ?? ''), path: paths(a.path), trigger_id: tid,
    }
    landedBy.set(tid, [...(landedBy.get(tid) ?? []), item])
  }

  const scans: Scan[] = (page.data?.scans ?? []).map((d) => {
    const row = d.metadata
    const f = d.file
    const touched = [...(f?.paths ?? [])].sort(
      (a, b) => (b.importance ?? 0) - (a.importance ?? 0) || a.path.localeCompare(b.path),
    )
    const agent = agents.get(row.agent_id) ?? null
    const waiting: string[] = []
    if (!d.files_entry) waiting.push(t('file entry'))
    if (!d.architecture_entry) waiting.push(t('architecture form'))
    return {
      row,
      summary: entryText(d).line || row.l1,
      why: entryText(d).text,
      deltas: entryText(d).list,
      proof: entryText(d).long,
      touched: touched.filter((p) => (p.importance ?? 0) > 0 || p.why),
      ignored: Number(f?.metadata?.files_ignored_n ?? 0),
      landed: landedBy.get(row.id) ?? [],
      waiting,
      agent,
      who: mentionLabel({ agent_id: row.agent_id, agent }),
    }
  })

  return { scans, loading: page.isLoading && !page.data, error: page.isError && !page.data }
}

export function matches(s: Scan, q: string): boolean {
  if (!q) return true
  const hay = [
    s.summary, s.why, s.row.scope, s.who, s.row.agent_id, s.row.project,
    ...s.deltas, ...s.touched.map((t) => t.path), ...s.landed.map((l) => `${l.type} ${l.name}`),
  ].join(' ').toLowerCase()
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))
}

/** A count of one type, in the interface language: "3 features". */
const TYPE_N: Record<string, (k: number) => string> = {
  feature: (k) => tn(k, '{n} feature', '{n} features'),
  fix: (k) => tn(k, '{n} fix', '{n} fixes'),
  debt: (k) => tn(k, '{n} debt', '{n} debt'),
  'action-needed': (k) => tn(k, '{n} action-needed', '{n} action-needed'),
  service: (k) => tn(k, '{n} service', '{n} services'),
  runtime: (k) => tn(k, '{n} runtime', '{n} runtimes'),
  config: (k) => tn(k, '{n} config', '{n} configs'),
  deploy: (k) => tn(k, '{n} deploy', '{n} deploys'),
  database: (k) => tn(k, '{n} database', '{n} databases'),
  files: (k) => tn(k, '{n} files', '{n} files'),
  cache: (k) => tn(k, '{n} cache', '{n} caches'),
  queue: (k) => tn(k, '{n} queue', '{n} queues'),
  endpoint: (k) => tn(k, '{n} endpoint', '{n} endpoints'),
  integration: (k) => tn(k, '{n} integration', '{n} integrations'),
  hook: (k) => tn(k, '{n} hook', '{n} hooks'),
  command: (k) => tn(k, '{n} command', '{n} commands'),
  framework: (k) => tn(k, '{n} framework', '{n} frameworks'),
  library: (k) => tn(k, '{n} library', '{n} libraries'),
  module: (k) => tn(k, '{n} module', '{n} modules'),
  surface: (k) => tn(k, '{n} surface', '{n} surfaces'),
  auth: (k) => tn(k, '{n} auth', '{n} auth'),
  job: (k) => tn(k, '{n} job', '{n} jobs'),
  rule: (k) => tn(k, '{n} rule', '{n} rules'),
  tests: (k) => tn(k, '{n} tests', '{n} tests'),
}

/** What landed, counted by type: "3 features · 1 endpoint". */
export function landedWords(landed: Landed[]): string[] {
  const n = new Map<string, number>()
  for (const l of landed) n.set(l.type, (n.get(l.type) ?? 0) + 1)
  return [...n.entries()].sort((a, b) => b[1] - a[1]).map(([t, k]) => TYPE_N[t]?.(k) ?? `${k} ${t}`)
}
