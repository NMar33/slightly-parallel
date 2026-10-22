/**
 * The prompt library's data layer — shared by the page and every variant.
 *
 * Variants differ in how they arrange the library, never in what it says, so
 * the types, the fetching and the derived numbers live here once. A variant
 * that computed its own "times sent" could disagree with the page beside it,
 * and the one thing this feature sells is that its counts are trustworthy.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fail, getJson, postJson } from '../../lib/getJson'
import { t, tn } from '../../i18n/scope/system'

interface Metrics {
  uses: number
  /** Sends after the first. The one number that is not true by construction. */
  reuses: number
  first_used: string
  /** Sends that matched a version byte for byte. `uses - exact` had a line swapped. */
  exact: number
  clustered: boolean
  sessions: number
  turns: number
  minutes: number
  projects: string[]
  tasks: string[]
  last_used: string
  by_version: Record<string, number>
  /** Sends per day, Slightly Parallel YYMM-DD. */
  by_day: Record<string, number>
}

/** What followed one send, recomputed from the log. Facts, never a rating. */
export interface Facts {
  turns_after: number
  follow_ups: number
  minutes: number
  reply_words: number
  produced: Record<string, number>
  task_moved: Array<{ task_id: string; from: string; to: string }>
  session_turns: number
}

/** The operator's judgement of one run. Ordinal steps in their own words. */
export interface Rating {
  task_success: string
  regression: string
  intervention: string
  score: number | null
  note: string
  rated_at: string
}

export type Scales = {
  task_success: string[]
  regression: string[]
  intervention: string[]
  score: [number, number]
}

export interface Send {
  at: string
  project: string
  agent_id: string
  session_id: string
  turn: number
  words: number
  head: string
  version: number | null
  exact: boolean
  facts: Facts
  rating: Rating | null
}

export interface VersionRollup {
  sends: number
  rated: number
  dist: Record<string, Record<string, number>>
  score_median: number | null
  follow_ups_median: number | null
}

export interface PromptRow {
  id: string
  title: string
  project: string
  agent_id: string
  created_date: string
  created_time: string
  tags: string
  status: string
  source: string
  versions_n: number
  /** Operator-kept fields: what they concluded, beside what was derived. */
  marks: Record<string, string>
  /** The current wording's judgement, when given. */
  current_rating?: Rating | null
  current_version?: number
  /** What the prompt caused, over the distinct sessions it was sent in. */
  made?: { commits: number; files: number; add: number; del: number; tasks: number }
  preview: string
  chars: number
  words: number
  metrics: Metrics
}

export interface Version {
  n: number
  at: string
  how: string
  note: string
  text: string
  chars: number
  words: number
  print?: string
  /** The operator's judgement of this wording — one per version. */
  rating?: Rating | null
}

export interface Detail {
  prompt: PromptRow
  versions: Version[]
  current: Version | null
  metrics: Metrics
  sends: Send[]
  rollup: Record<string, VersionRollup | { sends: number; rated: number }>
  scales: Scales
  mark_names: string[]
}

export interface Candidate {
  cluster: string
  sends: number
  first_at: string
  last_at: string
  projects: string[]
  words: number
  text: string
  title: string
  /** Distinct wordings across the sends — 1 means pasted identically. */
  wordings: number
}

interface LibraryPayload {
  prompts: PromptRow[]
  adopted: string[]
  counts: Record<string, number>
  mark_names: string[]
}

const BASE = '/api/prompt-library'

export function useLibrary(status = 'active') {
  return useQuery({
    queryKey: ['prompt-library', status],
    queryFn: ({ signal }) => getJson<LibraryPayload>(`${BASE}?status=${status}`, signal),
  })
}

/**
 * What the operator keeps sending but never filed.
 *
 * The `#prompt` tag asks them to know a message matters before it has proved
 * that it does, and a prompt usually earns its place on the fourth send. This
 * is the door that needs nothing from them.
 */
export function useCandidates() {
  return useQuery({
    queryKey: ['prompt-library', 'candidates'],
    queryFn: ({ signal }) => getJson<{ candidates: Candidate[]; min_sends: number }>(`${BASE}/candidates`, signal),
  })
}

export function usePrompt(id: string | null) {
  return useQuery({
    queryKey: ['prompt-library', 'one', id],
    queryFn: ({ signal }) => getJson<Detail>(`${BASE}/${id}`, signal),
    enabled: Boolean(id),
  })
}

/**
 * Rewrite, rename, tag, archive — the writes, sharing one refresh. A failed
 * rename, archive, new prompt or keep says so; the rewrite and the ratings
 * say it where they are made.
 */
export function useLibraryWrites(id?: string) {
  const qc = useQueryClient()
  const after = () => {
    void qc.invalidateQueries({ queryKey: ['prompt-library'] })
  }
  return {
    rewrite: useMutation({
      mutationFn: (v: { id?: string; text: string; note: string }) =>
        postJson(`${BASE}/${v.id ?? id}/version`, { text: v.text, note: v.note }),
      onSuccess: after,
    }),
    update: useMutation({
      mutationFn: (v: { id?: string } & Record<string, unknown>) => {
        const { id: target, ...fields } = v
        return postJson(`${BASE}/${target ?? id}/update`, fields)
      },
      onSuccess: after,
      onError: fail,
    }),
    write: useMutation({
      mutationFn: (v: { title: string; text: string; tags?: string }) =>
        postJson(BASE, v),
      onSuccess: after,
      onError: fail,
    }),
    keep: useMutation({
      // The prompt it filed, as the detail reads it.
      mutationFn: (cluster: string) =>
        postJson<Detail>(`${BASE}/candidates/${cluster}/keep`, {}),
      onSuccess: after,
      onError: fail,
    }),
    rateVersion: useMutation({
      mutationFn: (v: { id?: string; n: number } & Partial<Record<keyof Rating, unknown>>) => {
        const { id: target, n, ...fields } = v
        return postJson(`${BASE}/${target ?? id}/versions/${n}/rating`, fields)
      },
      onSuccess: after,
    }),
    rate: useMutation({
      mutationFn: (v: { id?: string; session_id: string; turn: number } & Partial<Record<keyof Rating, unknown>>) => {
        const { id: target, session_id, turn, ...fields } = v
        return postJson(`${BASE}/${target ?? id}/runs/${session_id}/${turn}`, fields)
      },
      onSuccess: after,
    }),
  }
}

export function tagList(row: PromptRow): string[] {
  return (row.tags ?? '').split(/[\s,]+/).filter(Boolean)
}

export function matches(row: PromptRow, needle: string): boolean {
  if (!needle) return true
  return `${row.title ?? ''} ${row.preview ?? ''} ${row.tags ?? ''}`
    .toLowerCase()
    .includes(needle.toLowerCase())
}

export function ageOf(iso: string): string {
  if (!iso) return t('never')
  const ms = Date.now() - new Date(iso).getTime()
  const min = Math.max(0, Math.round(ms / 60000))
  if (min < 60) return t('{n}m ago', { n: min })
  const h = Math.round(min / 60)
  if (h < 48) return t('{n}h ago', { n: h })
  const d = Math.round(h / 24)
  return d < 60 ? t('{n}d ago', { n: d }) : t('{n}mo ago', { n: Math.round(d / 30) })
}

/**
 * "reused 8× · 6 wordings" — the same phrasing everywhere.
 *
 * Two numbers were cut from this line and are not coming back. `turns` and
 * `minutes` belong to the session a send landed in, not to the prompt: a
 * two-word test prompt "produced" 11 turns and 56 minutes because that is how
 * long the night was. And a prompt filed from a message it was sent in starts
 * at one use, so "sent once" was the act of filing wearing the costume of
 * evidence — the headline is `reuses`, which nothing but real repetition can
 * raise above zero.
 */
export function usageWords(m: Metrics, versions = 0): string[] {
  const out = [
    m.uses === 0
      ? t('never sent')
      : m.reuses === 0
        ? t('sent once')
        : t('reused {n}×', { n: m.reuses }),
  ]
  // Nine sends, six of them reworded: saying so is the difference between a
  // number believed and one reverse-engineered.
  if (m.clustered && m.exact < m.uses) out.push(t('{n} reworded', { n: m.uses - m.exact }))
  if (m.projects.length > 1) out.push(tn(m.projects.length, '{n} project', '{n} projects'))
  if (m.tasks.length) out.push(tn(m.tasks.length, '{n} task', '{n} tasks'))
  if (versions > 1) out.push(tn(versions, '{n} version', '{n} versions'))
  return out
}

/** Where a send can be opened: the session, scrolled to that turn, ringed. */
export function chatHref(s: Pick<Send, 'session_id' | 'turn'>): string {
  return `/sessions#sel=${s.session_id}&turn=${s.turn}`
}

/** The label for a send's version: "v2", or "reworded" when it matched none exactly. */
export function versionLabel(s: Pick<Send, 'version'>): string {
  return s.version ? `v${s.version}` : t('reworded')
}

/** Every send of every prompt, by session then turn — so any chat can tag the turns that were one. */
interface SendMark {
  prompt_id: string
  title: string
  version: number | null
  exact: boolean
  rating: { task_success: string; score: number | null } | null
}

export function useSendMarks() {
  return useQuery({
    queryKey: ['prompt-library', 'marks'],
    queryFn: ({ signal }) => getJson<{ marks: Record<string, Record<string, SendMark>> }>(`${BASE}/marks`, signal),
    staleTime: 60_000,
  })
}
