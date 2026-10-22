import { copyText } from '../../lib/useCopy'
import { persistJsonPref, readJsonPref } from '../../lib/uiPrefs'
import { useMemo, useState } from 'react'

import { Button } from '../../components/primitives'
import { DaySpark } from '../agents/parts'
import { safeParseMs } from '../../utils/dateUtils'
import {
  useCandidates, useLibrary,
  type Candidate, type PromptRow,
} from './data'
import { t } from '../../i18n/scope/system'

export function useOverview() {
  const library = useLibrary('active')
  const candidates = useCandidates()
  const rows = useMemo(() => library.data?.prompts ?? [], [library.data])
  const byDay = useMemo(() => {
    const m = new Map<string, { date: string; turns: number; minutes: number; sessions: number }>()
    for (const r of rows) {
      for (const [date, n] of Object.entries(r.metrics.by_day ?? {})) {
        const d = m.get(date) ?? { date, turns: 0, minutes: 0, sessions: 0 }
        d.turns += n
        d.sessions += 1
        m.set(date, d)
      }
    }
    return [...m.values()].sort((a, b) => a.date.localeCompare(b.date))
  }, [rows])
  const range = useMemo<[number, number]>(() => {
    const ms = byDay.map((d) => safeParseMs(d.date)).filter((x): x is number => x != null)
    return ms.length ? [Math.min(...ms), Math.max(...ms)] : [Date.now(), Date.now()]
  }, [byDay])
  const totals = useMemo(() => ({
    prompts: rows.length,
    sends: rows.reduce((a, r) => a + r.metrics.uses, 0),
    judged: rows.filter((r) => r.current_rating).length,
  }), [rows])
  return { library, candidates, rows, byDay, range, totals }
}

/** When was this prompt last alive: today, this week, quiet, never. */
export function pulse(r: PromptRow): 'today' | 'week' | 'quiet' | 'never' {
  if (!r.metrics.last_used) return 'never'
  const days = (Date.now() - new Date(r.metrics.last_used).getTime()) / 864e5
  if (days < 1.5) return 'today'
  if (days < 14) return 'week'
  return 'quiet'
}

export function DaysOfSends({ byDay, range, picked, onPick }: {
  byDay: ReturnType<typeof useOverview>['byDay']
  range: [number, number]
  picked?: string
  onPick?: (date: string) => void
}) {
  return (
    <div className="min-w-0">
      <div className="text-10 uppercase tracking-wide font-mono text-tertiary mb-2">{t('days · sends per day')}</div>
      <DaySpark byDay={byDay} range={range} width={Math.min(720, Math.max(28, byDay.length * 14))} height={28} onPick={onPick} picked={picked} />
    </div>
  )
}

/** A repeat the library noticed, as a rail row with its own verbs. */
export function NoticedRow({ c, busy, onKeep, onDismiss }: { c: Candidate; busy: boolean; onKeep: () => void; onDismiss: () => void }) {
  return (
    <div className="rounded-input px-8 py-6 flex flex-col gap-4 border border-dashed border-brand/40">
      <div className="flex items-center gap-6 text-10 font-mono">
        <span className="px-4 py-1 rounded-input bg-brand/16 text-brand">{t('sent {n}×', { n: c.sends })}</span>
        <span className="text-tertiary tabular">{c.first_at.slice(5, 10)} → {c.last_at.slice(5, 10)}</span>
        {c.wordings > 1 && <span className="text-tertiary">{t('{n} wordings', { n: c.wordings })}</span>}
      </div>
      <div className="text-12 text-secondary leading-snug" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{c.text}</div>
      <div className="flex gap-6">
        <Button size="sm" disabled={busy} onClick={onKeep}>{t('keep it')}</Button>
        <Button size="sm" variant="ghost" onClick={() => { void copyText(c.text) }}>{t('copy')}</Button>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onDismiss}>{t('not a prompt')}</Button>
      </div>
    </div>
  )
}

const DISMISSED_KEY = 'sp-promptlib-dismissed'

/**
 * Dismissals survive the tab, like the page they came from. They are a
 * preference like any other: written through persistPref, so the server's
 * copy follows — a dismissal kept in this browser alone was undone by the
 * server's older copy at the next start.
 */
export function useDismissed() {
  const [dismissed, setDismissed] = useState<string[]>(() => {
    const kept = readJsonPref<unknown>(DISMISSED_KEY, [])
    return Array.isArray(kept) ? kept.map(String) : []
  })
  const dismiss = (cluster: string) => {
    const next = dismissed.includes(cluster) ? dismissed : [...dismissed, cluster]
    setDismissed(next)
    persistJsonPref(DISMISSED_KEY, next)
  }
  return { dismissed, dismiss }
}


