import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Pause, Play, Plus } from 'lucide-react'

import { Button, toast } from '../../components/primitives'
import { getJson, postJson } from '../../lib/getJson'
import { persistPref } from '../../lib/uiPrefs'
import { Live, useNow } from '../../lib/clock'
import { sprintBoardKey, useSprintBoard } from '../tasks/data'
import { StartBlockDialog } from './StartBlockDialog'
import {
  RING_TONES, dateKey, formatClock, formatDuration, keyOf, liveElapsed, startDate, weightedSec,
  type BlockDef, type TimeEntry,
} from './timeEntry'
import { OPERATOR_ACTOR } from './types'
import { t } from '../../i18n/scope/project'

/**
 * PunchDeck — a project's blocks as tiles: punch to clock in or out, the
 * share slider (the attribution multiplier, remembered per block and
 * applied to the open entry live), pause, and a note on the punch. Several
 * blocks run at once. The project's Timer tab and the Timer page both
 * draw it, so a timer is started the same way in both places.
 */


export function PunchDeck({ projectCode }: { projectCode: string }) {
  const queryClient = useQueryClient()
  // Which day is today, and nothing finer: the running clocks are `Live`.
  const nowMs = useNow(60_000)
  // Notes live on the tiles: a pending note per block for its next punch,
  // and which tile has its note line revealed.
  const [pendingNote, setPendingNote] = useState<Record<string, string>>({})
  const [noteOpen, setNoteOpen] = useState<string | null>(null)
  const [runningNote, setRunningNote] = useState<string | null>(null)
  const [startingBlock, setStartingBlock] = useState(false)

  const entries = useQuery({
    queryKey: ['time-entries', projectCode],
    queryFn: ({ signal }) =>
      getJson<{ time_entries: TimeEntry[] }>(`/api/time-entries?project=${encodeURIComponent(projectCode)}&limit=1000`, signal),
  })
  const sprints = useSprintBoard(projectCode)

  const all = entries.data?.time_entries ?? []
  // The auto-timer's own span is not a punch: it has no tile to clock out of.
  const opens = all.filter((e) => !e.ended_at && e.source !== 'auto')
  const openFor = (key: string) => opens.find((e) => keyOf(e) === key)

  const shareKey = `sp-punch-share:${projectCode}`
  const [shares, setShares] = useState<Record<string, number>>(() => {
    try {
      const raw = JSON.parse(localStorage.getItem(shareKey) || '{}')
      return raw && typeof raw === 'object' ? raw : {}
    } catch { return {} }
  })
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['time-entries', projectCode] })
    // The Timer page reads every project's entries under its own key.
    void queryClient.invalidateQueries({ queryKey: ['time-entries-all'] })
    // The sidebar's running-timer chip reads its own key.
    void queryClient.invalidateQueries({ queryKey: ['time-running'] })
    void queryClient.invalidateQueries({ queryKey: ['time-summary-all'] })
  }
  const setShareFor = (key: string, v: number) => {
    const next = { ...shares, [key]: v }
    setShares(next)
    persistPref(shareKey, JSON.stringify(next))
    const running = openFor(key)
    if (running) {
      void postJson(`/api/time-entries/${encodeURIComponent(running.id)}/update`, { share_pct: v })
        .then(refresh).catch(() => toast.error(t('The share didn\'t save')))
    }
  }
  const shareOf = (key: string) => shares[key] ?? 100

  // Punch = toggle this block only; the other blocks keep running.
  const punch = async (key: string) => {
    try {
      const running = openFor(key)
      if (running) {
        await postJson(`/api/time/${encodeURIComponent(running.id)}/stop`)
        setRunningNote(null)
        await refresh()
        return
      }
      await postJson('/api/time/start', {
        project: projectCode, agent_id: OPERATOR_ACTOR,
        sprint_id: key === 'other' ? '' : key, share_pct: shareOf(key), note: (pendingNote[key] ?? '').trim(),
      })
      setPendingNote((cur) => ({ ...cur, [key]: '' }))
      setRunningNote(null)
      await refresh()
    } catch (e) { toast.error(String((e as Error).message ?? e)) }
  }
  const pauseResume = async (key: string) => {
    const open = openFor(key)
    if (!open) return
    try {
      await postJson(`/api/time/${encodeURIComponent(open.id)}/${open.paused_at ? 'resume' : 'pause'}`)
      await refresh()
    } catch (e) { toast.error(String((e as Error).message ?? e)) }
  }

  const blocks: BlockDef[] = [
    ...(sprints.data ?? []).map((sp) => ({ key: sp.id, name: sp.name })),
    { key: 'other', name: t('Everything else') },
  ]
  const todayKey = dateKey(new Date(nowMs))
  const todays = all.filter((e) => { const d = startDate(e); return !!d && dateKey(d) === todayKey })
  const todayFor = (key: string) => weightedSec(todays.filter((e) => keyOf(e) === key && e.ended_at), nowMs)

  return (
    <>
      {/* The deck */}
      <div className="grid gap-10" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
        {blocks.map((b) => {
          const open = openFor(b.key)
          const on = !!open
          const share = on ? (open?.share_pct ?? shareOf(b.key)) : shareOf(b.key)
          const ticking = on && !open?.paused_at
          const live = (now: number) => (on && open ? liveElapsed(open, now) : 0)
          return (
            <div key={b.key} className={`rounded-card border p-12 flex flex-col gap-8 ${on ? 'border-brand bg-brand/10' : 'border-border-default bg-elevated'}`}>
              <button type="button" onClick={() => void punch(b.key)} aria-pressed={on} className="flex flex-col items-start gap-4 text-left"
                title={on ? t('Punch to clock out') : t('Clock in. Other blocks keep running; the sliders split the time between them.')}>
                <span className="text-13 font-semibold text-primary flex items-center gap-6">
                  <span className="h-8 w-8 rounded-pill" style={{ backgroundColor: RING_TONES[Math.min(blocks.indexOf(b), 3)] }} aria-hidden />
                  {b.name}
                  {on && open?.paused_at && <span className="text-10 font-mono text-status-amber">{t('paused')}</span>}
                </span>
                <span className={`text-24 font-semibold tabular leading-none ${on ? (open?.paused_at ? 'text-tertiary' : 'text-brand') : 'text-secondary'}`}>
                  {on ? <Live on={ticking}>{(now) => formatClock(live(now))}</Live> : formatDuration(todayFor(b.key))}
                </span>
                <span className="text-10 font-mono text-tertiary">{on ? t('click to clock out') : t('today · click to clock in')}</span>
              </button>
              <label className="flex items-center gap-6 text-10 font-mono text-tertiary">
                <input type="range" min={10} max={100} step={10} value={share} onChange={(e) => setShareFor(b.key, Number(e.target.value))} aria-label={`${b.name} share`} className="flex-1 accent-[var(--brand)]" />
                <span className={`w-[32px] text-right ${share < 100 ? 'text-status-amber' : 'text-secondary'}`}>{share}%</span>
              </label>
              {on && share < 100 && <span className="text-10 font-mono text-status-amber">{t('booking')} <Live on={ticking}>{(now) => formatClock(Math.round(live(now) * share / 100))}</Live></span>}
              {(() => {
                const current = on ? (runningNote ?? open?.note ?? '') : (pendingNote[b.key] ?? '')
                const hasNote = !!current.trim()
                return (
                  <>
                    <div className="flex items-center gap-10">
                      {on && (
                        <Button variant="text" size="bare" onClick={() => void pauseResume(b.key)}>
                          {open?.paused_at ? <><Play size={10} aria-hidden /> {t('resume')}</> : <><Pause size={10} aria-hidden /> {t('pause')}</>}
                        </Button>
                      )}
                      <button
                        type="button"
                        onClick={() => setNoteOpen(noteOpen === b.key ? null : b.key)}
                        aria-expanded={noteOpen === b.key}
                        aria-label={on ? t('Note for the running punch') : t('Note for the next punch')}
                        title={hasNote ? current : on ? t('Add a note to the running punch') : t('Add a note for the next punch on this block')}
                        className={`inline-flex items-center gap-4 text-10 font-mono ${hasNote ? 'text-brand' : 'text-tertiary hover:text-primary'}`}
                      >
                        <MessageSquare size={10} aria-hidden /> {hasNote ? (current.length > 18 ? `${current.slice(0, 18)}…` : current) : 'note'}
                      </button>
                    </div>
                  </>
                )
              })()}
            </div>
          )
        })}
        {(sprints.data?.length ?? 0) < 3 && (
          <button
            type="button"
            onClick={() => setStartingBlock(true)}
            className="rounded-card border border-dashed border-border-default p-12 flex flex-col items-start gap-4 text-left hover:border-brand group min-h-[120px]"
            title={t('Start a block of work. It shows here and as a sprint on the board.')}
          >
            <span className="text-13 font-semibold text-tertiary group-hover:text-brand inline-flex items-center gap-6"><Plus size={13} aria-hidden /> {t('start a block')}</span>
            <span className="text-10 font-mono text-tertiary">{3 - (sprints.data?.length ?? 0)} {t('slot')}{3 - (sprints.data?.length ?? 0) === 1 ? '' : 's'} {t('free · planned days and an hour budget')}</span>
          </button>
        )}
      </div>
      {startingBlock && (
        <StartBlockDialog
          projectCode={projectCode}
          active={(sprints.data ?? []).map((sp) => ({ id: sp.id, name: sp.name }))}
          backlog={[]}
          onClose={() => setStartingBlock(false)}
          onStarted={() => {
            setStartingBlock(false)
            void queryClient.invalidateQueries({ queryKey: sprintBoardKey(projectCode) })
            void queryClient.invalidateQueries({ queryKey: ['time-sprints-all', projectCode] })
            void queryClient.invalidateQueries({ queryKey: ['time-sprints-every'] })
          }}
        />
      )}

      {/* The note line — under the deck, above the entries, full width */}
      {noteOpen && (() => {
        const b = blocks.find((x) => x.key === noteOpen)
        if (!b) return null
        const open = openFor(b.key)
        const on = !!open
        const current = on ? (runningNote ?? open?.note ?? '') : (pendingNote[b.key] ?? '')
        const commit = () => {
          if (on && open && runningNote !== null && runningNote.trim() !== (open.note ?? '')) {
            void postJson(`/api/time-entries/${encodeURIComponent(open.id)}/update`, { note: runningNote.trim() })
              .then(refresh).catch(() => toast.error(t('The note didn\'t save')))
          }
        }
        return (
          <div className="rounded-card border border-border-default bg-elevated px-14 py-10 flex flex-col gap-6">
            <div className="flex items-baseline gap-8">
              <span className="h-8 w-8 rounded-pill self-center" style={{ backgroundColor: RING_TONES[Math.min(blocks.indexOf(b), 3)] }} aria-hidden />
              <span className="text-12 font-semibold text-primary">{b.name}</span>
              <span className="text-11 font-mono text-tertiary">{on ? t('Note for the running punch. Saved on Enter or when you leave the field.') : t('note for the next punch on this block')}</span>
              <Button variant="text" size="bare" onClick={() => { commit(); setNoteOpen(null) }} className="ml-auto">{t('done')}</Button>
            </div>
            <textarea
              autoFocus
              rows={2}
              value={current}
              onChange={(e) => on ? setRunningNote(e.target.value) : setPendingNote((cur) => ({ ...cur, [b.key]: e.target.value }))}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commit(); setNoteOpen(null) } if (e.key === 'Escape') setNoteOpen(null) }}
              onBlur={commit}
              placeholder={on ? t('What you are working on. Shift+Enter for a new line') : t('What the next punch is for')}
              aria-label={`${b.name} note`}
              className="bg-surface border border-border-subtle rounded-input px-10 py-8 text-13 text-primary outline-none focus:border-brand leading-relaxed"
            />
          </div>
        )
      })()}
    </>
  )
}
