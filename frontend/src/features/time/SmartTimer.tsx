/**
 * The smart timer, on every page (mounted once in the app shell):
 *
 * - while you give input and Slightly Parallel is in front, it tells the server which
 *   project (and task) you are on, every 20 s — the server counts auto time
 *   from these beats (timeauto.py);
 * - an away notice: a timer paused while you were away, and the choice to
 *   count the gap after all;
 * - the reminder: a task opened or an agent started on a project in
 *   "remind" with no timer running asks whether to track — the answer
 *   becomes the project's mode.
 */

import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Timer } from 'lucide-react'

import { Button } from '../../components/primitives'
import { getJson, postJson, fail } from '../../lib/getJson'
import {
  TIME_AUTO_KEY, clearAsk, currentWork, modeOf, useAsk, useTimeAuto,
  type AwayNotice, type TimeMode, type WorkContext,
} from '../../lib/timer'
import { hMin } from '../../utils/format'
import type { TimeEntry } from '../project/timeEntry'

import { t } from '../../i18n/scope/views'
import { rich } from '../../i18n/rich'
const BEAT_MS = 20_000
/** Reading counts: input this recent still means you are here. */
const READING_MS = 120_000

const DISMISSED = 'sp-time-ask-dismissed:'

export function SmartTimer() {
  useBeats()
  const st = useTimeAuto().data
  return (
    <div className="fixed right-16 top-[56px] z-toast flex flex-col gap-8 w-[340px] max-w-[calc(100vw-32px)] pointer-events-none">
      {st?.away.map((a) => <AwayCard key={a.entry_id} notice={a} />)}
      <Reminder />
    </div>
  )
}

/** Beats: input anywhere on the page, Slightly Parallel in front, a project in hand. */
function useBeats() {
  const lastInput = useRef(0)
  useEffect(() => {
    let lastMove = 0
    const mark = () => { lastInput.current = Date.now() }
    const move = () => { const tv = Date.now(); if (tv - lastMove > 1000) { lastMove = tv; mark() } }
    const opts = { passive: true, capture: true } as const
    window.addEventListener('keydown', mark, opts)
    window.addEventListener('pointerdown', mark, opts)
    window.addEventListener('wheel', mark, opts)
    window.addEventListener('pointermove', move, opts)
    const send = () => {
      const work = currentWork()
      if (!work || document.visibilityState !== 'visible' || !document.hasFocus()) return
      if (Date.now() - lastInput.current > READING_MS) return
      // A lost beat is covered by the next one, a few seconds later; nothing to say.
      void postJson('/api/time/auto/beat', { project: work.project, task_id: work.taskId ?? '' }).catch(() => undefined)
    }
    const id = window.setInterval(send, BEAT_MS)
    return () => {
      window.clearInterval(id)
      window.removeEventListener('keydown', mark, opts)
      window.removeEventListener('pointerdown', mark, opts)
      window.removeEventListener('wheel', mark, opts)
      window.removeEventListener('pointermove', move, opts)
    }
  }, [])
}

const minutes = (sec: number) => hMin(Math.max(1, Math.round(sec / 60)), '1m')

function Card({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div role="status" aria-label={label}
      className="pointer-events-auto rounded-card border border-border-strong bg-surface shadow-lg p-12 flex flex-col gap-8">
      {children}
    </div>
  )
}

function useRefresh() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: TIME_AUTO_KEY })
    void qc.invalidateQueries({ queryKey: ['time-running'] })
    void qc.invalidateQueries({ queryKey: ['time-entries'] })
  }
}

function AwayCard({ notice }: { notice: AwayNotice }) {
  const refresh = useRefresh()
  const answer = (action: string) =>
    postJson(`/api/time/auto/away/${encodeURIComponent(notice.entry_id)}`, { action }).then(refresh).catch(fail)
  const away = minutes(notice.sec)
  return (
    <Card label={t('Away from the timer')}>
      <p className="text-13 text-primary flex items-start gap-8">
        <Timer size={14} aria-hidden className="mt-2 shrink-0 text-status-amber" />
        {notice.long
          ? <span>{rich(t('Away {away}. The {project} timer is paused.'), { away, project: <b>{notice.project}</b> })}</span>
          : <span>{rich(t('Away {away} — not counted on {project}. The timer is running again.'), { away, project: <b>{notice.project}</b> })}</span>}
      </p>
      <div className="flex items-center gap-8 flex-wrap">
        {notice.long && <Button size="sm" variant="primary" onClick={() => void answer('resume')}>{t('Resume')}</Button>}
        {notice.long && <Button size="sm" onClick={() => void answer('stop')}>{t('Stop')}</Button>}
        <Button size="sm" onClick={() => void answer('count')}>{t('Count it anyway')}</Button>
        {!notice.long && <Button size="sm" variant="text" onClick={() => void answer('dismiss')}>{t('OK')}</Button>}
      </div>
    </Card>
  )
}

function Reminder() {
  const ask = useAsk()
  const st = useTimeAuto().data
  const running = useQuery({
    queryKey: ['time-running'],
    queryFn: ({ signal }) => getJson<{ running: TimeEntry[] }>('/api/time/running', signal),
  }).data?.running
  const refresh = useRefresh()
  if (!ask || !st || !running) return null
  if (modeOf(st, ask.project) !== 'remind') return null
  if (running.some((e) => e.project === ask.project)) return null
  try { if (sessionStorage.getItem(DISMISSED + ask.project)) return null } catch { /* fine */ }

  const choose = async (mode: TimeMode, ctx: WorkContext) => {
    try {
      if (mode === 'manual') await postJson('/api/time/start', { project: ctx.project, task_id: ctx.taskId ?? '' })
      await postJson('/api/time/auto/mode', { project: ctx.project, mode })
      if (mode === 'auto') await postJson('/api/time/auto/beat', { project: ctx.project, task_id: ctx.taskId ?? '' })
    } catch (e) { fail(e); return }
    clearAsk()
    refresh()
  }
  const later = () => {
    try { sessionStorage.setItem(DISMISSED + ask.project, '1') } catch { /* fine */ }
    clearAsk()
  }
  return (
    <Card label={t('Track time')}>
      <p className="text-13 text-primary flex items-start gap-8">
        <Timer size={14} aria-hidden className="mt-2 shrink-0 text-brand" />
        <span>{t('Track time on')}{' '}<b>{ask.title || ask.project}</b>?</span>
      </p>
      <p className="text-11 text-tertiary leading-relaxed">
        {t('auto counts while you work on')}{' '}{ask.project} {t('and stops when you leave; manual starts a timer now. Saved for this project. Change it on its Timer tab.')}
      </p>
      <div className="flex items-center gap-8">
        <Button size="sm" variant="primary" onClick={() => void choose('auto', ask)}>{t('auto')}</Button>
        <Button size="sm" onClick={() => void choose('manual', ask)}>{t('manual')}</Button>
        <Button size="sm" variant="text" onClick={later}>{t('not now')}</Button>
      </div>
    </Card>
  )
}
