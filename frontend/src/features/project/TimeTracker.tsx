import { useMemo, useState } from 'react'
import { TH } from '../../components/ui'
import { StatTile, StatTiles } from '../../components/StatTile'
import { getJson, postJson, refused } from '../../lib/getJson'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'

import { Button, toast } from '../../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { OPERATOR_ACTOR } from './types'
import { PunchDeck } from './PunchDeck'
import { LABEL } from '../promptlib/taskstyle'

/**
 * TimeTracker — the Broadsheet: numbers first.
 *
 * KPIs (today, this week, top block, streak), the day as a 24-hour dial
 * beside a 26-week contribution grid, the punch deck (blocks as tiles
 * with a share slider — the attribution multiplier, remembered per block
 * and applied to the open entry live), then every entry in a table with
 * day subtotals: click a row to edit block, share, times and note; tick
 * rows to delete in bulk; add by hand what the clock missed. The clock
 * itself lives on the server (an entry with no ended_at), so it survives
 * reloads and restarts.
 */

export { formatClock, formatDuration, liveElapsed, type TimeEntry } from './timeEntry'
import {
  RING_TONES, dateKey, formatClock, formatDuration, keyOf, liveElapsed, startDate, weightedSec,
  type BlockDef, type TimeEntry,
} from './timeEntry'
import { Segmented } from '../../components/Segmented'
import { Live, useNow } from '../../lib/clock'
import { useSprintBoard } from '../tasks/data'
import { TIME_AUTO_KEY, modeOf, useTimeAuto, type TimeMode } from '../../lib/timer'
import { t, tn } from '../../i18n/scope/project'


const minOfDay = (d: Date) => d.getHours() * 60 + d.getMinutes()
const hhmm = (d: Date) => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
const parseHHMM = (s: string): number | null => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s.trim())
  if (!m) return null
  const v = Number(m[1]) * 60 + Number(m[2])
  return v >= 0 && v < 24 * 60 ? v : null
}
/** ISO local timestamp for a day + minutes-of-day (no timezone suffix, like the server writes). */
const isoAt = (day: Date, min: number) => {
  const d = new Date(day.getFullYear(), day.getMonth(), day.getDate(), Math.floor(min / 60), min % 60, 0)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`
}
const dayLabel = (key: string, todayKey: string, yKey: string) => (key === todayKey ? t('Today') : key === yKey ? t('Yesterday') : key)

export function TimeTracker({ projectCode }: { projectCode: string }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [adding, setAdding] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const entries = useQuery({
    queryKey: ['time-entries', projectCode],
    queryFn: ({ signal }) =>
      getJson<{ time_entries: TimeEntry[] }>(`/api/time-entries?project=${encodeURIComponent(projectCode)}&limit=1000`, signal),
  })
  const sprints = useSprintBoard(projectCode)
  const allSprints = useQuery({
    queryKey: ['time-sprints-all', projectCode],
    queryFn: ({ signal }) =>
      getJson<{ sprints: Array<{ id: string; name: string; status?: string }> }>(`/api/sprints?project=${encodeURIComponent(projectCode)}&limit=200`, signal)
        .catch(refused({ sprints: [] })),
  })

  const all = entries.data?.time_entries ?? []
  // Every open punch, one per block — several run at once; that is what
  // the share sliders are for. The seconds hand ticks while any runs.
  // The auto-timer's own span is not a punch: it has no tile to clock out of.
  const opens = all.filter((e) => !e.ended_at && e.source !== 'auto')
  const autoOpen = all.find((e) => !e.ended_at && e.source === 'auto')
  const anyRunning = opens.some((e) => !e.paused_at) || !!autoOpen
  // The tab's totals are minutes: counted again every ten seconds while a
  // timer runs. A running entry's own clock is `Live`, a second apiece.
  const nowMs = useNow(anyRunning ? 10_000 : 60_000)

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['time-entries', projectCode] })
    void queryClient.invalidateQueries({ queryKey: ['time-entries-all'] })
    // The sidebar's running-timer chip reads its own key.
    void queryClient.invalidateQueries({ queryKey: ['time-running'] })
    void queryClient.invalidateQueries({ queryKey: ['time-summary-all'] })
  }
  const remove = async (id: string) => {
    try { await postJson(`/api/time/${encodeURIComponent(id)}/delete`); await refresh() } catch { toast.error(t('Couldn\'t delete')) }
  }

  if (entries.isLoading) return <LoadingSkeleton variant="row" count={3} />
  if (entries.isError) return <ErrorBanner title={t('Could not load the tracker')} onRetry={() => void entries.refetch()} hideDismiss />

  // Blocks: the running sprints are tiles; ended ones still name old entries.
  const blocks: BlockDef[] = [
    ...(sprints.data ?? []).map((sp) => ({ key: sp.id, name: sp.name })),
    { key: 'other', name: t('Everything else') },
  ]
  const nameOf = (key: string) =>
    blocks.find((b) => b.key === key)?.name
    ?? allSprints.data?.sprints.find((sp) => sp.id === key)?.name
    ?? key
  const today = new Date(nowMs)
  const todayKey = dateKey(today)
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1)
  const yKey = dateKey(yesterday)
  const byDay = new Map<string, TimeEntry[]>()
  for (const e of all) {
    const d = startDate(e)
    if (!d) continue
    const k = dateKey(d)
    byDay.set(k, [...(byDay.get(k) ?? []), e])
  }
  const minutesOn = (k: string) => weightedSec(byDay.get(k) ?? [], nowMs) / 60
  const todays = byDay.get(todayKey) ?? []
  const lastNDays = (n: number) => Array.from({ length: n }, (_, i) => { const d = new Date(today); d.setDate(today.getDate() - i); return dateKey(d) })
  const weekKeys = lastNDays(7)
  const weekMin = weekKeys.reduce((a, k) => a + minutesOn(k), 0)
  const perBlockWeek = blocks.map((b) => ({
    b, min: weekKeys.reduce((a, k) => a + weightedSec((byDay.get(k) ?? []).filter((e) => keyOf(e) === b.key), nowMs) / 60, 0),
  }))
  const top = [...perBlockWeek].sort((a, b) => b.min - a.min)[0]
  const streak = (() => { let n = 0; for (const k of lastNDays(365)) { if (minutesOn(k) > 0) n++; else break } return n })()
  const dayKeys = [...byDay.keys()].sort().reverse()
  const shownDays = showAll ? dayKeys : dayKeys.slice(0, 14)

  return (
    <div className="flex flex-col gap-14">
      <SmartTimerBar project={projectCode} counting={!!autoOpen} />
      {/* KPIs */}
      <StatTiles>
        {[
          ['today', formatDuration(weightedSec(todays, nowMs)), opens.length ? `● ${opens.map((o) => nameOf(keyOf(o))).join(' + ')} running` : 'idle'],
          [t('this week'), formatDuration(weekMin * 60), `${formatDuration((weekMin / 7) * 60)} a day`],
          ['top block', top && top.min > 0 ? top.b.name : '—', top && top.min > 0 ? `${formatDuration(top.min * 60)} this week` : t('nothing logged this week')],
          ['streak', `${streak} day${streak === 1 ? '' : 's'}`, t('with logged time')],
        ].map(([k, v, sub]) => <StatTile key={k} label={k} value={v} sub={sub} />)}
      </StatTiles>

      {/* Dial + contribution grid */}
      <div className="grid gap-16 items-center" style={{ gridTemplateColumns: '220px 1fr' }}>
        <DayDial blocks={blocks} todays={todays} opens={opens} nowMs={nowMs} weightedSec={weightedSec(todays, nowMs)} nameOf={nameOf} />
        <ContributionGrid minutesOn={minutesOn} today={today} />
      </div>

      <PunchDeck projectCode={projectCode} />

      {/* Entries */}
      <div className="flex items-center gap-8 border-b border-border-default pb-4">
        <span className={LABEL}>{t('entries')}</span>
        {sel.size > 0 && (
          <button type="button" onClick={() => {
            void Promise.all([...sel].map((id) => postJson(`/api/time/${encodeURIComponent(id)}/delete`).then(() => true, () => false))).then((done) => {
              const failed = done.filter((ok) => !ok).length
              if (failed) toast.error(tn(done.length, '{failed} of {n} entry could not be deleted', '{failed} of {n} entries could not be deleted', { failed }))
              setSel(new Set()); void refresh()
            })
          }}
            className="inline-flex items-center gap-4 text-11 font-mono text-status-red"><Trash2 size={11} aria-hidden /> {t('delete')} {sel.size} {t('selected')}</button>
        )}
        <button type="button" onClick={() => setAdding((v) => !v)} className="ml-auto inline-flex items-center gap-4 text-11 font-mono text-brand"><Plus size={11} aria-hidden /> {t('entry')}</button>
      </div>
      {adding && (
        <div className="rounded-input bg-elevated p-8">
          <AddEntryForm projectCode={projectCode} blocks={blocks} today={today} onDone={() => { setAdding(false); void refresh() }} />
        </div>
      )}
      {dayKeys.length === 0 ? (
        <p className="text-12 text-tertiary italic">{t('No time logged yet.')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-12 font-mono">
            <thead>
              <tr className={TH}>
                <th className="w-[28px]" />
                <th className="text-left py-4 font-normal">{t('when')}</th>
                <th className="text-left py-4 font-normal">{t('block')}</th>
                <th className="text-left py-4 font-normal">{t('note')}</th>
                <th className="text-right py-4 font-normal">{t('share')}</th>
                <th className="text-right py-4 font-normal">{t('time')}</th>
              </tr>
            </thead>
            <tbody>
              {shownDays.map((k) => {
                const es = [...(byDay.get(k) ?? [])].sort((a, b) => Date.parse(a.started_at ?? '') - Date.parse(b.started_at ?? ''))
                return [
                  <tr key={`h${k}`} className="bg-elevated/50">
                    <td colSpan={5} className="px-8 py-3 text-11 text-secondary font-semibold">{dayLabel(k, todayKey, yKey)}</td>
                    <td className="px-8 py-3 text-right text-primary tabular">{formatDuration(weightedSec(es, nowMs))}</td>
                  </tr>,
                  ...es.map((e) => {
                    const d0 = startDate(e)!
                    const d1 = e.ended_at ? new Date(Date.parse(e.ended_at)) : null
                    return editing === e.id ? (
                      <tr key={e.id}>
                        <td colSpan={6} className="py-6 px-8">
                          <EntryEditor e={e} blocks={blocks} nameOf={nameOf} onDone={() => { setEditing(null); void refresh() }} onDelete={() => { setEditing(null); void remove(e.id) }} />
                        </td>
                      </tr>
                    ) : (
                      <tr key={e.id} className="border-b border-border-subtle hover:bg-hover cursor-pointer" onClick={() => setEditing(e.id)}>
                        <td className="px-4" onClick={(ev) => ev.stopPropagation()}>
                          {e.ended_at && (
                            <input type="checkbox" checked={sel.has(e.id)} onChange={() => setSel((cur) => { const n = new Set(cur); if (n.has(e.id)) n.delete(e.id); else n.add(e.id); return n })} aria-label={t('Select entry')} className="accent-[var(--brand)]" />
                          )}
                        </td>
                        <td className="py-5 text-tertiary tabular whitespace-nowrap">
                          {/* The row is clickable; the button is its keyboard and screen-reader way in. */}
                          <button type="button" onClick={(ev) => { ev.stopPropagation(); setEditing(e.id) }}
                            aria-label={t('Edit the entry {time}', { time: `${hhmm(d0)}–${d1 ? hhmm(d1) : t('now')}` })}
                            className="tabular text-left hover:text-primary">
                            {hhmm(d0)}–{d1 ? hhmm(d1) : t('now')}
                          </button>
                        </td>
                        <td className="py-5 text-secondary whitespace-nowrap">{nameOf(keyOf(e))}</td>
                        <td className="py-5 text-secondary font-sans truncate max-w-[260px]">
                          {e.source === 'auto' && <span className="mr-6 px-4 rounded-input bg-brand/16 text-brand font-mono text-10" title={t('Counted by the auto-timer while you worked on the project')}>{t('auto')}</span>}
                          {e.note || (e.source === 'auto' ? null : <span className="text-tertiary italic">—</span>)}
                        </td>
                        <td className={`py-5 text-right tabular ${(e.share_pct ?? 100) < 100 ? 'text-status-amber' : 'text-tertiary'}`}>{e.share_pct ?? 100}%</td>
                        <td className="py-5 text-right text-primary tabular whitespace-nowrap">{e.ended_at ? formatDuration(liveElapsed(e, nowMs)) : <span className="text-brand"><Live on={!e.paused_at}>{(now) => formatClock(liveElapsed(e, now))}</Live></span>}</td>
                      </tr>
                    )
                  }),
                ]
              })}
            </tbody>
          </table>
          {dayKeys.length > 14 && (
            <button type="button" onClick={() => setShowAll((v) => !v)} className="mt-6 text-11 font-mono text-brand">
              {showAll ? t('− last 14 days only') : t('+ {n} more days', { n: dayKeys.length - 14 })}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Editing one entry — block, times, share, note — against the update route.
 * ------------------------------------------------------------------------- */

function EntryEditor({
  e, blocks, nameOf, onDone, onDelete,
}: {
  e: TimeEntry
  blocks: BlockDef[]
  nameOf: (k: string) => string
  onDone: () => void
  onDelete: () => void
}) {
  const d0 = startDate(e)!
  const d1 = e.ended_at ? new Date(Date.parse(e.ended_at)) : null
  const [block, setBlock] = useState(keyOf(e))
  const [from, setFrom] = useState(hhmm(d0))
  const [to, setTo] = useState(d1 ? hhmm(d1) : '')
  const [share, setShare] = useState(e.share_pct ?? 100)
  const [note, setNote] = useState(e.note ?? '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const options: BlockDef[] = blocks.some((b) => b.key === keyOf(e)) ? blocks : [...blocks, { key: keyOf(e), name: nameOf(keyOf(e)) }]
  const save = async () => {
    const f = parseHHMM(from), t = d1 ? parseHHMM(to) : null
    if (f === null || (d1 && t === null)) { setErr('times are HH:MM'); return }
    if (t !== null && t <= f) { setErr('end must come after start'); return }
    setBusy(true)
    const patch: Record<string, unknown> = {
      sprint_id: block === 'other' ? '' : block, share_pct: share, note: note.trim(), started_at: isoAt(d0, f),
    }
    if (t !== null) { patch.ended_at = isoAt(d0, t); patch.duration_min = t - f - Math.round((e.paused_total_sec ?? 0) / 60) }
    try { await postJson(`/api/time-entries/${encodeURIComponent(e.id)}/update`, patch); onDone() }
    catch (x) { setErr(String((x as Error).message ?? x)); setBusy(false) }
  }
  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center gap-6 flex-wrap">
        <select value={block} onChange={(ev) => setBlock(ev.target.value)} aria-label={t('Block')} className="bg-elevated border border-border-default rounded-input px-6 py-4 text-12 text-primary">
          {options.map((b) => <option key={b.key} value={b.key}>{b.name}</option>)}
        </select>
        <input value={from} onChange={(ev) => setFrom(ev.target.value)} aria-label={t('Start')} className="w-[56px] bg-elevated border border-border-default rounded-input px-6 py-4 text-12 font-mono text-primary text-center" />
        <span className="text-tertiary">–</span>
        {d1 ? <input value={to} onChange={(ev) => setTo(ev.target.value)} aria-label={t('End')} className="w-[56px] bg-elevated border border-border-default rounded-input px-6 py-4 text-12 font-mono text-primary text-center" />
            : <span className="text-12 font-mono text-brand">{t('running')}</span>}
        <label className="flex items-center gap-6 text-10 font-mono text-tertiary w-[150px]">
          <input type="range" min={10} max={100} step={10} value={share} onChange={(ev) => setShare(Number(ev.target.value))} aria-label={t('Entry share')} className="flex-1 accent-[var(--brand)]" />
          <span className={`w-[32px] text-right ${share < 100 ? 'text-status-amber' : 'text-secondary'}`}>{share}%</span>
        </label>
      </div>
      <input value={note} onChange={(ev) => setNote(ev.target.value)} placeholder={t('Note')} aria-label={t('Note')} className="bg-elevated border border-border-default rounded-input px-8 py-6 text-12 text-primary outline-none focus:border-brand" />
      <div className="flex items-center gap-8">
        {err && <span className="text-11 font-mono text-status-red">{err}</span>}
        {d1 && <Button variant="danger-text" size="bare" onClick={onDelete} className="ml-auto"><Trash2 size={11} aria-hidden /> {t('delete')}</Button>}
        <Button variant="text" size="bare" onClick={onDone} className={d1 ? '' : 'ml-auto'}>{t('cancel')}</Button>
        <Button variant="primary" size="sm" onClick={() => void save()} disabled={busy}>{t('save')}</Button>
      </div>
    </div>
  )
}

function AddEntryForm({
  projectCode, blocks, today, onDone,
}: {
  projectCode: string
  blocks: BlockDef[]
  today: Date
  onDone: () => void
}) {
  const [day, setDay] = useState(dateKey(today))
  const [block, setBlock] = useState('other')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [share, setShare] = useState(100)
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  const add = async () => {
    const f = parseHHMM(from), t = parseHHMM(to)
    const d = new Date(`${day}T12:00:00`)
    if (Number.isNaN(d.getTime())) { setErr('the day is YYYY-MM-DD'); return }
    if (f === null || t === null) { setErr('times are HH:MM'); return }
    if (t <= f) { setErr('end must come after start'); return }
    const yy = String(d.getFullYear()).slice(-2)
    try {
      await postJson('/api/time-entries', {
        project: projectCode, agent_id: OPERATOR_ACTOR,
        created_date: `${yy}${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`,
        created_time: from.trim().padStart(5, '0'),
        started_at: isoAt(d, f), ended_at: isoAt(d, t), duration_min: t - f, paused_total_sec: 0,
        share_pct: share, sprint_id: block === 'other' ? '' : block, note: note.trim(),
      })
      onDone()
    } catch (x) { setErr(String((x as Error).message ?? x)) }
  }
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-6 flex-wrap">
        <input value={day} onChange={(ev) => setDay(ev.target.value)} aria-label={t('Day')} className="w-[96px] bg-elevated border border-border-default rounded-input px-6 py-4 text-12 font-mono text-primary text-center" />
        <select value={block} onChange={(ev) => setBlock(ev.target.value)} aria-label={t('Block')} className="bg-elevated border border-border-default rounded-input px-6 py-4 text-12 text-primary">
          {blocks.map((b) => <option key={b.key} value={b.key}>{b.name}</option>)}
        </select>
        <input value={from} onChange={(ev) => setFrom(ev.target.value)} placeholder="14:00" aria-label={t('Start')} className="w-[56px] bg-elevated border border-border-default rounded-input px-6 py-4 text-12 font-mono text-primary text-center" />
        <span className="text-tertiary">–</span>
        <input value={to} onChange={(ev) => setTo(ev.target.value)} placeholder="15:30" aria-label={t('End')} className="w-[56px] bg-elevated border border-border-default rounded-input px-6 py-4 text-12 font-mono text-primary text-center" />
        <label className="flex items-center gap-6 text-10 font-mono text-tertiary w-[150px]">
          <input type="range" min={10} max={100} step={10} value={share} onChange={(ev) => setShare(Number(ev.target.value))} aria-label={t('New entry share')} className="flex-1 accent-[var(--brand)]" />
          <span className={`w-[32px] text-right ${share < 100 ? 'text-status-amber' : 'text-secondary'}`}>{share}%</span>
        </label>
        <input value={note} onChange={(ev) => setNote(ev.target.value)} placeholder={t('note')} aria-label={t('Note')} className="flex-1 min-w-[120px] bg-elevated border border-border-default rounded-input px-8 py-4 text-12 text-primary outline-none focus:border-brand" />
        <Button variant="primary" size="sm" onClick={() => void add()}>{t('add')}</Button>
      </div>
      {err && <span className="text-11 font-mono text-status-red">{err}</span>}
      <span className="text-10 font-mono text-tertiary">{t('Add time the timer did not record')}</span>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * The contribution grid — 26 weeks of weighted minutes, GitHub-style.
 * ------------------------------------------------------------------------- */

export function ContributionGrid({ minutesOn, today, weeks = 26 }: { minutesOn: (k: string) => number; today: Date; weeks?: number }) {
  const CELL = 13, GAP = 3
  // Last cell = today; columns are weeks; rows Mon…Sun. Pad the first column
  // so weekdays line up with the rows.
  const todayDow = (today.getDay() + 6) % 7 // 0 = Mon
  const total = weeks * 7 - (6 - todayDow)
  const cells = Array.from({ length: total }, (_, i) => {
    const d = new Date(today); d.setDate(today.getDate() - (total - 1 - i))
    const k = dateKey(d)
    return { k, d, min: minutesOn(k) }
  })
  const max = Math.max(...cells.map((c) => c.min), 60)
  const level = (m: number) => (m === 0 ? 0 : m < max * 0.25 ? 1 : m < max * 0.5 ? 2 : m < max * 0.75 ? 3 : 4)
  const fill = (l: number) => (l === 0 ? 'var(--bg-elevated)' : `color-mix(in oklab, var(--brand) ${[0, 28, 48, 70, 95][l]}%, var(--bg-elevated))`)
  const sum = cells.reduce((a, c) => a + c.min, 0)
  const active = cells.filter((c) => c.min > 0).length
  const best = cells.reduce((a, c) => (c.min > a.min ? c : a), cells[0]!)
  const firstDow = (cells[0]!.d.getDay() + 6) % 7
  const ticks = [24, 20, 16, 12, 8, 4]
  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div className="flex items-baseline gap-10 flex-wrap">
        <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('last {weeks}', { weeks: tn(weeks, '{n} week', '{n} weeks') })}</span>
        <span className="text-11 font-mono text-secondary">{formatDuration(sum * 60)}</span>
        <span className="text-10 font-mono text-tertiary">{tn(active, '{n} active day', '{n} active days')}{best.min > 0 ? ` · ${t('best {day} {time}', { day: best.k, time: formatDuration(best.min * 60) })}` : ''}</span>
      </div>
      <div className="flex gap-6 overflow-x-auto">
        <div className="grid text-10 font-mono text-tertiary pt-14" style={{ gridTemplateRows: `repeat(7, ${CELL}px)`, rowGap: GAP }}>
          {['M', '', 'W', '', 'F', '', 'S'].map((d, i) => <span key={i} style={{ lineHeight: `${CELL}px` }}>{d}</span>)}
        </div>
        <div className="flex flex-col gap-2">
          <div className="relative h-12" style={{ width: weeks * (CELL + GAP) - GAP }}>
            {ticks.map((wk) => <span key={wk} className="absolute text-10 font-mono text-tertiary" style={{ left: (weeks - wk) * (CELL + GAP) }}>{wk}w</span>)}
            <span className="absolute right-0 text-10 font-mono text-status-red">{t('now')}</span>
          </div>
          <div className="grid" style={{ gridTemplateColumns: `repeat(${weeks}, ${CELL}px)`, gridAutoFlow: 'column', gridTemplateRows: `repeat(7, ${CELL}px)`, gap: GAP }}>
            {Array.from({ length: firstDow }, (_, i) => <div key={`pad${i}`} />)}
            {cells.map((c) => (
              <div key={c.k} title={`${c.k} · ${c.min ? formatDuration(c.min * 60) : 'nothing logged'}`}
                className={`rounded-bar ${c.k === dateKey(today) ? 'ring-1 ring-status-red' : ''}`} style={{ backgroundColor: fill(level(c.min)) }} />
            ))}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4 self-end text-10 font-mono text-tertiary">
        {t('less')} {[0, 1, 2, 3, 4].map((l) => <span key={l} className="h-10 w-10 rounded-bar" style={{ backgroundColor: fill(l) }} aria-hidden />)} {t('more')}
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * The day dial — 24 hours, one ring per block, entries as arcs.
 * ------------------------------------------------------------------------- */

/** `ringOf` says which ring an entry is drawn on: its block by default; the Timer page passes its project. */
export function DayDial({
  blocks, todays, opens, nowMs, weightedSec: total, nameOf, ringOf = keyOf,
}: {
  ringOf?: (e: TimeEntry) => string
  blocks: BlockDef[]
  todays: TimeEntry[]
  opens: TimeEntry[]
  nowMs: number
  weightedSec: number
  nameOf: (k: string) => string
}) {
  const SZ = 220, C = SZ / 2
  const rings = useMemo(() => {
    const map: Record<string, { r: number; tone: string }> = {}
    blocks.forEach((b, i) => { map[b.key] = { r: C - 22 - i * 14, tone: b.tone ?? RING_TONES[Math.min(i, 3)]! } })
    return map
  }, [blocks, C])
  const ang = (m: number) => ((m / (24 * 60)) * 360 - 90) * (Math.PI / 180)
  const arc = (from: number, to: number, r: number) => {
    const a0 = ang(from), a1 = ang(Math.max(to, from + 3))
    const large = to - from > 12 * 60 ? 1 : 0
    return `M ${C + r * Math.cos(a0)} ${C + r * Math.sin(a0)} A ${r} ${r} 0 ${large} 1 ${C + r * Math.cos(a1)} ${C + r * Math.sin(a1)}`
  }
  const now = new Date(nowMs)
  const nowMin = minOfDay(now)
  const ringFor = (e: TimeEntry) => rings[ringOf(e)] ?? rings.other
  return (
    <svg viewBox={`0 0 ${SZ} ${SZ}`} width={SZ} height={SZ} role="img" aria-label={t('Today as a dial')}>
      {[0, 6, 12, 18].map((h) => {
        const a = ang(h * 60)
        return <text key={h} x={C + (C - 8) * Math.cos(a)} y={C + (C - 8) * Math.sin(a) + 3} fontSize={8} fill="var(--text-tertiary)" textAnchor="middle" fontFamily="monospace">{h}</text>
      })}
      {blocks.map((b) => <circle key={b.key} cx={C} cy={C} r={rings[b.key]!.r} fill="none" stroke="var(--bg-elevated)" strokeWidth={10} />)}
      {todays.filter((e) => e.ended_at).map((e) => {
        const d0 = startDate(e), d1 = new Date(Date.parse(e.ended_at!))
        const ring = ringFor(e)
        if (!d0 || !ring) return null
        return (
          <path key={e.id} d={arc(minOfDay(d0), Math.max(minOfDay(d1), minOfDay(d0) + 1), ring.r)} fill="none" stroke={ring.tone} strokeWidth={10} strokeLinecap="round" opacity={(e.share_pct ?? 100) < 100 ? 0.55 : 0.9}>
            <title>{`${nameOf(ringOf(e))} · ${hhmm(d0)}–${hhmm(d1)}${e.note ? ` · ${e.note}` : ''}${(e.share_pct ?? 100) < 100 ? ` · ${e.share_pct}%` : ''}`}</title>
          </path>
        )
      })}
      {opens.map((open) => {
        const d0 = startDate(open), ring = ringFor(open)
        if (!d0 || !ring) return null
        return <path key={open.id} d={arc(minOfDay(d0), Math.max(nowMin, minOfDay(d0) + 2), ring.r)} fill="none" stroke={ring.tone} strokeWidth={10} strokeLinecap="round" className={open.paused_at ? '' : 'animate-pulse'} />
      })}
      <line x1={C} y1={C} x2={C + (C - 14) * Math.cos(ang(nowMin))} y2={C + (C - 14) * Math.sin(ang(nowMin))} stroke="var(--status-red)" strokeWidth={1} />
      <text x={C} y={C - 2} fontSize={15} fontWeight={700} fill="var(--text-primary)" textAnchor="middle">{formatDuration(total)}</text>
      <text x={C} y={C + 12} fontSize={8} fill="var(--text-tertiary)" textAnchor="middle" fontFamily="monospace">{t('today, weighted')}</text>
    </svg>
  )
}

const IDLE_FROM: Record<string, string> = {
  gnome: 'GNOME', xprintidle: 'X11', macos: 'macOS', windows: t('Windows'),
}

/**
 * The project's timer mode, and what the smart timer sees: remind (asks
 * when you open a task or start an agent), auto (counts while you work on
 * the project), manual (only the tiles below).
 */
function SmartTimerBar({ project, counting }: { project: string; counting: boolean }) {
  const qc = useQueryClient()
  const st = useTimeAuto().data
  if (!st) return null
  const mode = modeOf(st, project)
  const setMode = (m: TimeMode) => {
    void postJson('/api/time/auto/mode', { project, mode: m })
      .then(() => qc.invalidateQueries({ queryKey: TIME_AUTO_KEY }))
      .catch(() => toast.error(t('The timer mode didn\'t save')))
  }
  const away = !st.idle_pause
    ? t('does not pause when you are away (Settings › Time)')
    : st.idle_source
      ? t('pauses after {n} min away (read from {source})', { n: st.idle_minutes, source: IDLE_FROM[st.idle_source] ?? st.idle_source })
      : t('cannot tell when you are away on this system, so it does not pause')
  return (
    <div className="flex items-center gap-10 flex-wrap text-11 font-mono text-tertiary">
      <span className="uppercase tracking-wide text-10">{t('timer')}</span>
      <Segmented label={t('Timer mode')} value={mode} onChange={setMode}
        options={[
          ['remind', 'remind', t('Asks whether to track when you open a task or start an agent')],
          ['auto', 'auto', t('Counts while you work on this project: its pages, terminals and files')],
          ['manual', 'manual', t('Only the timers you start below')],
        ] as const} />
      {mode === 'auto' && (
        <span className={counting ? 'text-brand' : ''}>{counting ? t('● counting') : t('counts while you work on the project')}</span>
      )}
      <span className="ml-auto">{away}</span>
    </div>
  )
}
