/*
 * Small parts the runway and the blocks board share: the status dot, the
 * start button, the batch move menu, and the two windows over a block —
 * edit it, or finish it with the retro.
 */
import { useState, type ReactNode } from 'react'
import { Plus } from 'lucide-react'
import { usePopover } from '../../hooks/usePopover'

import { hm } from '../../utils/format'
import { Modal } from '../../components/Modal'
import { Button } from '../../components/primitives'
import { PillRow } from '../../components/PillRow'
import { LABEL } from '../promptlib/taskstyle'
import { EditBlockDialog, StartBlockDialog } from './StartBlockDialog'
import { groupOf, useSprintDetail, type SprintRow } from './sprintsModel'
import type { TaskRow } from './kanban/model'
import { t, tn } from '../../i18n/scope/project'

export function StatusDot({ status }: { status: string }) {
  const g = groupOf(status)
  const cls = g === 'done' ? 'bg-status-green border-status-green' : g === 'doing' ? 'bg-brand border-brand' : 'bg-transparent border-border-strong'
  return <span title={status} className={`h-10 w-10 rounded-pill border shrink-0 ${cls}`} />
}

export function NewSprint({
  projectCode, active, backlog, onStarted,
}: {
  projectCode: string
  active: Array<{ id: string; name: string }>
  backlog: Array<{ id: string; title: string }>
  onStarted: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-4 h-24 px-8 rounded-pill border border-dashed border-border-default text-11 font-mono text-tertiary hover:text-brand hover:border-brand"
      >
        <Plus size={11} aria-hidden /> {t('start a block')}
      </button>
      {open && (
        <StartBlockDialog
          projectCode={projectCode}
          active={active}
          backlog={backlog}
          onClose={() => setOpen(false)}
          onStarted={() => { setOpen(false); onStarted() }}
        />
      )}
    </>
  )
}

/** The batch handle of the blocks board: move a whole group at once. */
export function BatchMenu({
  label, targets, onPick,
}: {
  label: string
  targets: Array<{ id: string; name: string }>
  onPick: (sprintId: string) => void
}) {
  const { open, setOpen, rootRef } = usePopover()
  if (targets.length === 0) return null
  return (
    <span ref={rootRef} className="relative inline-flex">
      <Button
        variant="text"
        size="bare"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={t('Move all {group}', { group: label })}
        title={t('Move all {group} to another block', { group: label })}
        className="leading-none"
      >
        {t('⧉ all →')}
      </Button>
      {open && (
        <>
          <div role="menu" className="absolute left-0 top-[calc(100%+4px)] z-30 min-w-[160px] rounded-card border border-border-default bg-surface shadow-lg py-4">
            <div className="px-10 py-2 text-10 font-mono text-tertiary">{label} →</div>
            {targets.map((target) => (
              <button
                key={target.id || 'backlog'}
                type="button"
                role="menuitem"
                onClick={() => { onPick(target.id); setOpen(false) }}
                className="w-full text-left px-10 py-4 text-11 font-mono text-secondary hover:bg-hover hover:text-primary"
              >
                {target.name}
              </button>
            ))}
          </div>
        </>
      )}
    </span>
  )
}

/**
 * Finishing a block is a settlement: the dialog lays the bet against what
 * actually happened, decides where the open tasks go (backlog by default,
 * or another running block), and takes the retro — required, in words.
 */
function FinishBlockDialog({
  sprint, leftovers, otherBlocks, onClose, onFinish,
}: {
  sprint: SprintRow
  /** Open (not done) tasks still on the block. */
  leftovers: TaskRow[]
  otherBlocks: Array<{ id: string; name: string }>
  onClose: () => void
  onFinish: (retro: string, moveTo: string | null) => void
}) {
  const [retro, setRetro] = useState('')
  const [moveTo, setMoveTo] = useState<string>('')  // '' = backlog
  // The goals set when the bet was placed come back at settlement; a failed
  // read leaves the section out, the retro is still asked for.
  const l3 = useSprintDetail(sprint.id).data?.l3
  const goals = Array.isArray(l3) ? l3.map(String).filter(Boolean) : []
  const over = sprint.days_left != null && sprint.days_left < 0
  const rows: Array<[string, string, boolean]> = [
    [t('planned'), t('{n} days', { n: sprint.bet_days ?? '—' }), false],
    [t('it ran'), over ? t('{n} days — {over} over', { n: (Number(sprint.bet_days) || 0) + -sprint.days_left!, over: -sprint.days_left! }) : t('{n} days, on plan', { n: (Number(sprint.bet_days) || 0) - (sprint.days_left ?? 0) }), over],
    [t('your hours'), (sprint.budget_h ? t('{used} of {n}h budgeted', { used: hm(sprint.human_min), n: sprint.budget_h }) : hm(sprint.human_min)), !!sprint.budget_h && sprint.human_min / 60 > Number(sprint.budget_h)],
    [t('agent hours'), hm(sprint.agent_min), false],
    [t('done'), t('{done} of {total} tasks', { done: sprint.tasks_done, total: sprint.tasks_total }), false],
  ]
  return (
    <Modal label={`Finish ${sprint.name}`} onClose={onClose} width="w-[520px]" padding="p-20">
      <div className="flex flex-col gap-14">
        <div>
          <h3 className="text-20 font-semibold text-primary">{t('Finish “{name}”', { name: sprint.name })}</h3>
          <p className="text-12 text-tertiary mt-2">{t('Below are the block\'s final numbers. Write a retro of what happened before ending it, the text is required.')}</p>
        </div>

        {/* Bet vs reality */}
        <dl className="grid grid-cols-[110px_1fr] gap-x-12 gap-y-4 text-12">
          {rows.map(([k, v, warn]) => (
            <div key={k} className="contents">
              <dt className={LABEL}>{k}</dt>
              <dd className={`font-mono ${warn ? 'text-status-red' : 'text-secondary'}`}>{v}</dd>
            </div>
          ))}
        </dl>

        {goals.length > 0 && (
          <div className="flex flex-col gap-3 rounded-input border border-border-subtle bg-elevated/50 p-10">
            <span className={LABEL}>{t('goals')}</span>
            {goals.map((g, i) => (
              <span key={i} className="text-12 text-secondary">· {g}</span>
            ))}
            <span className="text-11 text-tertiary italic">{t('Say in the retro which of these are met')}</span>
          </div>
        )}

        {/* Leftovers */}
        {leftovers.length > 0 && (
          <div className="flex flex-col gap-6 rounded-input border border-border-subtle bg-elevated/50 p-10">
            <div className="text-12 text-primary font-medium">
              {tn(leftovers.length, '{n} task on this block is not done. Choose the backlog or another running block below, and it is moved there when the block is finished.', '{n} tasks on this block are not done. Choose the backlog or another running block below, and they are moved there when the block is finished.')}
            </div>
            <PillRow
              label={t('Move the leftovers to')}
              value={moveTo}
              onChange={setMoveTo}
              options={[['', t('back to Backlog')], ...otherBlocks.map((b) => [b.id, `→ ${b.name}`] as const)]}
            />
            <div className="text-11 text-tertiary truncate">
              {leftovers.slice(0, 3).map((t) => t.title).join(' · ')}{leftovers.length > 3 ? ` +${leftovers.length - 3}` : ''}
            </div>
          </div>
        )}

        <textarea
          autoFocus
          value={retro}
          onChange={(e) => setRetro(e.target.value)}
          rows={4}
          placeholder={t('Required: what happened, in your own words')}
          className="bg-elevated text-primary border border-border-default rounded-input px-10 py-8 text-12 leading-relaxed"
        />
        <div className="flex items-center gap-8 justify-end">
          <button type="button" onClick={onClose} className="text-12 font-mono text-tertiary hover:text-primary">{t('cancel')}</button>
          <Button
            variant="primary"
            size="md"
            onClick={() => retro.trim() && onFinish(retro.trim(), leftovers.length > 0 ? (moveTo || null) : null)}
            disabled={!retro.trim()}
            title={retro.trim() ? t('End this block and save the retro') : t('The retro is required')}
          >
            {t('End this block and save the retro')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/**
 * The edit and finish windows of a view's blocks. Finishing moves the open
 * tasks where the dialog says, then ends the block with its retro.
 */
export function useBlockDialogs({ sprints, tasksOf, onEnd, onMoveMany, onSprintChanged }: {
  sprints: SprintRow[]
  tasksOf: (id: string | null) => TaskRow[]
  onEnd: (s: SprintRow, retro: string) => void
  onMoveMany: (taskIds: string[], sprintId: string) => void
  onSprintChanged: () => void
}): { edit: (s: SprintRow) => void; finish: (s: SprintRow) => void; dialogs: ReactNode } {
  const [ending, setEnding] = useState<SprintRow | null>(null)
  const [editingSprint, setEditingSprint] = useState<SprintRow | null>(null)
  const dialogs = (
    <>
      {editingSprint && (
        <EditBlockDialog
          sprint={editingSprint}
          onClose={() => setEditingSprint(null)}
          onSaved={() => { setEditingSprint(null); onSprintChanged() }}
        />
      )}
      {ending && (
        <FinishBlockDialog
          sprint={ending}
          leftovers={tasksOf(ending.id).filter((t) => groupOf(t.status) !== 'done')}
          otherBlocks={sprints.filter((sp) => sp.id !== ending.id).map((sp) => ({ id: sp.id, name: sp.name }))}
          onClose={() => setEnding(null)}
          onFinish={(retro, moveTo) => {
            const open = tasksOf(ending.id).filter((t) => groupOf(t.status) !== 'done')
            if (open.length > 0) onMoveMany(open.map((t) => t.id), moveTo ?? '')
            onEnd(ending, retro)
            setEnding(null)
          }}
        />
      )}
    </>
  )
  return { edit: setEditingSprint, finish: setEnding, dialogs }
}
