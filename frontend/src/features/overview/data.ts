/*
 * What the home page reads besides the year of sessions: the snapshot every
 * page holds, the work waiting on the operator and the newest standup of each
 * project. Each read fails alone; a part with no data draws nothing.
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api, lensApi, qk, type LensRow, type SnapshotResponse } from '../../lib/api'
import { getJson } from '../../lib/getJson'
import { useDayStart } from '../../lib/clock'
import { formatYYMMDD, stampMs } from '../../utils/dateUtils'

export const DAYS = 30

export interface Standup {
  id: string
  project: string
  agent_id: string
  created_date: string
  created_time: string
  for_date?: string
  l1: string
}

/** The last DAYS days as YYMM-DD, oldest first, today last. */
export function lastDays(now = new Date(), n = DAYS): string[] {
  const out: string[] = []
  for (let i = n - 1; i >= 0; i -= 1) out.push(formatYYMMDD(new Date(now.getFullYear(), now.getMonth(), now.getDate() - i)))
  return out
}

export function useOverviewData(fetcher: (signal?: AbortSignal) => Promise<SnapshotResponse> = api.snapshot) {
  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => fetcher(signal), staleTime: 4_000 })
  const problems = useQuery({
    queryKey: qk.lensList('problems', { status: 'open', limit: 50 }),
    queryFn: ({ signal }) => lensApi.list('problems', 'problems', { status: 'open', limit: 50 }, signal),
    staleTime: 4_000,
  })
  const review = useQuery({
    queryKey: qk.lensList('tasks', { status: 'review', limit: 50 }),
    queryFn: ({ signal }) => lensApi.list('tasks', 'tasks', { status: 'review', limit: 50 }, signal),
    staleTime: 4_000,
  })
  const standups = useQuery({
    queryKey: ['overview', 'standups'],
    queryFn: ({ signal }) => getJson<{ standups: Standup[] }>('/api/standups?limit=60', signal),
    staleTime: 30_000,
  })
  const dayStart = useDayStart()
  const days = useMemo(() => lastDays(new Date(dayStart)), [dayStart])

  const latestStandup = useMemo(() => {
    const out = new Map<string, Standup>()
    for (const s of standups.data?.standups ?? []) {
      const have = out.get(s.project)
      if (!have || stampMs(s.created_date, s.created_time) > stampMs(have.created_date, have.created_time)) out.set(s.project, s)
    }
    return out
  }, [standups.data])

  return {
    snapshot: snapshot.data,
    loading: snapshot.isLoading,
    error: snapshot.error as Error | null,
    refetch: snapshot.refetch,
    problems: (problems.data?.rows ?? []) as LensRow[],
    review: (review.data?.rows ?? []) as LensRow[],
    days,
    latestStandup,
  }
}

export type OverviewData = ReturnType<typeof useOverviewData>

/** Agents with a turn in the last `minutes`. */
export function workingNow(data: OverviewData, minutes = 30): SnapshotResponse['agents'] {
  const since = Date.now() - minutes * 60_000
  return (data.snapshot?.agents ?? [])
    .filter((a) => {
      const ms = Date.parse(String(a.last_active ?? ''))
      return Number.isFinite(ms) && ms >= since
    })
    .sort((a, b) => String(b.last_active).localeCompare(String(a.last_active)))
}
