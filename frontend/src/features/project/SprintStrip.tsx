import { useEffect, useRef, useState } from 'react'
import { useQueries, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { toast } from 'sonner'
import { fail, getJson, postJson } from '../../lib/getJson'
import type { SprintBoardAnswer, SprintBoardRow } from '../tasks/data'

import { StartBlockDialog } from './StartBlockDialog'
import { Modal } from '../../components/Modal'
import { Button } from '../../components/primitives'
import { t } from '../../i18n/scope/project'

/**
 * SprintStrip — sprints as blocks of work, above the board.
 *
 * A sprint is a named block ("Authorization", "Bug fixing") with two limits:
 * a bet in days and a human-hours budget. Everything on the chip is derived —
 * tasks done/total, days left, human hours (timer entries × share), agent
 * hours (captured sessions that mentioned the sprint's tasks; a session
 * counts once, whole). Clicking a chip filters the board to that block and
 * makes new tasks join it; dropping a card on a chip assigns it. At most
 * three run in parallel. Ending one requires a retro, in words.
 */

type SprintRow = SprintBoardRow

/** The boards of every project, one row per sprint (a board shared by two projects lists its sprints once). */
function mergeBoards(results: Array<{ data?: SprintBoardAnswer }>): { rows: SprintRow[]; noSprint: number } {
  const seen = new Set<string>(); const rows: SprintRow[] = []
  let noSprint = 0
  for (const r of results) {
    const d = r.data
    noSprint += Number(d?.no_sprint) || 0
    for (const s of Array.isArray(d?.sprints) ? d.sprints : []) {
      if (!seen.has(s.id)) { seen.add(s.id); rows.push(s) }
    }
  }
  return { rows, noSprint }
}

const h = (min: number) => (min >= 60 ? t('{n}h', { n: Math.round(min / 6) / 10 }) : min > 0 ? t('{n}m', { n: min }) : t('{n}h', { n: 0 }))

export function SprintStrip({
  projects, filter, onFilter, onAssignTask, tick,
}: {
  projects: string[]
  filter: string | null           // sprint id | 'none' | null (= all)
  onFilter: (f: string | null) => void
  onAssignTask: (taskId: string, sprintId: string) => void
  tick: number
}) {
  const [creating, setCreating] = useState(false)
  const [ending, setEnding] = useState<SprintRow | null>(null)
  const home = projects[0] ?? ''
  // Under the sprint board's key, so a write that reads the board again
  // reads these too; a project whose board fails counts as none.
  const { rows, noSprint } = useQueries({
    queries: projects.map((p) => ({
      queryKey: ['sprints', 'board', p, 'answer'],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        getJson<SprintBoardAnswer>(`/api/sprints/board?project=${encodeURIComponent(p)}`, signal),
    })),
    combine: mergeBoards,
  })
  const qc = useQueryClient()
  const refresh = () => void qc.invalidateQueries({ queryKey: ['sprints', 'board'] })
  // The board's own writes bump `tick`: read again then, not on the first draw.
  const seenTick = useRef(tick)
  useEffect(() => {
    if (seenTick.current === tick) return
    seenTick.current = tick
    void qc.invalidateQueries({ queryKey: ['sprints', 'board'] })
  }, [tick, qc])

  if (rows.length === 0 && noSprint === 0 && !creating) {
    return (
      <div className="flex items-center gap-6">
        <button type="button" onClick={() => setCreating(true)} className="inline-flex items-center gap-4 h-24 px-8 rounded-pill border border-dashed border-border-default text-11 font-mono text-tertiary hover:text-brand hover:border-brand">
          <Plus size={11} aria-hidden /> {t('sprint')}
        </button>
        <span className="text-11 text-tertiary">{t('A block of work with planned days and an hour budget. Drag tasks onto it from the board.')}</span>
        {creating && null}
        {renderCreate()}
      </div>
    )
  }

  function renderCreate() {
    if (!creating) return null
    return (
      <StartBlockDialog
        projectCode={home}
        active={rows.map((r) => ({ id: r.id, name: r.name }))}
        backlog={[]}
        onClose={() => setCreating(false)}
        onStarted={() => { setCreating(false); refresh() }}
      />
    )
  }

  return (
    <div className="flex items-center gap-6 flex-wrap">
      {rows.map((s) => {
        const active = filter === s.id
        const overdue = s.days_left != null && s.days_left < 0
        const overBudget = s.budget_h != null && Number(s.budget_h) > 0 && s.human_min / 60 > Number(s.budget_h)
        return (
          <span
            key={s.id}
            onDragOver={(e) => { e.preventDefault() }}
            onDrop={(e) => {
              e.preventDefault()
              const id = e.dataTransfer.getData('text/plain')
              if (id && !id.startsWith('__')) onAssignTask(id, s.id)
            }}
            className={`inline-flex items-center gap-6 h-24 pl-10 pr-6 rounded-pill border text-11 font-mono transition-colors ${
              active ? 'border-brand bg-brand text-on-brand' : 'border-border-default text-secondary hover:border-brand'
            }`}
            title={`planned ${s.bet_days ?? '—'}d · budget ${s.budget_h ?? '—'}h · agent time counts the chats that mention this sprint's tasks · drop a card here to add it`}
          >
            <button type="button" onClick={() => onFilter(active ? null : s.id)} className="inline-flex items-center gap-6">
              <span className="font-semibold">{s.name}</span>
              <span className={active ? 'opacity-90' : 'text-tertiary'}>{s.tasks_done}/{s.tasks_total}</span>
              <span className={overdue ? 'text-status-red font-semibold' : active ? 'opacity-90' : 'text-tertiary'}>
                {s.days_left == null ? '' : overdue ? t('overdue {n}d', { n: -s.days_left }) : t('{n}d left', { n: s.days_left })}
              </span>
              <span className={overBudget ? 'text-status-amber font-semibold' : active ? 'opacity-90' : 'text-tertiary'}>
                {h(s.human_min)}{s.budget_h ? `/${s.budget_h}h` : ''}
              </span>
              <span className={active ? 'opacity-90' : 'text-tertiary'} title={t('agent time')}>{t('agent')} {h(s.agent_min)}</span>
            </button>
            <button
              type="button"
              onClick={() => setEnding(s)}
              aria-label={`Finish sprint ${s.name}`}
              title={t('Finish (a retro is required)')}
              className={`h-14 w-14 inline-flex items-center justify-center rounded-pill text-10 ${active ? 'hover:bg-base/20' : 'text-tertiary hover:text-primary hover:bg-hover'}`}
            >
              ✓
            </button>
          </span>
        )
      })}
      <button
        type="button"
        onClick={() => onFilter(filter === 'none' ? null : 'none')}
        className={`h-24 px-10 rounded-pill border text-11 font-mono ${
          filter === 'none' ? 'border-brand bg-brand text-on-brand' : 'border-border-default text-tertiary hover:text-primary hover:border-brand'
        }`}
      >
        {t('no sprint ·')} {noSprint}
      </button>
      <button
        type="button"
        onClick={() => {
          if (rows.length >= 3) { toast.error(t('Three sprints are running. Finish one first.')); return }
          setCreating(true)
        }}
        className="inline-flex items-center gap-4 h-24 px-8 rounded-pill border border-dashed border-border-default text-11 font-mono text-tertiary hover:text-brand hover:border-brand"
        title={t('New sprint (max 3 in parallel)')}
      >
        <Plus size={11} aria-hidden /> {t('sprint')}
      </button>
      {renderCreate()}
      {ending && (
        <EndSprintDialog
          sprint={ending}
          onClose={() => setEnding(null)}
          onEnded={() => { setEnding(null); onFilter(null); refresh() }}
        />
      )}
    </div>
  )
}

function EndSprintDialog({
  sprint, onClose, onEnded,
}: {
  sprint: SprintRow
  onClose: () => void
  onEnded: () => void
}) {
  const [retro, setRetro] = useState('')
  const facts = `planned ${sprint.bet_days ?? '—'}d, ${sprint.days_left != null && sprint.days_left < 0 ? `ran ${-sprint.days_left}d over` : 'on plan'} · done ${sprint.tasks_done}/${sprint.tasks_total} · ${h(sprint.human_min)} human${sprint.budget_h ? ` of ${sprint.budget_h}h` : ''} · ${h(sprint.agent_min)} agent`
  const end = async () => {
    if (!retro.trim()) return
    const now = new Date()
    const yy = String(now.getFullYear()).slice(-2)
    const today = `${yy}${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
    try {
      await postJson(`/api/sprints/${encodeURIComponent(sprint.id)}/update`, {
        status: 'ended', ended_date: today,
        goals_shipped_n: sprint.tasks_done,
        l2: `${facts}\n\n${retro.trim()}`,
      })
    } catch (e) { fail(e); return }
    onEnded()
  }
  return (
    <Modal label={t('Finish sprint')} onClose={onClose} width="w-[460px]">
      <div className="flex flex-col gap-10">
        <h2 className="text-14 font-semibold text-primary">{t('Finish “{name}”', { name: sprint.name })}</h2>
        <p className="text-11 font-mono text-tertiary">{facts}</p>
        <textarea autoFocus value={retro} onChange={(e) => setRetro(e.target.value)} rows={4}
          placeholder={t('Required: what happened, in your own words')}
          className="bg-elevated text-primary border border-border-default rounded-input px-10 py-6 text-12 leading-relaxed" />
        <div className="flex items-center gap-8 justify-end">
          <Button variant="text" size="bare" onClick={onClose}>{t('cancel')}</Button>
          <Button variant="primary" size="sm" onClick={() => void end()} disabled={!retro.trim()}>
            {t('end sprint')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
