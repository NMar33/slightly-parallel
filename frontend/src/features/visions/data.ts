/**
 * Kept visions — the data layer shared by the vision page variants.
 *
 * A vision is an operator's message kept by its #vision tag: the message
 * itself, the turns around it, and the versions of its interpretation
 * (backend/keeplib.py). The list endpoint returns the rows with their
 * interpretation (`with_l2`); the record — the message, the versions, the
 * chat around it — rides the detail, which is read for the rows on screen
 * (near.ts), not for all of them at once. Variants differ in arrangement,
 * never in what they say, so the fetching and the derived bits live here once.
 */

import { entryText, type EntryDetailLike } from '../../lib/entryText'
import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'

import { useCallback, useMemo } from 'react'
import { getJson, postJson } from '../../lib/getJson'
import { useAllTasks } from '../tasks/data'
import { useNear, type Near } from './near'

export interface Turn {
  n: number
  at: string
  user: string
  agent: string
}

export interface Version {
  n: number
  at: string
  /** `interpreted` — written by an agent; `edited` — by the operator. */
  how: string
  note: string
  text: string
  words: number
  chars: number
}

export interface Kept {
  kind: string
  /** A rule written from a problem reads that problem's message; this is its id. */
  from?: string | null
  /** The operator's message, verbatim, tags taken out. Never edited. */
  message: string
  /** The tagged turn as captured, tag and agent reply included. */
  turn: Turn | null
  before: Turn[]
  after: Turn[]
  versions: Version[]
  current: Version | null
}

export interface VisionRow {
  id: string
  created_date: string
  created_time: string
  project: string
  agent_id: string
  l1: string
  source: string | null
  session_id: string | null
  source_turn: number | null
  versions_n: number | null
  /** Comma-separated groups: `ui,backend`. One vision may sit in several. */
  tags: string | null
  // Rules and problems share the shape and add their own fields.
  /** Rule: active · off. Problem: open · resolved. */
  status?: string | null
  /** Rule: "yes" when it reaches every agent in every project. */
  auto?: string | null
  /** Problem: high · medium · low. */
  severity?: string | null
  resolved_date?: string | null
  /** Rule: the problem it was written from. */
  related_incident?: string | null
  /** The interpretation, when the list was asked `with_l2`. */
  l2?: string | null
}

/** The three kinds of kept entry. Their pages share this data layer. */
export type KeptKind = 'vision' | 'rule' | 'problem'

const KIND_BASE: Record<KeptKind, { base: string; list: string }> = {
  vision: { base: '/api/visions', list: 'visions' },
  rule: { base: '/api/rules', list: 'rules' },
  problem: { base: '/api/problems', list: 'problems' },
}

export interface Vision {
  row: VisionRow
  /** The current interpretation (the entry's l2); a posted vision's own l2. */
  l2: string
  /** Null for a vision an agent posted rather than one kept from a message. */
  kept: Kept | null
  /** Its detail is still to come: `kept` is not known yet and `l2` is the list's. */
  pending?: boolean
}

/**
 * Whether a page is on its first load — the only time it shows a skeleton.
 * A detail whose key changed keeps its previous data (placeholderData), a
 * detail that failed is shown from its row, and a row that appeared during a
 * poll waits for its own detail without taking the page down: an open editor
 * survives every refetch. Only "nothing has arrived yet" is loading.
 */
export function firstLoad(listLoading: boolean, details: Array<{ data: unknown; isError: boolean }>): boolean {
  if (listLoading) return true
  return details.length > 0 && details.every((d) => d.data === undefined && !d.isError)
}

/** The details a page can draw now: arrived, or failed (drawn from the row). */
export const settled = (d: { data: unknown; isError: boolean }) => d.data !== undefined || d.isError

/** Every vision in scope with its record, newest first. */
export function useVisions(project = '') {
  return useKept('vision', project)
}

type KeptDetail = EntryDetailLike & { metadata: VisionRow; kept?: Kept }

/** The row's own fields are in the key, so a switch or a status change refetches the detail. */
const detailKey = (listKey: string, r: VisionRow) =>
  [listKey, 'one', r.id, r.versions_n ?? 0, r.tags ?? '', r.status ?? '', r.auto ?? '', r.severity ?? '']

function asVision(r: VisionRow, d: KeptDetail | undefined, pending: boolean): Vision {
  if (pending) return { row: r, l2: String(r.l2 ?? ''), kept: null, pending: true }
  return { row: d?.metadata ?? r, l2: entryText(d).text, kept: d?.kept ?? null }
}

/**
 * Every entry of one kind. Rules and problems read the same way visions do.
 *
 * Every row is there at once, with its interpretation; the record (the
 * message, the versions) arrives for the rows `near` holds — the page
 * watches its sections with `near.watch`. `details: false` reads the rows
 * alone (the problems page reads the rules for their links, never their
 * records). `complete` reads the records of the given entries first, for a
 * copy of entries the reader has not scrolled to.
 */
export function useKept(kind: KeptKind, project = '', { details = true }: { details?: boolean } = {}) {
  const { base, list: listKey } = KIND_BASE[kind]
  const qc = useQueryClient()
  const near = useNear()
  const list = useQuery({
    queryKey: [listKey, project],
    queryFn: ({ signal }) =>
      getJson<Record<string, VisionRow[]>>(
        `${base}?limit=500&with_l2=1${project ? `&project=${encodeURIComponent(project)}` : ''}`, signal,
      ),
  })
  const rows = useMemo(() => list.data?.[listKey] ?? [], [list.data, listKey])
  const detailOf = useCallback((r: VisionRow) => ({
    queryKey: detailKey(listKey, r),
    queryFn: ({ signal }: { signal: AbortSignal }) => getJson<KeptDetail>(`${base}/${r.id}`, signal),
    staleTime: 60_000,
  }), [base, listKey])
  const results = useQueries({
    queries: rows.map((r) => ({
      ...detailOf(r),
      enabled: details && near.has(r.id),
      // A key change (a new version, a switch) keeps the last detail on screen while the next one loads.
      placeholderData: keepPreviousData,
    })),
  })
  const visions: Vision[] = rows.map((r, i) => {
    const q = results[i]
    return asVision(r, q?.data, !q || !settled(q))
  })
  const complete = useCallback(async (vs: Vision[]): Promise<Vision[]> => Promise.all(vs.map(async (v) => {
    if (!v.pending) return v
    const r = rows.find((x) => x.id === v.row.id)
    if (!r) return v
    // A record that cannot be read is copied as the row has it.
    const d = await qc.fetchQuery(detailOf(r)).catch(() => undefined)
    return d ? asVision(r, d, false) : v
  })), [rows, qc, detailOf])
  return {
    list,
    visions,
    loading: list.isLoading,
    error: list.isError,
    near: near as Near,
    complete,
  }
}

/** Write a new version of the interpretation, as the operator. */
export function useInterpret(kind: KeptKind = 'vision') {
  const qc = useQueryClient()
  const { base, list } = KIND_BASE[kind]
  return useMutation({
    mutationFn: ({ id, text, note }: { id: string; text: string; note?: string }) =>
      postJson(`${base}/${id}/interpretation`, { actor: 'operator', text, note: note ?? '' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [list] })
      void qc.invalidateQueries({ queryKey: ['lens', list] })
      if (kind === 'rule') void qc.invalidateQueries({ queryKey: ['integrate'] })
    },
  })
}

/** Change an entry's own fields — a rule's status or "for all agents", a problem's status or severity. */
export function useSetFields(kind: KeptKind) {
  const qc = useQueryClient()
  const { base, list } = KIND_BASE[kind]
  return useMutation({
    mutationFn: ({ id, ...fields }: { id: string } & Partial<Pick<VisionRow, 'status' | 'auto' | 'severity' | 'resolved_date'>>) =>
      postJson(`${base}/${id}/update`, { ...fields, actor: 'operator' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [list] })
      void qc.invalidateQueries({ queryKey: ['lens', list] })
      // A rule's change rewrites the written blocks, so their states change too.
      if (kind === 'rule') void qc.invalidateQueries({ queryKey: ['integrate'] })
    },
  })
}

/** The built-in set Slightly Parallel keeps written into every project: every active rule for all agents. */
export const ALL_RULES = 'all-rules'

interface AllRules {
  items: string[]
  /** The exact block written into each AGENTS.md; empty when no rule is for all agents. */
  content: string
  words: number
  projects: Array<{ project: string; path: string; status: 'fresh' | 'stale' | 'missing' | 'none' }>
}

export function useAllRules() {
  return useQuery({
    queryKey: ['integrate', 'all-rules'],
    queryFn: ({ signal }) => getJson<AllRules>('/api/integrations/all-rules', signal),
  })
}

/** Write "Rules for all agents" into every project now — for a copy changed by hand. */
export function useSyncAllRules() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => postJson('/api/integrations/all-rules/sync', {}) as Promise<{ results: Array<{ project: string; action: string }> }>,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integrate'] }),
  })
}

/** The operator writes a rule on the basis of a problem. The problem is not changed. */
export function useRuleFromProblem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ problemId, text, title }: { problemId: string; text: string; title?: string }) =>
      postJson(`/api/problems/${problemId}/rule`, { actor: 'operator', text, title: title ?? '' }) as
        Promise<{ metadata: VisionRow; kept: Kept }>,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['rules'] }); void qc.invalidateQueries({ queryKey: ['lens', 'rules'] }) },
  })
}

interface IntegrateTarget {
  project: string
  path: string
  agents_md: boolean
}

export interface SetIntegration {
  set_id: string
  project: string
  path: string
  written_at: string
  /** fresh — the file holds what the set writes now; stale — something changed; missing — the block is gone. */
  status: 'fresh' | 'stale' | 'missing'
}

interface IntegratePreview {
  file: string
  action: 'created' | 'appended' | 'updated' | 'unchanged'
  dry_run: boolean
  content: string
  previous: string | null
  words: number
}

/** The projects a set can be written into (set up in Setup). */
export function useIntegrateTargets() {
  return useQuery({
    queryKey: ['integrate', 'targets'],
    queryFn: ({ signal }) => getJson<{ targets: IntegrateTarget[] }>('/api/integrations/targets', signal).then((d) => d.targets),
    staleTime: 60_000,
  })
}

/** Where every set was written, with each block's status. */
export function useIntegrations() {
  return useQuery({
    queryKey: ['integrate', 'all'],
    queryFn: ({ signal }) => getJson<{ integrations: SetIntegration[] }>('/api/integrations', signal).then((d) => d.integrations),
  })
}

/** Preview, write, or take out a set's block in a project's AGENTS.md. */
export function useIntegrate() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['integrate'] })
  return {
    preview: useMutation({
      mutationFn: ({ setId, project }: { setId: string; project: string }) =>
        postJson(`/api/sets/${setId}/integrate`, { project, dry_run: true }) as Promise<IntegratePreview>,
    }),
    apply: useMutation({
      mutationFn: ({ setId, project }: { setId: string; project: string }) =>
        postJson(`/api/sets/${setId}/integrate`, { project }) as Promise<IntegratePreview>,
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: ({ setId, project }: { setId: string; project: string }) =>
        postJson(`/api/sets/${setId}/integrate/remove`, { project }) as Promise<{ file: string; action: string }>,
      onSuccess: refresh,
    }),
  }
}

/** An example a new Slightly Parallel starts with. A mock: it stays on the page, out of every AGENTS.md and project. */
export const isExample = (row: Pick<VisionRow, 'source'>) => row.source === 'demo'

/** Take every example vision, rule, problem and skill out, for good. */
export function useRemoveExamples() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => postJson('/api/examples/remove', {}) as Promise<{ removed: string[] }>,
    onSuccess: () => {
      for (const key of ['visions', 'rules', 'problems', 'skills', 'integrate']) void qc.invalidateQueries({ queryKey: [key] })
    },
  })
}

/** A vision's tags as a clean list: trimmed, lowercase, no blanks or repeats. */
export function tagsOf(row: Pick<VisionRow, 'tags'>): string[] {
  return normaliseTags(row.tags ?? '')
}

/** "UI, backend ,ui" → ["ui", "backend"] — what the tags field is stored as. */
export function normaliseTags(text: string): string[] {
  return [...new Set(text.split(',').map((t) => t.trim().toLowerCase().replace(/\s+/g, '-')).filter(Boolean))]
}

/** Set one entry's tags. The server stores the comma-separated list. */
export function useSetTags(kind: KeptKind = 'vision') {
  const qc = useQueryClient()
  const { base, list } = KIND_BASE[kind]
  return useMutation({
    mutationFn: ({ id, tags }: { id: string; tags: string[] }) =>
      postJson(`${base}/${id}/update`, { tags: normaliseTags(tags.join(',')).join(','), actor: 'operator' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [list] }),
  })
}

/** Every tag in use across the given visions, commonest first. */
export function tagCounts(visions: Vision[]): Array<[string, number]> {
  const n = new Map<string, number>()
  for (const v of visions) for (const t of tagsOf(v.row)) n.set(t, (n.get(t) ?? 0) + 1)
  return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
}

/** A saved, ordered group of kept entries (backend routers/sets.py). */
export interface KeptSet {
  id: string
  name: string
  kind: string
  items: string[]
  created_at: string
  updated_at: string
}

/** The operator's saved sets of one kind, in the order they were made. */
export function useSets(kind = 'vision') {
  return useQuery({
    queryKey: ['sets', kind],
    queryFn: ({ signal }) => getJson<{ sets: KeptSet[] }>(`/api/sets?kind=${kind}`, signal).then((d) => d.sets),
  })
}

/** Make, change and forget sets. Changes show at once; the server's answer follows. */
export function useSetWrites(kind = 'vision') {
  const qc = useQueryClient()
  const key = ['sets', kind]
  const refresh = () => qc.invalidateQueries({ queryKey: key })
  return {
    create: useMutation({
      mutationFn: ({ name, items }: { name: string; items?: string[] }) =>
        postJson('/api/sets', { name, kind, items: items ?? [] }) as Promise<KeptSet>,
      onSuccess: refresh,
    }),
    update: useMutation({
      mutationFn: ({ id, ...patch }: { id: string; name?: string; items?: string[] }) =>
        postJson(`/api/sets/${id}/update`, patch) as Promise<KeptSet>,
      onMutate: async ({ id, ...patch }) => {
        // A read in flight would land on top of the change and undo it on screen.
        await qc.cancelQueries({ queryKey: key })
        const before = qc.getQueryData<KeptSet[]>(key)
        qc.setQueryData<KeptSet[]>(key, (cur) => (cur ?? []).map((s) => (s.id === id ? { ...s, ...patch } : s)))
        return { before }
      },
      // A refused change goes back at once, not at the next read.
      onError: (_e, _v, ctx) => { if (ctx?.before) qc.setQueryData(key, ctx.before) },
      onSettled: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: string) => postJson(`/api/sets/${id}/delete`, {}),
      onSuccess: refresh,
    }),
  }
}

export type SetWrites = ReturnType<typeof useSetWrites>

export interface TaskRef {
  id: string
  title: string
  status: string
  project: string
}

/** Task ids with an optional round, as the chat log writes them: tk_28b1b490.2 */
const TASK_RE = /\b(tk_[a-z0-9][a-z0-9_-]{2,40})(?:\.(\d{1,3}))?\b/g

export function taskIds(text: string): string[] {
  return [...new Set([...(text ?? '').matchAll(TASK_RE)].map((m) => m[1]!))]
}

/** Every task by id — a vision names the tasks it came from. */
export function useTaskIndex() {
  const q = useAllTasks()
  return useMemo(() => new Map((q.data ?? []).map((t): [string, TaskRef] =>
    [t.id, { id: t.id, title: String(t.title ?? ''), status: String(t.status ?? ''), project: String(t.project ?? '') }])), [q.data])
}

/** The name without the task id and list number a message may open with. */
export function cleanTitle(l1: string): string {
  return (l1 ?? '')
    .replace(/^\s*\d+\.\s*/, '')
    .replace(/^tk_[a-z0-9_-]+(?:\.\d+)?\s*·\s*/i, '')
    .trim() || l1
}

/** YYMM-DD + HH:MM → a Date. */
export function dateOf(row: Pick<VisionRow, 'created_date' | 'created_time'>): Date {
  const d = row.created_date ?? ''
  const t = row.created_time || '00:00'
  return new Date(`20${d.slice(0, 2)}-${d.slice(2, 4)}-${d.slice(5, 7)}T${t}:00`)
}

/** What Copy puts on the clipboard: the interpretation, then the words it came from. */
export function visionText(v: Vision): string {
  const head = `## ${cleanTitle(v.row.l1)}`
  const words = v.kept?.message
    ? `\n\nIn the operator's words:\n\n${v.kept.message.split('\n').map((l) => `> ${l}`).join('\n')}`
    : ''
  return `${head}\n\n${v.l2 || v.kept?.message || ''}${words}\n`
}
