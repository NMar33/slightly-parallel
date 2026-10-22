import { useEffect, useRef, useState } from 'react'
import {
  Check,
} from 'lucide-react'

import { COLOR, DAY, dayList, ms, norm, type TTask } from './taskViz'
import { t, tn, locale } from '../../i18n/scope/project'
import { dayMonth } from '../../lib/months'
const mdd = (t: number) => dayMonth(new Date(t))

/* ================================= Days ================================== */

/**
 * Days — the window as a strip of day columns, five in view at a time and
 * scrollable back up to a fortnight. It opens on today (the strip starts
 * scrolled to its right edge), because the day you are in is the one you
 * came to read; a card is a button that opens the task.
 */
export function Days({
  tasks, since, now, onOpenTask,
}: {
  tasks: TTask[]
  since: number
  now: number
  /** Clicking a card opens the task — the panel is a way in, not a poster. */
  onOpenTask?: (id: string) => void
}) {
  // At most a fortnight, however wide the window is set.
  const days = dayList(Math.max(since, now - 13 * DAY), now)
  const strip = useRef<HTMLDivElement>(null)
  // A busy day hides its tail behind "+N more" — clicking opens the day in
  // place, scrolling inside its own column so the strip keeps its height.
  const [opened, setOpened] = useState<Set<number>>(() => new Set())
  const toggleDay = (d: number) => setOpened((cur) => {
    const next = new Set(cur)
    if (next.has(d)) next.delete(d); else next.add(d)
    return next
  })
  const SHOWN = 7
  useEffect(() => {
    const el = strip.current
    if (el) el.scrollLeft = el.scrollWidth
  }, [days.length])
  const cols = days.map((d) => {
    const cards: Array<{ t: TTask; chips: React.ReactNode[]; weight: number }> = []
    for (const task of tasks) {
      const evs = task.events.map((e) => ({ ...e, ms: ms(e.at) })).filter((e) => e.ms >= d && e.ms < d + DAY)
      if (!evs.length) continue
      const chips: React.ReactNode[] = []
      let weight = 0
      const done = evs.find((e) => e.kind === 'status' && e.to === 'done')
      const moved = evs.filter((e) => e.kind === 'status' && e.to !== 'done')
      const created = evs.find((e) => e.kind === 'created')
      const chats = evs.filter((e) => e.kind === 'mention').length
      const edits = evs.filter((e) => e.kind === 'edit').length
      if (done) { chips.push(<span key="d" className="inline-flex items-center gap-2 text-status-green"><Check size={10} aria-hidden />{t('done')}</span>); weight += 3 }
      for (const m of moved.slice(0, 1)) { chips.push(<span key="m" style={{ color: COLOR[norm(m.to)] }}>→ {norm(m.to)}</span>); weight += 2 }
      if (created) { chips.push(<span key="c" className="text-secondary">{t('new')}</span>); weight += 2 }
      if (chats) { chips.push(<span key="ch" className="text-status-amber">◆ {chats}</span>); weight += 1 }
      if (edits && !chips.length) chips.push(<span key="e" className="text-tertiary">✎ {edits}</span>)
      cards.push({ t: task, chips, weight })
    }
    cards.sort((a, b) => b.weight - a.weight)
    return { d, cards }
  })
  return (
    <div>
      <div
        ref={strip}
        className="flex gap-8 overflow-x-auto pb-4"
        role="group"
        aria-label={t('{days}, scroll for the earlier ones', { days: tn(cols.length, '{n} day', '{n} days') })}
      >
      {cols.map(({ d, cards }) => {
        const isToday = new Date(d).toDateString() === new Date(now).toDateString()
        return (
          <div
            key={d}
            className={`rounded-card border ${isToday ? 'border-brand' : 'border-border-subtle'} bg-base flex flex-col min-h-[220px] shrink-0`}
            style={{ flexBasis: 'calc((100% - 32px) / 5)', minWidth: 150 }}
          >
            <header className={`px-8 py-6 border-b ${isToday ? 'border-brand/40' : 'border-border-subtle'} flex items-baseline gap-6`}>
              <span className="text-11 font-semibold text-primary">{new Date(d).toLocaleDateString(locale(), { weekday: 'short' })}</span>
              <span className="text-10 font-mono text-tertiary">{mdd(d)}</span>
              {isToday && <span className="ml-auto text-10 font-mono px-4 rounded-pill" style={{ backgroundColor: 'var(--brand)', color: 'var(--bg-base)' }}>{t('today')}</span>}
            </header>
            <div
              className="flex flex-col gap-4 p-6"
              style={opened.has(d) && cards.length > SHOWN ? { maxHeight: 460, overflowY: 'auto' } : undefined}
            >
              {cards.length === 0 && <span className="text-10 font-mono text-tertiary/60 px-2 py-4">—</span>}
              {(opened.has(d) ? cards : cards.slice(0, SHOWN)).map(({ t, chips }) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => onOpenTask?.(t.id)}
                  disabled={!onOpenTask}
                  title={onOpenTask ? `${t.title} · open the task` : t.title}
                  className={`rounded-input bg-surface border border-border-subtle px-6 py-4 flex flex-col gap-2 text-left ${onOpenTask ? 'hover:border-brand cursor-pointer' : 'cursor-default'}`}
                >
                  <span className="text-11 text-primary leading-snug" style={{ display: '-webkit-box', WebkitBoxOrient: 'vertical', WebkitLineClamp: 2, overflow: 'hidden' }}>{t.title}</span>
                  <span className="flex items-center gap-6 flex-wrap text-10 font-mono">{chips}</span>
                </button>
              ))}
              {cards.length > SHOWN && (
                <button
                  type="button"
                  onClick={() => toggleDay(d)}
                  aria-expanded={opened.has(d)}
                  className="text-10 font-mono text-tertiary hover:text-brand px-2 py-2 text-left"
                >
                  {opened.has(d) ? t('− show less') : t('+{n} more', { n: cards.length - SHOWN })}
                </button>
              )}
            </div>
          </div>
        )
      })}
      </div>
      {cols.length > 5 && (
        <p className="text-10 font-mono text-tertiary">
          {cols.length} {t('days · five at a time — scroll left for the earlier ones')}
        </p>
      )}
    </div>
  )
}
