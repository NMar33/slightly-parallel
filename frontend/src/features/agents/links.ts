/**
 * Links between agents — the lines the operator draws on the timeline.
 *
 * A link is directed: `from` is the earlier lane, `to` the one it explains.
 * `kind` is the reason (branch · handoff · same-work · relates), `style` is
 * how the line is drawn (solid · dashed · dotted), `note` is what the dot
 * on it says. Stored in `agent_links.csv`; every write goes through the API.
 */

import { getJson, postJson, refused } from '../../lib/getJson'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { AgentBrief } from './profile'

import { t } from '../../i18n/scope/views'
export type AgentLinkKind = 'branch' | 'subagent' | 'handoff' | 'same-work' | 'relates'
export type AgentLinkStyle = 'solid' | 'dashed' | 'dotted'

export const LINK_KINDS: AgentLinkKind[] = ['branch', 'subagent', 'handoff', 'same-work', 'relates']
export const LINK_STYLES: AgentLinkStyle[] = ['solid', 'dashed', 'dotted']

export const LINK_KIND_LABEL: Record<AgentLinkKind, string> = {
  branch: t('branched from'),
  subagent: t('started a subagent'),
  handoff: t('handed over to'),
  'same-work': t('same work as'),
  relates: t('relates to'),
}

/** What the kind means, for the composer's helper line. */
export const LINK_KIND_HINT: Record<AgentLinkKind, string> = {
  branch: t('the second lane was started from the first (a /branch, a fork, a retry)'),
  subagent: t('the first ran the second as its subagent (an Agent call, a worker, a worktree)'),
  handoff: t('the first stopped and the second continued its work'),
  'same-work': t('both worked on one feature or task'),
  relates: t('worth seeing together, for a reason the note gives'),
}

export const LINK_DEFAULT_STYLE: Record<AgentLinkKind, AgentLinkStyle> = {
  branch: 'solid',
  subagent: 'solid',
  handoff: 'dashed',
  'same-work': 'dotted',
  relates: 'dotted',
}

/** SVG stroke-dasharray per style lives with the chart; re-exported here. */
export { LINK_DASH } from '../../components/AgentTimeline/AgentTimeline'

export interface AgentLink {
  id: string
  project: string
  from_id: string
  to_id: string
  kind: AgentLinkKind
  style: AgentLinkStyle
  note: string
  from_at: string
  to_at: string
  created_at: string
  actor: string
  from: AgentBrief
  to: AgentBrief
}

interface LinkDraft {
  from: string
  to: string
  kind: AgentLinkKind
  style?: AgentLinkStyle
  note?: string
  from_at?: string
  to_at?: string
}

async function fetchLinks(project: string, signal?: AbortSignal): Promise<AgentLink[]> {
  const d = await getJson<{ links?: unknown }>(`/api/agents/links?project=${encodeURIComponent(project)}`, signal)
  return Array.isArray(d?.links) ? (d.links as AgentLink[]) : []
}

export function useAgentLinks(project: string | undefined) {
  return useQuery({
    queryKey: ['agents', 'links', project ?? ''],
    queryFn: ({ signal }) => fetchLinks(project ?? '', signal),
    enabled: !!project,
    staleTime: 15_000,
  })
}

/** Create / update / delete, each invalidating what reads links. */
export function useLinkMutations(project: string | undefined) {
  const qc = useQueryClient()
  const done = () => {
    void qc.invalidateQueries({ queryKey: ['agents', 'links', project ?? ''] })
    void qc.invalidateQueries({ queryKey: ['agents', 'profiles', project ?? ''] })
    void qc.invalidateQueries({ queryKey: ['agents', 'profile'] })
  }
  const create = useMutation({
    mutationFn: (draft: LinkDraft) =>
      postJson('/api/agents/links', { ...draft, actor: 'operator' }) as Promise<{ link: AgentLink; created: boolean }>,
    onSuccess: done,
  })
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Pick<AgentLink, 'kind' | 'style' | 'note' | 'from_at' | 'to_at'>> }) =>
      postJson(`/api/agents/links/${encodeURIComponent(id)}/update`, patch) as Promise<{ link: AgentLink }>,
    onSuccess: done,
  })
  const remove = useMutation({
    mutationFn: (id: string) =>
      postJson(`/api/agents/links/${encodeURIComponent(id)}/delete`, {}) as Promise<{ deleted: string }>,
    onSuccess: done,
  })
  return { create, update, remove }
}

/** Rename + group — the two things an operator edits on an agent. */
export function useAgentEdits() {
  const qc = useQueryClient()
  const done = () => void qc.invalidateQueries()
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      postJson(`/api/agents/${encodeURIComponent(id)}/rename`, { name }),
    onSuccess: done,
  })
  const group = useMutation({
    mutationFn: ({ id, group }: { id: string; group: string }) =>
      postJson(`/api/agents/${encodeURIComponent(id)}/group`, { group }),
    onSuccess: done,
  })
  return { rename, group }
}

export async function fetchGroups(project: string, signal?: AbortSignal): Promise<Array<{ name: string; members: AgentBrief[] }>> {
  const d = await getJson<{ groups?: unknown }>(`/api/agents/groups?project=${encodeURIComponent(project)}`, signal)
    .catch(refused(null))
  return Array.isArray(d?.groups) ? d.groups : []
}
