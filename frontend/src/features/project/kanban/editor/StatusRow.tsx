/*
 * The task window's status row: the column chips, the auto / evidence
 * ticks of the agent-done loop, and the "an agent reported this done"
 * line under them. Moved out of TaskEditor.tsx; the window owns the state.
 */

import { formatStamp } from '../../../../utils/dateUtils'
import type { TaskRow } from '../model'
import { t } from '../../../../i18n/scope/project'

const STATUS_OPTS = [
  { k: 'unclassified', label: t('Unclassified') },
  { k: 'backlog',      label: t('Backlog') },
  { k: 'next',         label: t('Next') },
  { k: 'agent',         label: t('From agents') },
  { k: 'todo',          label: t('To do') },
  { k: 'parked',        label: t('To do · parked') },
  { k: 'review-later',  label: t('Review later') },
  { k: 'doing',         label: t('Doing') },
  { k: 'review',        label: t('Review') },
  { k: 'done',          label: t('Done') },
  { k: 'done-archived', label: t('Done archived') },
]

export function StatusRow({ status, setStatus, autoManage, setAutoManage, evidenceRequired, setEvidenceRequired }: {
  status: string
  setStatus: (s: string) => void
  autoManage: boolean
  setAutoManage: (v: boolean) => void
  evidenceRequired: boolean
  setEvidenceRequired: (v: boolean) => void
}) {
  return (
    <div className="flex flex-wrap gap-4">
      {STATUS_OPTS.map((s) => (
        <button
          key={s.k}
          type="button"
          aria-pressed={status === s.k}
          onClick={() => setStatus(s.k)}
          className={`px-8 py-4 rounded-input border font-mono text-11 transition-colors ${
            status === s.k
              ? 'bg-brand/16 text-brand border-brand'
              : 'bg-elevated text-secondary border-border-default hover:text-primary'
          }`}
        >
          {s.label}
        </button>
      ))}
      <span className="mx-4 w-px self-stretch bg-border-subtle" aria-hidden />
      <label className="inline-flex items-center gap-4 px-6 text-11 font-mono text-secondary cursor-pointer" title={t('When an agent reports done: move to Review. When off: show a badge.')}>
        <input type="checkbox" checked={autoManage} onChange={(e) => setAutoManage(e.target.checked)} className="accent-[var(--brand)]" />
        {t('auto')}
      </label>
      <label className="inline-flex items-center gap-4 px-6 text-11 font-mono text-secondary cursor-pointer" title={t('An agent that reports this task done is asked for proof, text and screenshots, as the evidence prompt below says.')}>
        <input type="checkbox" checked={evidenceRequired} onChange={(e) => setEvidenceRequired(e.target.checked)} className="accent-[var(--brand)]" />
        {t('evidence')}
      </label>
    </div>
  )
}

/** An agent said it is done: who, when, what it said — until the next move. */
export function AgentDoneLine({ task }: { task: TaskRow }) {
  return (
    <div className="text-11 font-mono flex items-baseline gap-6 flex-wrap" style={{ color: 'var(--status-amber)' }}>
      <span>⚑ {task.agent_done_by} {t('reported this done')}</span>
      <span className="text-tertiary">{formatStamp(task.agent_done_at)}</span>
      {task.agent_done_note && <span className="text-secondary">— “{task.agent_done_note}”</span>}
      <span className="text-tertiary">{t('· your next status change clears this')}</span>
    </div>
  )
}
