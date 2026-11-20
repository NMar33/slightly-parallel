/**
 * SP Aqua's reads and writes against the terminal API.
 *
 * The list of terminals is the one every page shares (`useTerminals`), read
 * every two seconds while this window is in front. The routes tk_bbb84183
 * adds — groups, sleep and wake, restore, typing — are detected, not
 * assumed: a server without one answers 404 and the control it drives is
 * not drawn.
 */

import { useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { getJson, postJson } from '../../../lib/getJson'
import { useTerminals } from '../../../lib/terminal'
import type { AquaSession, Group, Role } from './model'
import { t } from '../../../i18n/scope/aqua'

/** A route this server does not have: null, so the caller hides what needs it. */
const absent = (e: unknown): null => {
  const status = (e as { status?: number } | null)?.status
  if (status === 404 || status === 405) return null
  throw e
}

export function useSessions() {
  const q = useTerminals(true)
  const sessions = useMemo(() => (q.data?.sessions ?? []) as unknown as AquaSession[], [q.data])
  // The rows carry `asleep` once the server knows sleep: the switch shows then.
  const canSleep = sessions.some((s) => 'asleep' in s || 'role' in s)
  return { sessions, loaded: !!q.data, canSleep }
}

export function useGroups() {
  return useQuery({
    queryKey: ['terminal', 'groups'],
    queryFn: ({ signal }) => getJson<{ groups: Group[] }>('/api/terminal/groups', signal).then((d) => d.groups ?? [], absent),
    staleTime: 30_000,
    retry: false,
  })
}

export interface RestoreRow { id: string; label: string; project?: string }
export interface RestoreResult { id: string; label: string; ok: boolean; error?: string }

export function useRestoreNeeded() {
  return useQuery({
    queryKey: ['terminal', 'restore'],
    queryFn: ({ signal }) => getJson<{ needed: number; sessions: RestoreRow[] }>('/api/terminal/restore', signal).catch(absent),
    staleTime: Infinity,
    retry: false,
  })
}

/** The snapshot a tile shows: the terminal's screen as text, read slowly and only while asked for. */
export function useSnapshot(s: AquaSession, on: boolean) {
  const tmux = s.backend === 'tmux'
  return useQuery({
    queryKey: ['terminal', 'snapshot', s.id],
    queryFn: ({ signal }) => postJson<{ text: string }>(`/api/terminal/sessions/${encodeURIComponent(s.id)}/capture`, { mode: 'screen' }, signal).then((d) => d.text ?? ''),
    enabled: on && tmux,
    refetchInterval: on && tmux ? 5000 : false,
    refetchIntervalInBackground: false,
    staleTime: 4000,
    retry: false,
  })
}

const failed = (what: string) => (e: unknown) => {
  toast.error(t('{what}: {error}', { what, error: e instanceof Error ? e.message : String(e) }))
  return null
}

export function useAquaActions() {
  const qc = useQueryClient()
  const refresh = () => void qc.invalidateQueries({ queryKey: ['terminal'] })
  const sid = (id: string) => `/api/terminal/sessions/${encodeURIComponent(id)}`
  return {
    /** A new terminal, handed back (never shown in the app's drawer). */
    open: async (req: { kind: 'shell' | 'resume' | 'start'; project?: string; cwd?: string; label?: string; command?: string; agent?: string; task_id?: string; role?: Role; group?: string }) => {
      const d = await postJson<{ session: AquaSession }>('/api/terminal/sessions', { ...req, actor: 'operator' }).catch(failed(t('The terminal did not open')))
      refresh()
      return d?.session ?? null
    },
    close: async (id: string) => { await postJson(`${sid(id)}/close`, { actor: 'operator' }).catch(failed(t('The terminal did not close'))); refresh() },
    rename: async (id: string, label: string) => { await postJson(`${sid(id)}/rename`, { label, actor: 'operator' }).catch(failed(t('The terminal was not renamed'))); refresh() },
    sleep: async (id: string) => { await postJson(`${sid(id)}/sleep`, { actor: 'operator' }).catch(failed(t('The chat did not go to sleep'))); refresh() },
    wake: async (id: string) => { await postJson(`${sid(id)}/wake`, { actor: 'operator' }).catch(failed(t('The chat did not wake'))); refresh() },
    setGroup: async (id: string, group: string) => {
      const result = await postJson(`${sid(id)}/group`, { group, actor: 'operator' }).catch(failed(t('The chat did not move')))
      refresh()
      return !!result
    },
    newGroup: async (name: string, color: number, project?: string, tabs?: string[]) => {
      const d = await postJson<{ group: Group }>('/api/terminal/groups', { name, color, project, tabs, actor: 'operator' }).catch(failed(t('The group was not made')))
      refresh()
      return d?.group ?? null
    },
    moveTabs: async (tabs: string[], project: string, group: string) => {
      const result = await postJson('/api/terminal/groups/move', { tabs, project, group, actor: 'operator' }).catch(failed(t('The tabs did not move')))
      refresh()
      return !!result
    },
    editGroup: async (gid: string, patch: { name?: string; color?: number }) => {
      await postJson(`/api/terminal/groups/${encodeURIComponent(gid)}`, { ...patch, actor: 'operator' }).catch(failed(t('The group was not changed')))
      refresh()
    },
    removeGroup: async (gid: string) => {
      await postJson(`/api/terminal/groups/${encodeURIComponent(gid)}/remove`, { actor: 'operator' }).catch(failed(t('The group was not removed')))
      refresh()
    },
    restore: async (): Promise<RestoreResult[] | null> => {
      const d = await postJson<{ results: RestoreResult[] }>('/api/terminal/restore', { actor: 'operator' }).catch(failed(t('Restore did not run')))
      refresh()
      return d?.results ?? null
    },
  }
}

/** One typing tick: 'gone' when the server has no such route. */
export async function sendTyping(sid: string, keys: number): Promise<'ok' | 'gone'> {
  try {
    await postJson('/api/terminal/typing', { sid, keys, actor: 'operator' })
    return 'ok'
  } catch (e) {
    const status = (e as { status?: number }).status
    return status === 404 || status === 405 ? 'gone' : 'ok'
  }
}
