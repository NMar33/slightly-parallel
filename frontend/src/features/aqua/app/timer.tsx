import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../../lib/getJson'
import { useTimeAuto, type TimeAuto } from '../../../lib/timer'
import type { ReactNode } from 'react'
import { projectColor } from '../../../utils/projectColor'
import { clockOf } from './health/healthModel'
import type { TimeEntry } from '../../project/timeEntry'
import { post } from './bridge'
import { t } from '../../../i18n/scope/aqua'
import type { WindowPreferences } from './WindowSettings'

const RUNNING_TIMER_REFETCH_MS = 30_000
const TIMER_TOTALS_REFETCH_MS = 60_000

export type ChipState = 'counting' | 'paused' | 'away' | 'off'

/** What the timer says about `project` now. Away first (a notice waits on
 *  you), then counting (a timer of yours or the smart timer runs), then
 *  paused (every open timer of the project is paused), else off. */
export function chipState(project: string, running: TimeEntry[], auto: Pick<TimeAuto, 'working' | 'away'> | undefined): ChipState {
  if (auto?.away.some((a) => a.project === project)) return 'away'
  const open = running.filter((e) => e.project === project && !e.ended_at)
  if (open.some((e) => !e.paused_at) || auto?.working.some((w) => w.project === project)) return 'counting'
  if (open.length) return 'paused'
  return 'off'
}

const WORD: Record<ChipState, string> = {
  counting: t('counting'),
  paused: t('paused'),
  away: t('away'),
  off: t('timer off'),
}

/** The Timer page, in the browser: through the window's bridge, or a new tab. */
export function openTimerPage() {
  const url = `${window.location.origin}/time`
  if (!post({ op: 'open', url })) window.open(url, '_blank', 'noopener')
}

type Summary = { today_min: number; today_agent_min?: number }

export function TimerGroup({ project, prefs, session }: { project: string; prefs: WindowPreferences; session?: ReactNode }) {
  const { projectTimer, totalTimer, showSessionTimer, timerOrder } = prefs
  // This window has no freshness stamp: the reads poll, slowly.
  const running = useQuery({
    queryKey: ['time-running'],
    queryFn: ({ signal }) => getJson<{ running: TimeEntry[] }>('/api/time/running', signal),
    refetchInterval: RUNNING_TIMER_REFETCH_MS, retry: false,
  })
  const mine = useQuery({
    queryKey: ['time-summary', project, projectTimer],
    queryFn: ({ signal }) => getJson<Summary>(`/api/time/summary?project=${encodeURIComponent(project)}${projectTimer === 'agents' ? '&agent_work=true' : ''}`, signal),
    refetchInterval: TIMER_TOTALS_REFETCH_MS, retry: false, enabled: !!project && projectTimer !== 'off',
  })
  const all = useQuery({
    queryKey: ['time-summary-all', totalTimer],
    queryFn: ({ signal }) => getJson<Summary>(totalTimer === 'agents' ? '/api/time/summary?agent_work=true' : '/api/time/summary', signal),
    refetchInterval: TIMER_TOTALS_REFETCH_MS, retry: false, enabled: totalTimer !== 'off',
  })
  const auto = useTimeAuto()
  const state = chipState(project, running.data?.running ?? [], auto.data)
  const rows = {
    project: { source: projectTimer, data: project ? mine.data : undefined },
    total: { source: totalTimer, data: all.data },
  }
  const enabled = timerOrder.filter((kind) => kind === 'session'
    ? showSessionTimer && session
    : rows[kind].source !== 'off' && rows[kind].data)
  if (!enabled.length) return null

  return (
    <span data-timer-group className="ml-4 inline-flex shrink-0 items-center gap-2">
      {enabled.map((kind) => {
        if (kind === 'session') return <span key={kind} data-timer-kind={kind} className="inline-flex">{session}</span>
        const { source, data } = rows[kind]
        const minutes = source === 'agents' ? data?.today_agent_min : data?.today_min
        const time = minutes === undefined ? '—' : clockOf(minutes)
        const label = kind === 'project' ? `${t('Project timer')} · ${project}` : t('Total timer')
        const sourceLabel = source === 'agents' ? t('Agent work time') : t('My work time')
        const title = `${label} · ${time} · ${sourceLabel} · ${WORD[state]}. ${t('Click to open the Timer page.')}`
        return (
          <button key={kind} type="button" data-nodrag data-timer-kind={kind} data-timer={state} data-timer-source={source}
            onClick={openTimerPage} title={title} aria-label={title}
            className="aq-btn shrink-0 !px-4 !text-11 !leading-[1] font-mono tabular-nums whitespace-nowrap text-tertiary">
            {kind === 'project'
              ? <span aria-hidden data-project-timer-dot className="size-[6px] rounded-full shrink-0" style={{ backgroundColor: projectColor(project) }} />
              : <span aria-hidden>Σ</span>}
            {time}
          </button>
        )
      })}
    </span>
  )
}
