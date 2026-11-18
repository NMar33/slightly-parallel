/**
 * The timer in the terminal window, at the right end of the tab strip:
 * today's time on the project of the tab in front, today's time in all,
 * and whether the timer counts, is paused or saw you away. One quiet line;
 * a click opens the Timer page in the browser.
 *
 * Drawn only when the server has the time routes (a 404 hides it).
 */

import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../../lib/getJson'
import { useTimeAuto, type TimeAuto } from '../../../lib/timer'
import { hMin } from '../../../utils/format'
import type { TimeEntry } from '../../project/timeEntry'
import { post } from './bridge'
import { t } from '../../../i18n/scope/aqua'

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

/** The chip's words: "harbor 1h 20m · today 3h 05m". */
export function chipText(project: string, projectMin: number, totalMin: number): string {
  return t('{project} {time} · today {total}', { project, time: hMin(projectMin, '0m'), total: hMin(totalMin, '0m') })
}

/** The Timer page, in the browser: through the window's bridge, or a new tab. */
export function openTimerPage() {
  const url = `${window.location.origin}/time`
  if (!post({ op: 'open', url })) window.open(url, '_blank', 'noopener')
}

type Summary = { today_min: number }

export function TimerChip({ project }: { project: string }) {
  // This window has no freshness stamp: the reads poll, slowly.
  const running = useQuery({
    queryKey: ['time-running'],
    queryFn: ({ signal }) => getJson<{ running: TimeEntry[] }>('/api/time/running', signal),
    refetchInterval: 30_000, retry: false,
  })
  const mine = useQuery({
    queryKey: ['time-summary', project],
    queryFn: ({ signal }) => getJson<Summary>(`/api/time/summary?project=${encodeURIComponent(project)}`, signal),
    refetchInterval: 60_000, retry: false, enabled: !!project,
  })
  const all = useQuery({
    queryKey: ['time-summary-all'],
    queryFn: ({ signal }) => getJson<Summary>('/api/time/summary', signal),
    refetchInterval: 60_000, retry: false,
  })
  const auto = useTimeAuto()
  if (!project || running.isError || all.isError || !running.data || !all.data) return null

  const state = chipState(project, running.data.running, auto.data)
  const text = chipText(project, mine.data?.today_min ?? 0, all.data.today_min)
  const said = `${t('Timer')}: ${WORD[state]}. ${text}. ${t('Click to open the Timer page.')}`
  const tone = state === 'counting' ? 'var(--brand)' : state === 'off' ? 'var(--aq-ink3, var(--text-tertiary))' : 'var(--status-amber)'
  return (
    <button type="button" data-nodrag data-timer={state} onClick={openTimerPage} title={said} aria-label={said}
      className="self-center shrink-0 ml-auto h-[20px] px-6 inline-flex items-center gap-6 rounded-[5px] text-11 font-mono tabular-nums whitespace-nowrap hover:bg-[var(--aq-hover)]"
      style={{ color: 'var(--aq-ink2)' }}>
      <span aria-hidden className={`w-[6px] h-[6px] rounded-full shrink-0 ${state === 'counting' ? 'animate-pulse' : ''}`}
        style={state === 'off' ? { border: `1px solid ${tone}` } : { background: tone }} />
      {state !== 'counting' && state !== 'off' && <span style={{ color: tone }}>{WORD[state]}</span>}
      <span className="max-w-[260px] truncate">{text}</span>
    </button>
  )
}
