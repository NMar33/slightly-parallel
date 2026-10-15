import { useQuery } from '@tanstack/react-query'
import { getJson } from '../../../lib/getJson'
import { t } from '../../../i18n/scope/system'

/** The map of a program: every part as a row of one kind, and what
 *  connects to what (backend repomap.py). Kept in versions. */
export interface MapRow {
  kind: string
  name: string
  what: string
  where?: string
  version?: string
  evidence?: string
  note?: string
}
interface MapRelation { from: string; verb: string; to: string }
interface MapDoc {
  template: string
  rows: MapRow[]
  relations: MapRelation[]
  notes: Record<string, string>
}
interface MapVersion { n: number; at: string; agent_id: string; note: string; template: string; rows_n: number }
export interface MapCurrent extends MapVersion {
  map: MapDoc
  changes: { added: MapRow[]; removed: MapRow[] }
  problems: string[]
  by_kind: Record<string, number>
}
export interface MapFacts {
  files?: number
  languages?: Array<[string, number]>
  manifests?: Array<{ file: string; declares: Record<string, unknown> }>
  build_and_ci_files?: string[]
  test_folders?: string[]
  env_variables_read_by_code?: string[]
  ports_named_in_code?: string[]
  git?: { commits: string; last_commit: string; remote: string[] } | null
  note?: string
}
interface MapAnswer {
  project: string
  map: MapCurrent | null
  versions: MapVersion[]
  kinds: string[]
  verbs: string[]
  templates: Record<string, string[]>
  facts: MapFacts
}

export function useMap(project: string, version?: number) {
  return useQuery({
    queryKey: ['map', project, version ?? 'current'],
    queryFn: ({ signal }) =>
      getJson<MapAnswer>(`/api/map?project=${encodeURIComponent(project)}${version ? `&version=${version}` : ''}`, signal),
    enabled: !!project,
  })
}

/** The kinds in the order a lead reads them: how it runs, where a person
 *  or a program meets it, what it is made of, what it needs, how it is
 *  checked. The vocabulary is the server's; this is only the order. */
const KIND_ORDER = [
  'runtime', 'framework', 'library', 'entry', 'surface', 'api', 'service', 'module', 'step', 'model',
  'store', 'data-in', 'data-out', 'external', 'config', 'auth', 'job', 'build', 'deploy', 'test',
]

export const KIND_WORDS: Record<string, string> = {
  runtime: t('Runtime'), framework: t('Framework'), library: t('Libraries'), entry: t('Entries'), surface: t('Surfaces'),
  api: t('Program interfaces'), service: t('Services'), module: t('Modules'), step: t('Steps'), model: t('Models'),
  store: t('Stores'), 'data-in': t('Data in'), 'data-out': t('Data out'), external: t('Outside services'),
  config: t('Configuration'), auth: t('Who may do what'), job: t('Jobs'), build: t('Build'), deploy: t('Deploy'), test: t('Tests'),
}

/** Rows grouped by kind, kinds in reading order; a kind the map lacks is left out. */
export function groupRows(rows: MapRow[]): Array<[string, MapRow[]]> {
  const by = new Map<string, MapRow[]>()
  for (const r of rows) by.set(r.kind, [...(by.get(r.kind) ?? []), r])
  const known = KIND_ORDER.filter((k) => by.has(k)).map((k) => [k, by.get(k)!] as [string, MapRow[]])
  const rest = [...by.keys()].filter((k) => !KIND_ORDER.includes(k)).map((k) => [k, by.get(k)!] as [string, MapRow[]])
  return [...known, ...rest]
}

/** The problems that name a given row, by its name in quotes. */
export function problemsFor(problems: string[], name: string): string[] {
  return problems.filter((p) => p.includes(`“${name}”`))
}
