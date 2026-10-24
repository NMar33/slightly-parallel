/**
 * The timer in the top bar, beside the monitor: what is being timed now.
 *
 * - a timer runs — a dot, its clock, its project; "auto" when the smart
 *   timer started it; "+1" when more run;
 * - every timer is paused — the same in amber, with "paused";
 * - nothing runs — the time tracked today.
 *
 * Hovering lists every timer, today and the last 7 days, the mode of the
 * project you are on, and when the timer pauses by itself. A click opens
 * the Timer page.
 */

import { Live } from '../../lib/clock'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Timer } from 'lucide-react'

import { getJson } from '../../lib/getJson'
import { modeOf, useTimeAuto, type TimeAuto, type TimeMode } from '../../lib/timer'
import { hMin } from '../../utils/format'
import { formatClock, liveElapsed, type TimeEntry } from '../project/timeEntry'

import { t, tn } from '../../i18n/scope/views'
import { rich } from '../../i18n/rich'
import { decodeSafe } from '../../hooks/useHashState'
interface TimerLine {
  state: 'running' | 'paused' | 'idle'
  /** The timer shown: one that runs before one that is paused, yours before the smart timer's. */
  entry: TimeEntry | null
  /** How many other timers are open. */
  more: number
}

export function timerLine(running: TimeEntry[]): TimerLine {
  if (running.length === 0) return { state: 'idle', entry: null, more: 0 }
  const rank = (e: TimeEntry) => (e.paused_at ? 2 : 0) + (e.source === 'auto' ? 1 : 0)
  const entry = [...running].sort((a, b) => rank(a) - rank(b))[0]
  return { state: entry.paused_at ? 'paused' : 'running', entry, more: running.length - 1 }
}

const MODE_SAYS: Record<TimeMode, string> = {
  remind: t('asks when you open a task or start an agent'),
  auto: t('counts by itself while you work on it'),
  manual: t('counts only the timers you start'),
}
const IDLE_FROM: Record<string, string> = { gnome: 'GNOME', xprintidle: 'X11', macos: 'macOS', windows: 'Windows' }

/** "pauses after 10 min away", or why it does not. */
export function awayLine(st: TimeAuto | undefined): string {
  if (!st) return ''
  if (!st.idle_pause) return t('pausing when away is off (Settings › Time)')
  if (!st.idle_source) return t('cannot detect when you are away on this system; it does not pause automatically')
  return t('pauses after {idle_minutes} min away (read from {v})', { idle_minutes: st.idle_minutes, v: IDLE_FROM[st.idle_source] ?? st.idle_source })
}

export function TopbarTimer() {
  const location = useLocation()
  const running = useQuery({
    queryKey: ['time-running'],
    // No poll: a timer started, paused or stopped is a write, and the
    // freshness stamp asks again for it.
    queryFn: ({ signal }) => getJson<{ running: TimeEntry[] }>('/api/time/running', signal),
  }).data?.running ?? []
  const summary = useQuery({
    queryKey: ['time-summary-all'],
    queryFn: ({ signal }) => getJson<{ today_min: number; week_min: number }>('/api/time/summary', signal),
    // The minute hand: today's total grows while a timer runs, with no write.
    refetchInterval: 60_000,
  }).data
  const st = useTimeAuto().data

  const line = timerLine(running)
  const e = line.entry
  const tone = line.state === 'paused' ? 'var(--status-amber)' : 'var(--brand)'
  const here = /^\/project\/([^/]+)/.exec(location.pathname)?.[1]
  const project = here ? decodeSafe(here) : ''
  const today = hMin(summary?.today_min ?? 0, '0m')
  const title = line.state === 'idle' ? t('No timer is running') : (line.state === 'paused' ? tn(running.length, '{n} timer paused', '{n} timers paused') : tn(running.length, '{n} timer running', '{n} timers running'))

  return (
    <span className="relative group inline-flex">
      <Link to="/time" aria-label={t('{title} — open the Timer page', { title })}
        className="inline-flex items-center gap-6 h-24 px-8 rounded-pill hover:bg-hover text-11 font-mono tabular-nums text-secondary whitespace-nowrap">
        <span className="text-tertiary text-10 hidden 2xl:inline">{t('TIMER')}</span>
        {e ? (
          <>
            <span className={`w-6 h-6 rounded-pill ${line.state === 'running' ? 'animate-pulse' : ''}`} style={{ background: tone }} />
            <span className={line.state === 'paused' ? 'text-tertiary' : 'text-primary'}><Live on={!e.paused_at}>{(now) => formatClock(liveElapsed(e, now))}</Live></span>
            <span className="max-w-[120px] truncate">{e.project}</span>
            {line.state === 'paused' ? <span className="text-status-amber">{t('paused')}</span> : e.source === 'auto' && <span className="text-brand">{t('auto')}</span>}
            {line.more > 0 && <span className="text-tertiary">+{line.more}</span>}
          </>
        ) : (
          <>
            <Timer size={12} className="text-tertiary 2xl:hidden" aria-hidden />
            <span className="text-primary">{today}</span>
            <span className="text-tertiary hidden 2xl:inline">{t('today')}</span>
          </>
        )}
      </Link>
      <span className="absolute right-0 top-full pt-4 z-50 hidden group-hover:block group-focus-within:block">
        <span className="flex flex-col gap-6 w-[280px] p-10 rounded-card border border-border-subtle bg-base shadow-lg">
          <span className="text-12 font-medium text-primary">{title}</span>
          {running.map((r) => (
            <span key={r.id} className="flex items-center gap-8 text-11 font-mono tabular-nums">
              <span className={`w-6 h-6 rounded-pill shrink-0 ${r.paused_at ? '' : 'animate-pulse'}`}
                style={{ background: r.paused_at ? 'var(--status-amber)' : 'var(--brand)' }} />
              <span className="truncate text-secondary">{r.project}</span>
              {r.source === 'auto' && <span className="text-brand">{t('auto')}</span>}
              {r.paused_at && <span className="text-status-amber">{t('paused')}</span>}
              <span className="ml-auto text-primary"><Live on={!r.paused_at}>{(now) => formatClock(liveElapsed(r, now))}</Live></span>
            </span>
          ))}
          <span className="flex items-center gap-8 text-11 font-mono tabular-nums border-t border-border-subtle pt-6">
            <span className="text-tertiary">{t('today')}</span><span className="text-primary">{today}</span>
            <span className="text-tertiary ml-auto">{t('last 7 days')}</span><span className="text-primary">{hMin(summary?.week_min ?? 0, '0m')}</span>
          </span>
          {project && st && (
            <span className="text-11 text-secondary">
              {rich(t('{project} is on {mode}: the timer {says}.'), { project: <span className="font-mono text-primary">{project}</span>, mode: modeOf(st, project), says: MODE_SAYS[modeOf(st, project)] })}
            </span>
          )}
          {st && <span className="text-10 font-mono text-tertiary">{awayLine(st)}</span>}
        </span>
      </span>
    </span>
  )
}
