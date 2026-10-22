/**
 * Skills — the data layer shared by the skills page variants.
 *
 * A skill is a folder agents load when a task matches: SKILL.md and the files
 * it links (backend/skilllib.py). Slightly Parallel keeps every version, writes copies
 * into projects' .claude/skills and .agents/skills, watches those copies for
 * edits, and counts the turns each skill ran in. The detail carries all of it;
 * a page reads it for the skills on screen and the one opened (near.ts).
 */

import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'

import { getJson, postJson } from '../../lib/getJson'
import { settled, type Kept, type VisionRow } from '../visions/data'
import { useNear } from '../visions/near'

interface SkillRow extends VisionRow {
  /** The folder name agents see. Empty until the first draft. */
  name: string | null
  /** What agents read when they choose a skill. */
  description: string | null
  /** draft · active · archived */
  status: string | null
}

interface SkillVersion {
  n: number
  at: string
  how: string
  note: string
  skill_md: string
  /** Relative path → text, besides SKILL.md. */
  files: Record<string, string>
  hash: string
}

interface SkillCheck {
  level: 'error' | 'warning'
  text: string
}

export interface SkillInstall {
  skill_id: string
  project: string
  path: string
  name: string
  version: number
  written_at: string
  /** fresh · stale (an older version) · changed (edited on disk) · missing */
  status: 'fresh' | 'stale' | 'changed' | 'missing'
  /** The files a changed copy no longer matches, SKILL.md included. Empty otherwise. */
  differs: string[]
}

interface SkillCopy {
  project: string
  path: string
  skill_md: string
  files: Record<string, string>
  differs: string[]
}

/** A copy as it is on disk — read to show what a hand edit changed. */
export function useSkillCopy(id: string, project: string) {
  return useQuery({
    queryKey: ['skills', 'copy', id, project],
    enabled: Boolean(id && project),
    queryFn: ({ signal }) =>
      getJson<SkillCopy>(`/api/skills/${id}/copy?project=${encodeURIComponent(project)}`, signal),
    staleTime: 10_000,
  })
}

interface SkillUse {
  at: string
  project: string
  agent_id: string
  session_id: string
  turn: number
  /** auto — the agent chose it; typed — the person typed /name. */
  how: string
}

interface SkillUsage {
  uses: number
  recent: number
  days: number
  projects: string[]
  last_used: string
  sessions: SkillUse[]
}

export interface Skill {
  row: SkillRow
  /** The message it was kept from (empty for a skill written on the page) and every version. */
  kept: Kept | null
  current: SkillVersion | null
  checks: SkillCheck[]
  installs: SkillInstall[]
  usage: SkillUsage | null
  /** Its detail is still to come: only the row is known. */
  pending?: boolean
}

interface SkillDetail {
  metadata: SkillRow
  kept?: Kept
  skill?: { current: SkillVersion | null; checks: SkillCheck[]; installs: SkillInstall[]; usage: SkillUsage }
}

/**
 * Every skill, newest first; the versions, checks, copies and usage of the
 * ones `near` holds — the page watches its list rows and wants the open one.
 */
export function useSkills(project = '') {
  const near = useNear()
  const list = useQuery({
    queryKey: ['skills', project],
    queryFn: ({ signal }) =>
      getJson<{ skills: SkillRow[] }>(`/api/skills?limit=500${project ? `&project=${encodeURIComponent(project)}` : ''}`, signal),
  })
  const rows = useMemo(() => list.data?.skills ?? [], [list.data])
  const details = useQueries({
    queries: rows.map((r) => ({
      queryKey: ['skills', 'one', r.id, r.versions_n ?? 0, r.tags ?? '', r.status ?? ''],
      queryFn: ({ signal }: { signal: AbortSignal }) => getJson<SkillDetail>(`/api/skills/${r.id}`, signal),
      enabled: near.has(r.id),
      // Copies on disk and usage change without the row changing.
      // A key change (a new version, a status) keeps the last detail on screen while the next one loads.
      placeholderData: keepPreviousData,
    })),
  })
  const skills: Skill[] = rows.map((r, i) => {
    const q = details[i]
    if (!q || !settled(q)) {
      return { row: r, kept: null, current: null, checks: [], installs: [], usage: null, pending: true }
    }
    const d = q.data
    return {
      row: d?.metadata ?? r,
      kept: d?.kept ?? null,
      current: d?.skill?.current ?? null,
      checks: d?.skill?.checks ?? [],
      installs: d?.skill?.installs ?? [],
      usage: d?.skill?.usage ?? null,
    }
  })
  return { list, skills, loading: list.isLoading, error: list.isError, near }
}

export interface UsageSummary {
  days: number
  skills: Record<string, { uses: number; recent: number; typed: number; projects: string[]; last_used: string }>
  /** Skills that ran but are not in Slightly Parallel — plugin or hand-made skills. */
  unknown: Array<{ name: string; uses: number; recent: number; typed: number; projects: string[]; last_used: string }>
}

export function useSkillUsage(days = 30) {
  return useQuery({
    queryKey: ['skills', 'usage', days],
    queryFn: ({ signal }) => getJson<UsageSummary>(`/api/skills/usage?days=${days}`, signal),
  })
}

/** The project code that installs into the home folders every agent on this machine reads. */
export const ALL_PROJECTS = 'all'

/** A skill folder on this machine that Slightly Parallel does not keep. */
export interface FoundSkill {
  name: string
  description: string
  hash: string
  files_n: number
  lines: number
  /** Times agents ran a skill of this name. */
  uses: number
  /** A skill in Slightly Parallel already has this name. */
  clash: boolean
  /** Every folder holding this same content; `project` is "all" for the home folders. */
  where: Array<{ project: string; path: string }>
}

export function useFoundSkills() {
  return useQuery({
    queryKey: ['skills', 'found'],
    queryFn: ({ signal }) => getJson<{ found: FoundSkill[] }>('/api/skills/found', signal).then((d) => d.found),
    staleTime: 60_000,
  })
}

/** Everything the operator does to skills. Each refreshes the skills it touches. */
export function useSkillWrites() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['skills'] })
  return {
    create: useMutation({
      mutationFn: (body: { skill_md: string; files?: Record<string, string>; project?: string; tags?: string }) =>
        postJson('/api/skills/new', { ...body, actor: 'operator' }) as Promise<SkillDetail>,
      onSuccess: refresh,
    }),
    draft: useMutation({
      mutationFn: ({ id, ...body }: { id: string; skill_md: string; files?: Record<string, string>; note?: string }) =>
        postJson(`/api/skills/${id}/draft`, { ...body, actor: 'operator' }) as Promise<SkillDetail>,
      onSuccess: refresh,
    }),
    /** Take a folder from "Not in Slightly Parallel" in. The folder on disk is not changed. */
    takeIn: useMutation({
      mutationFn: ({ path, tags }: { path: string; tags?: string }) =>
        postJson('/api/skills/import', { path, tags: tags ?? '', actor: 'operator' }) as
          Promise<SkillDetail & { skipped: string[] }>,
      onSuccess: refresh,
    }),
    setFields: useMutation({
      mutationFn: ({ id, ...fields }: { id: string; status?: string; tags?: string }) =>
        postJson(`/api/skills/${id}/update`, { ...fields, actor: 'operator' }),
      onSuccess: refresh,
    }),
    preview: useMutation({
      mutationFn: ({ id, project }: { id: string; project: string }) =>
        postJson(`/api/skills/${id}/install`, { project, dry_run: true, actor: 'operator' }) as Promise<InstallResult>,
    }),
    /** `force` replaces a copy that was edited on disk; without it the server refuses (422). */
    install: useMutation({
      mutationFn: ({ id, project, force }: { id: string; project: string; force?: boolean }) =>
        postJson(`/api/skills/${id}/install`, { project, actor: 'operator', ...(force ? { force: true } : {}) }) as Promise<InstallResult>,
      onSuccess: refresh,
    }),
    /** `force` removes a copy that was edited on disk; without it the server refuses (422). */
    uninstall: useMutation({
      mutationFn: ({ id, project, force }: { id: string; project: string; force?: boolean }) =>
        postJson(`/api/skills/${id}/uninstall`, { project, actor: 'operator', ...(force ? { force: true } : {}) }) as Promise<{ removed: string[] }>,
      onSuccess: refresh,
    }),
    keepDisk: useMutation({
      mutationFn: ({ id, project }: { id: string; project: string }) =>
        postJson(`/api/skills/${id}/keep-disk`, { project, actor: 'operator' }) as Promise<SkillDetail>,
      onSuccess: refresh,
    }),
    backfill: useMutation({
      mutationFn: () => postJson('/api/skills/usage/backfill', {}) as Promise<{ transcripts: number; added: number }>,
      onSuccess: refresh,
    }),
  }
}

export type SkillWrites = ReturnType<typeof useSkillWrites>

export interface InstallResult {
  project: string
  paths: string[]
  /** changed — a dry run found the copy edited on disk; a real install needs `force`. */
  action: 'created' | 'updated' | 'unchanged' | 'changed'
  version: number
  dry_run: boolean
}

/** A skill's title: its folder name once drafted, else the message it was kept from. */
export function skillTitle(s: Skill): string {
  return s.row.name || s.row.l1 || s.row.id
}

/** The worst state among a skill's copies — what needs the operator first. */
export function worstInstall(s: Skill): SkillInstall['status'] | null {
  for (const st of ['changed', 'missing', 'stale', 'fresh'] as const) {
    if (s.installs.some((i) => i.status === st)) return st
  }
  return null
}

/**
 * A kept #skill with no SKILL.md yet: the agent's draft is still to come.
 * Before the detail is read the row says it: a draft writes `versions_n`.
 */
export const awaitingDraft = (s: Skill) => (s.pending ? !(s.row.versions_n ?? 0) : !s.current)

export const isArchived = (s: Skill) => s.row.status === 'archived'

export const hasErrors = (s: Skill) => s.checks.some((c) => c.level === 'error')

/** The template the page's New skill starts from. */
export const NEW_SKILL = `---
name: new-skill
description: What this skill does. Use when …
---

1. First step.
2. Second step.

Check: how to know it worked.
`
