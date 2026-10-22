/**
 * The Timer page: time across every project. On top, the Timer tab's own
 * head counted over all projects — the numbers, today as the dial, the
 * 26-week grid. Below, the ledger: a row a block under its project, with
 * the project's mode and a pill that starts or stops the block, the last
 * seven days and the totals; then the entries of those days. Shares, notes
 * and edits to an entry stay on each project's Timer tab.
 */

import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Timer } from 'lucide-react'

import { PageHeader } from '../../components/PageHeader'

import { toast } from '../../components/primitives'
import { Segmented } from '../../components/Segmented'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { api, qk } from '../../lib/api'
import { getJson, postJson, refused } from '../../lib/getJson'
import { TIME_AUTO_KEY, modeOf, useTimeAuto, type TimeMode } from '../../lib/timer'
import { OPERATOR_ACTOR } from '../project/types'
import type { TimeEntry } from '../project/timeEntry'
import { useNow } from '../../lib/clock'
import { useAllTasks, type SprintsAnswer } from '../tasks/data'
import { build, type Period } from './model'
import type { Block, TimeCtx } from './parts'
import { TIMER_GUIDE } from '../visions/guides'
import { PageGuide } from '../visions/parts'
import { formatDuration } from '../project/timeEntry'
import { Head } from './Head'
import { Ledger } from './Ledger'

import { t, tn } from '../../i18n/scope/views'
const ENTRIES_KEY = ['time-entries-all'] as const
const NO_ENTRIES: TimeEntry[] = []

export function TimePage() {
  useEffect(() => { document.title = t('Timer — Slightly Parallel') }, [])
  const qc = useQueryClient()
  const [period, setPeriod] = useState<Period>('30')

  // No poll: an entry written is a change under the data root, and the
  // freshness stamp (area "tasks") asks for the entries again.
  const entries = useQuery({
    queryKey: ENTRIES_KEY,
    queryFn: ({ signal }) => getJson<{ time_entries: TimeEntry[] }>('/api/time-entries?limit=5000', signal),
  })
  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal) })
  const sprints = useQuery({
    queryKey: ['time-sprints-every'],
    queryFn: ({ signal }) => getJson<SprintsAnswer>('/api/sprints?limit=500', signal).catch(refused<SprintsAnswer>({ sprints: [] })),
  })
  // For the titles of the tasks the entries name: the shared read of every task.
  const tasks = useAllTasks()
  const auto = useTimeAuto().data

  const all = entries.data?.time_entries ?? NO_ENTRIES
  const anyOpen = all.some((e) => !e.ended_at && !e.paused_at)
  // The page's totals are minutes: counted again every ten seconds while a
  // timer runs. The running clocks themselves are `Live`, a second apiece.
  const nowMs = useNow(anyOpen ? 10_000 : 60_000)
  const codes = useMemo(() => (snapshot.data?.projects ?? []).map((p) => p.code), [snapshot.data])
  const m = useMemo(() => build(all, codes, nowMs, period), [all, codes, nowMs, period])

  const c: TimeCtx = useMemo(() => {
    const refresh = () => {
      void qc.invalidateQueries({ queryKey: ENTRIES_KEY })
      void qc.invalidateQueries({ queryKey: ['time-running'] })
      void qc.invalidateQueries({ queryKey: ['time-summary-all'] })
      void qc.invalidateQueries({ queryKey: TIME_AUTO_KEY })
    }
    const act = (work: Promise<unknown>) => {
      void work.then(refresh).catch((e) => toast.error(String((e as Error).message ?? e)))
    }
    const sprintRows = sprints.data?.sprints ?? []
    const sprintNames = new Map(sprintRows.map((s) => [s.id, s.name]))
    const titles = new Map((tasks.data ?? []).map((it) => [it.id, it.title ?? '']))
    return {
      m, period, nowMs, entries: all,
      mode: (code: string) => modeOf(auto, code),
      blocks: (code: string): Block[] => [
        ...sprintRows
          .filter((s) => s.status === 'active' && (s.projects ?? '').split(',').map((x) => x.trim()).includes(code))
          .map((s) => ({ id: s.id, name: s.name })),
        { id: '', name: t('Everything else') },
      ],
      sprintName: (id: string) => sprintNames.get(id) ?? id,
      taskTitle: (id: string) => titles.get(id) ?? id,
      start: (code: string, sprintId = '') =>
        act(postJson('/api/time/start', { project: code, agent_id: OPERATOR_ACTOR, sprint_id: sprintId })),
      stop: (ids: string[]) => act(Promise.all(ids.map((id) => postJson(`/api/time/${encodeURIComponent(id)}/stop`, {})))),
      pauseResume: (e: TimeEntry) => act(postJson(`/api/time/${encodeURIComponent(e.id)}/${e.paused_at ? 'resume' : 'pause'}`, {})),
      setMode: (code: string, mode: TimeMode) => act(postJson('/api/time/auto/mode', { project: code, mode })),
    }
  }, [m, period, nowMs, all, auto, sprints.data, tasks.data, qc])

  return (
    <div className="flex flex-col gap-16 min-w-0">
      <PageHeader
        variant="tool"
        title={t('Timer')}
        sub={entries.data ? `${tn(m.projects.length, '{n} project', '{n} projects')} · ${t('{duration} today', { duration: formatDuration(m.todaySec) })} · ${t('{duration} this week', { duration: formatDuration(m.weekSec) })}` : undefined}
        actions={(
          <Segmented label={t('Period')} shape="pill" height={20} value={period} onChange={setPeriod}
            options={[['7', t('7 days')], ['30', t('30 days')], ['90', t('90 days')]] as const} />
        )}
      />
      <PageGuide id="timer" guide={TIMER_GUIDE} examples={0} />

      {entries.isLoading && <LoadingSkeleton variant="row" count={6} />}
      {entries.isError && <ErrorBanner title={t('The time entries could not be read')} onRetry={() => void entries.refetch()} hideDismiss />}
      {entries.data && m.projects.length === 0 && (
        <EmptyState icon={<Timer size={24} aria-hidden />} title={t('There are no projects yet.')}
          subtitle={t('Add a project in Setup. Its timer appears here.')} />
      )}
      {entries.data && m.projects.length > 0 && (
        <>
          <Head c={c} />
          <Ledger c={c} />
        </>
      )}
    </div>
  )
}
