/**
 * Artifacts — the data layer of the artifacts page.
 *
 * An artifact is a folder an agent wrote under the project in the Slightly Parallel
 * directory: ARTIFACT.md on top, the files beside it (backend/artifactlib.py).
 * One record per folder; the detail reads the folder as it is right now —
 * the files, the manifest, and a preview by kind. The page reads it for the
 * sections on screen (near.ts), not for every artifact at once.
 */

import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'

import { getJson, postJson } from '../../lib/getJson'
import { settled, type Kept, type VisionRow } from '../visions/data'
import { useNear } from '../visions/near'
import { t } from '../../i18n/scope/system'

export type Kind = 'dataset' | 'document' | 'page' | 'app' | 'other'

export const KINDS: { kind: Kind; title: string; one: string; line: string }[] = [
  { kind: 'dataset', title: t('Datasets'), one: t('Dataset'), line: t('Rows with fields, for training or checking.') },
  { kind: 'document', title: t('Documents'), one: t('Document'), line: t('Text to read: research, notes, a report.') },
  { kind: 'page', title: t('Pages'), one: t('Page'), line: t('A web page that opens as it is.') },
  { kind: 'app', title: t('Apps'), one: t('App'), line: t('Sources and a line that runs them.') },
  { kind: 'other', title: t('Other'), one: t('Other'), line: t('Files of any kind.') },
]

interface ArtifactRow extends VisionRow {
  /** The folder name. Empty until the agent made the record. */
  name: string | null
  kind: Kind | '' | null
  description: string | null
  /** draft · active · archived */
  status: string | null
  /** The folder, absolute. */
  path: string | null
  files_n: number | null
  bytes: number | null
  updated_at: string | null
}

interface ArtifactFile {
  path: string
  bytes: number
  is_text: boolean
}

export interface TablePreview {
  file: string
  fields: string[]
  rows: number
  sample: Record<string, unknown>[]
  /** Why the file could not be read to the end, when it could not. */
  error?: string
}

export interface TreeEntry {
  path: string
  dir: boolean
  depth: number
  bytes?: number
}

export interface Preview {
  kind: Kind
  /** The folder is gone. */
  missing: boolean
  readme?: string
  tables?: TablePreview[]
  document?: { file: string; text: string; truncated: boolean }
  entry?: string | null
  pages?: string[]
  tree?: TreeEntry[]
  run?: string
}

interface Folder {
  path: string
  exists: boolean
  files: ArtifactFile[]
  manifest: { meta: Record<string, unknown>; body: string }
  preview: Preview
}

interface ArtifactDetail {
  metadata: ArtifactRow
  kept?: Kept
  artifact?: Folder
}

export interface Artifact {
  row: ArtifactRow
  kept: Kept | null
  folder: Folder | null
  /** Its detail is still to come: only the row is known. */
  pending?: boolean
}

export const NEW_ARTIFACT = { project: '', name: '', kind: 'document' as Kind, description: '' }

/**
 * Every artifact, newest first, with its folder as it is now for the ones
 * `near` holds — the page watches its sections.
 */
export function useArtifacts(project = '') {
  const near = useNear()
  const list = useQuery({
    queryKey: ['artifacts', project],
    queryFn: ({ signal }) =>
      getJson<{ artifacts: ArtifactRow[] }>(
        `/api/artifacts?limit=500${project ? `&project=${encodeURIComponent(project)}` : ''}`, signal,
      ),
  })
  const rows = useMemo(() => list.data?.artifacts ?? [], [list.data])
  const details = useQueries({
    queries: rows.map((r) => ({
      queryKey: ['artifacts', 'one', r.id, r.updated_at ?? '', r.status ?? '', r.tags ?? ''],
      queryFn: ({ signal }: { signal: AbortSignal }) => getJson<ArtifactDetail>(`/api/artifacts/${r.id}`, signal),
      enabled: near.has(r.id),
      // The folder changes on disk without the row changing.
      placeholderData: keepPreviousData,
    })),
  })
  const artifacts: Artifact[] = rows.map((r, i) => {
    const q = details[i]
    if (!q || !settled(q)) return { row: r, kept: null, folder: null, pending: true }
    const d = q.data
    return { row: d?.metadata ?? r, kept: d?.kept ?? null, folder: d?.artifact ?? null }
  })
  return { list, artifacts, loading: list.isLoading, error: list.isError, near }
}

export function useArtifactWrites() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['artifacts'] })
  return {
    setStatus: useMutation({
      mutationFn: ({ id, status }: { id: string; status: 'active' | 'archived' }) =>
        postJson(`/api/artifacts/${id}/update`, { status, actor: 'operator' }),
      onSettled: refresh,
    }),
    register: useMutation({
      mutationFn: (body: { project: string; name: string; kind: Kind; description: string }) =>
        postJson<ArtifactDetail>('/api/artifacts/new', { ...body, actor: 'operator' }),
      onSettled: refresh,
    }),
  }
}

// ---------------------------------------------------------------------------
// Reading the rows
// ---------------------------------------------------------------------------

const isArchived = (a: Artifact) => a.row.status === 'archived'

/** A kept #artifact whose folder the agent never wrote. */
export const notWritten = (a: Artifact) =>
  (a.row.status ?? 'draft') === 'draft' && !(a.folder?.exists ?? false) && !a.row.name

export function kindOf(a: Artifact): Kind {
  const k = a.row.kind
  return KINDS.some((x) => x.kind === k) ? (k as Kind) : 'other'
}

export function kindTitle(kind: Kind, one = false): string {
  const k = KINDS.find((x) => x.kind === kind) ?? KINDS[KINDS.length - 1]
  return one ? k.one : k.title
}

interface Chapter {
  kind: Kind
  title: string
  line: string
  items: Artifact[]
}

/** A chapter per kind, in the kinds' order; archived and not-written rows left out. */
export function chaptersOf(artifacts: Artifact[]): Chapter[] {
  const shown = artifacts.filter((a) => !isArchived(a) && !notWritten(a))
  return KINDS.map((k) => ({ kind: k.kind, title: k.title, line: k.line, items: shown.filter((a) => kindOf(a) === k.kind) }))
    .filter((c) => c.items.length > 0)
}

export const archivedOf = (artifacts: Artifact[]) => artifacts.filter(isArchived)
export const notWrittenOf = (artifacts: Artifact[]) => artifacts.filter((a) => notWritten(a) && !isArchived(a))

export function projectsOf(artifacts: Artifact[]): string[] {
  return [...new Set(artifacts.map((a) => a.row.project).filter(Boolean))].sort()
}

export function matches(a: Artifact, q: string): boolean {
  if (!q) return true
  const hay = `${a.row.name ?? ''} ${a.row.description ?? ''} ${a.row.l1} ${a.row.kind ?? ''} ${a.row.project} ${a.row.tags ?? ''}`.toLowerCase()
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))
}

export { bytes as sizeLabel } from '../../utils/format'

/** The route that serves one file of the folder, for frames and images. */
export function fileRoute(id: string, path: string): string {
  return `/api/artifacts/${encodeURIComponent(id)}/files/${path.split('/').map(encodeURIComponent).join('/')}`
}

/** Which part of the preview the page draws for this kind. */
export function previewShape(p: Preview | null | undefined): 'missing' | 'tables' | 'document' | 'page' | 'app' | 'tree' | 'empty' {
  if (!p || p.missing) return 'missing'
  if (p.kind === 'dataset') return p.tables && p.tables.length ? 'tables' : 'empty'
  if (p.kind === 'document') return p.document?.text ? 'document' : 'empty'
  if (p.kind === 'page') return p.entry ? 'page' : 'empty'
  if (p.kind === 'app') return 'app'
  return p.tree && p.tree.length ? 'tree' : 'empty'
}

export const artifactTitle = (a: Artifact) => a.row.name || a.row.l1 || a.row.id
