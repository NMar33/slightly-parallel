/*
 * The runway answers "when": every block a bar on one time axis, with a
 * today-line, task ticks and a red hatched overhang past the bet.
 */
import type { ReactNode } from 'react'

import { hm } from '../../utils/format'
import { useBlockDialogs } from './SprintParts'
import { clamp01, groupOf, pct, verdictOf, type SprintRow } from './sprintsModel'
import type { TaskRow } from './kanban/model'
import { t } from '../../i18n/scope/project'

export function RunwayView({
  sprints, tasksOf, onOpen, onEnd, onMoveMany, onSprintChanged, newSprint,
}: {
  sprints: SprintRow[]
  tasksOf: (id: string | null) => TaskRow[]
  onOpen: (t: TaskRow) => void
  onEnd: (s: SprintRow, retro: string) => void
  onMoveMany: (taskIds: string[], sprintId: string) => void
  onSprintChanged: () => void
  newSprint: ReactNode
}) {
  const { edit, finish, dialogs } = useBlockDialogs({ sprints, tasksOf, onEnd, onMoveMany, onSprintChanged })
  const elapsed = (s: SprintRow) => Math.max(0, (Number(s.bet_days) || 0) - (s.days_left ?? 0))
  const today = Math.max(...sprints.map(elapsed), 0)
  const horizon = Math.max(...sprints.map((s) => (Number(s.bet_days) || 0) + 2), today + 2, 4)
  const x = (day: number) => `${(day / horizon) * 100}%`
  const step = horizon > 14 ? 4 : 2
  return (
    <div className="flex flex-col gap-6">
      <div className="relative rounded-card border border-border-subtle bg-surface px-16 py-12">
        <div className="relative h-14 mb-6" style={{ marginLeft: 170 }}>
          {Array.from({ length: Math.floor(horizon / step) + 1 }, (_, i) => i * step).map((d) => (
            <span key={d} className="absolute top-0 -translate-x-1/2 text-10 font-mono text-tertiary" style={{ left: x(d) }}>
              {d === today ? 'today' : `d${d}`}
            </span>
          ))}
        </div>
        <div className="flex flex-col gap-10">
          {sprints.map((s) => {
            const ts = tasksOf(s.id)
            const bet = Number(s.bet_days) || 0
            const el = elapsed(s)
            const over = s.days_left != null && s.days_left < 0
            const v = verdictOf(s)
            return (
              <div key={s.id} className="flex items-center gap-0">
                <div className="w-[170px] shrink-0 pr-8">
                  <button
                    type="button"
                    onClick={() => edit(s)}
                    title={t('Edit block')}
                    className="text-12 font-medium text-primary truncate text-left hover:text-brand block max-w-full"
                  >
                    {s.name} <span className="text-tertiary font-normal">✎</span>
                  </button>
                  <div className={`text-10 font-mono ${v.cls}`}>
                    {over ? t('overdue {n}d', { n: -s.days_left! }) : s.days_left != null ? t('{n}d left', { n: s.days_left }) : '—'} · {hm(s.human_min)}{s.budget_h ? `/${s.budget_h}h` : ''} {t('· agent')} {hm(s.agent_min)}
                  </div>
                </div>
                <div className="relative flex-1 h-24">
                  <div className="absolute top-[-4px] bottom-[-4px] w-px bg-status-amber/70" style={{ left: x(today) }} aria-hidden />
                  {bet > 0 && (
                    <div className="absolute top-4 h-12 rounded-pill bg-elevated" style={{ left: 0, width: x(bet) }}>
                      <div className="h-full rounded-pill" style={{ width: `${pct(clamp01(el / bet))}%`, backgroundColor: 'color-mix(in oklab, var(--brand) 45%, transparent)' }} />
                    </div>
                  )}
                  {over && bet > 0 && (
                    <div
                      className="absolute top-4 h-12 rounded-r-pill"
                      style={{
                        left: x(bet), width: `calc(${x(el)} - ${x(bet)})`,
                        background: 'repeating-linear-gradient(45deg, color-mix(in srgb, var(--status-red) 55%, transparent) 0 4px, transparent 4px 8px)',
                      }}
                    />
                  )}
                  {ts.map((t, i) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => onOpen(t)}
                      title={`${t.title} — ${t.status} · click to open`}
                      className={`absolute top-0 h-20 w-6 rounded-bar border ${groupOf(t.status) === 'done' ? 'bg-status-green border-status-green' : groupOf(t.status) === 'doing' ? 'bg-brand border-brand' : 'bg-surface border-border-strong'}`}
                      style={{ left: `calc(${x(((i + 1) / (ts.length + 1)) * (bet || horizon))} - 3px)` }}
                    />
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => finish(s)}
                  className="shrink-0 ml-8 h-20 px-8 rounded-pill border border-border-subtle text-10 font-mono text-tertiary hover:text-primary hover:border-border-strong"
                  title={t('End this block and save the retro. The retro is required.')}
                >
                  {t('finish')}
                </button>
              </div>
            )
          })}
        </div>
      </div>
      <div className="flex items-center gap-8">
        {newSprint}
        <span className="text-10 font-mono text-tertiary">{t('bar: planned days · fill: days spent · hatched: overdue · ticks: tasks, click to open')}</span>
      </div>
      {dialogs}
    </div>
  )
}
