/**
 * Everything the board reads, through the app's one query cache.
 *
 * The tasks of every member project, merged, are one query; the five things
 * drawn on the cards (chat mentions, time in the column, notes, evidence,
 * links) are one query each, fetched side by side. So:
 *
 * - a reload refetches in parallel, and only what is asked for;
 * - the app's freshness poll (lib/settings useFreshness) refetches the board
 *   when an agent changes a task, with no reload of the page;
 * - the board's optimistic edits write into the cache (`setTasks`), and the
 *   next refetch replaces them with what the server kept. A refetch already
 *   on its way when an edit is made is dropped first: it left before the
 *   edit, and its answer would put the card back where it was.
 */

import { useCallback, useEffect, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { getJson } from '../../../lib/getJson'
import type { MentionSummary, TaskLink, TaskRow } from './model'
import { PROJECT_TASKS_LIMIT } from '../../tasks/data'
import { t } from '../../../i18n/scope/project'

/** Every board query starts with this: one invalidation reaches them all. */
const BOARD_KEY = ['tasks', 'board'] as const

/* ---------------------------------------------------------------------------
 * Evidence prompts — the instructions a copied task carries. One small
 * store, shared by every copy button on the board and by the task window's
 * Evidence panel. It lives in the query cache (not a module variable) so a
 * save, a new default or a delete in the panel reaches the board's copies
 * through one invalidation instead of going stale for the session.
 * ------------------------------------------------------------------------- */

export type EvidencePrompt = { id: string; name: string; text: string }
export type EvidencePromptStore = { prompts: EvidencePrompt[]; default_id: string }

export const EVIDENCE_PROMPTS_KEY = ['evidence-prompts'] as const

export function useEvidencePrompts(enabled = true) {
  return useQuery({
    queryKey: EVIDENCE_PROMPTS_KEY,
    queryFn: async ({ signal }) => {
      const d = await getJson<Partial<EvidencePromptStore> | null>('/api/evidence-prompts', signal)
      return d && Array.isArray(d.prompts) ? (d as EvidencePromptStore) : null
    },
    // The prompts change only through the panel (which invalidates); a
    // minute keeps the board from refetching them on every remount.
    staleTime: 60_000,
    enabled,
  })
}

/** Keep what is on screen while the same board refetches (a reload, the
 *  descriptions switched on) — never another board's cards while this one
 *  loads. The board's key is the fourth part of every board query key. */
function sameBoard<T>(prev: T | undefined, prevQuery: { queryKey: readonly unknown[] } | undefined, boardKey: string): T | undefined {
  return prevQuery?.queryKey[3] === boardKey ? prev : undefined
}

/** A failed read is an error, not an empty answer: the cards keep the counts
 *  they had and the board says so, instead of quietly showing zeros. */
async function each<T>(projects: string[], path: (code: string) => string, signal?: AbortSignal): Promise<T[]> {
  return Promise.all(projects.map((code) => getJson<T>(path(code), signal)))
}

/**
 * Put some tasks back as they were, and only those: a rollback that
 * restored the whole list would also undo whatever a refetch brought in
 * for the other cards while the write was out.
 */
export function putBack(before: TaskRow[], ids: ReadonlySet<string>): (cur: TaskRow[]) => TaskRow[] {
  const was = new Map(before.filter((t) => ids.has(t.id)).map((t) => [t.id, t]))
  return (cur) => cur.map((t) => was.get(t.id) ?? t)
}

async function loadTasks(projects: string[], withBodies: boolean, signal?: AbortSignal): Promise<TaskRow[]> {
  const pages = await Promise.all(projects.map((code) =>
    getJson<{ tasks?: TaskRow[] }>(`/api/tasks?project=${encodeURIComponent(code)}&limit=${PROJECT_TASKS_LIMIT}${withBodies ? '&with_desc=1' : ''}`, signal)))
  // A task in several member projects comes back from each — keep one.
  const seen = new Set<string>()
  const merged: TaskRow[] = []
  for (const d of pages) {
    for (const t of Array.isArray(d?.tasks) ? d.tasks : []) {
      if (seen.has(t.id)) continue
      seen.add(t.id)
      merged.push(t)
    }
  }
  return merged
}

/** One per-project summary, merged into one map across the board. */
function useSummary<T>(kind: string, boardKey: string, projects: string[], path: (code: string) => string, field: string) {
  const q = useQuery({
    queryKey: [...BOARD_KEY, kind, boardKey, projects.join(',')],
    queryFn: async ({ signal }) => {
      const all: Record<string, T> = {}
      for (const d of await each<Record<string, unknown>>(projects, path, signal)) {
        Object.assign(all, (d?.[field] as Record<string, T> | undefined) ?? {})
      }
      return all
    },
    placeholderData: (prev, prevQuery) => sameBoard(prev, prevQuery, boardKey),
  })
  return { data: q.data ?? EMPTY as Record<string, T>, failed: q.isError }
}
const EMPTY = {}

export function useBoardData(boardKey: string, projects: string[], withBodies: boolean) {
  const qc = useQueryClient()
  const joined = projects.join(',')
  const tasksKey = useMemo(() => [...BOARD_KEY, 'tasks', boardKey, joined, withBodies] as const, [boardKey, joined, withBodies])
  const tasksQ = useQuery({
    queryKey: tasksKey,
    queryFn: ({ signal }) => loadTasks(projects, withBodies, signal),
    placeholderData: (prev, prevQuery) => sameBoard(prev, prevQuery, boardKey),
  })
  const q = (code: string) => encodeURIComponent(code)
  const mentionsQ = useSummary<MentionSummary>('mentions', boardKey, projects, (c) => `/api/tasks/mentions/summary?project=${q(c)}`, 'mentions')
  const sinceQ = useSummary<string>('since', boardKey, projects, (c) => `/api/tasks/status-since?project=${q(c)}`, 'since')
  const notesQ = useSummary<number>('notes', boardKey, projects, (c) => `/api/tasks/notes/summary?project=${q(c)}`, 'notes')
  const evidenceQ = useSummary<number>('evidence', boardKey, projects, (c) => `/api/tasks/evidence/summary?project=${q(c)}`, 'evidence')
  const linksKey = useMemo(() => [...BOARD_KEY, 'links', boardKey, joined] as const, [boardKey, joined])
  const linksQ = useQuery({
    queryKey: linksKey,
    queryFn: async ({ signal }) => {
      const seen = new Set<string>()
      const merged: TaskLink[] = []
      for (const d of await each<{ links?: TaskLink[] }>(projects, (c) => `/api/tasks/links?project=${q(c)}`, signal)) {
        for (const l of Array.isArray(d?.links) ? d.links : []) {
          if (seen.has(l.id)) continue
          seen.add(l.id)
          merged.push(l)
        }
      }
      return merged
    },
    placeholderData: (prev, prevQuery) => sameBoard(prev, prevQuery, boardKey),
  })

  // What could not be read, said once per failure — not on every retry.
  const failed = [
    mentionsQ.failed && t('chat mentions'), sinceQ.failed && t('time in the column'), notesQ.failed && t('notes'),
    evidenceQ.failed && t('evidence'), linksQ.isError && t('links'),
  ].filter(Boolean).join(', ')
  useEffect(() => {
    if (failed) toast.error(t('Could not load: {what}', { what: failed }), { description: t('The cards show the last loaded values.') })
  }, [failed])

  const setTasks = useCallback((u: TaskRow[] | ((cur: TaskRow[]) => TaskRow[])) => {
    // Dropped synchronously, and the cache goes back to what it held before
    // that refetch began — then the edit lands on it. The write that follows
    // moves the freshness stamp, which asks again.
    void qc.cancelQueries({ queryKey: tasksKey })
    qc.setQueryData<TaskRow[]>(tasksKey, (cur) => (typeof u === 'function' ? u(cur ?? []) : u))
  }, [qc, tasksKey])
  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: BOARD_KEY }), [qc])
  const reloadLinks = useCallback(() => qc.invalidateQueries({ queryKey: linksKey }), [qc, linksKey])

  return {
    tasks: tasksQ.data ?? (EMPTY_TASKS as TaskRow[]),
    setTasks,
    loading: tasksQ.isLoading,
    loadError: tasksQ.error ? String((tasksQ.error as Error).message ?? tasksQ.error) : null,
    mentions: mentionsQ.data, statusSince: sinceQ.data, noteCounts: notesQ.data, evidenceCounts: evidenceQ.data,
    links: linksQ.data ?? (EMPTY_TASKS as unknown as TaskLink[]),
    refresh, reloadLinks,
  }
}
const EMPTY_TASKS: never[] = []
