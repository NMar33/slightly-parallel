import { useMemo, useState } from 'react'
import { useProjectTasks } from '../tasks/data'
import { Modal } from '../../components/Modal'
import { type Block, hm } from './deck'

/**
 * The few pieces every /sprints design needs identically — finishing a
 * block, splitting a timer's attention, drawing a bar. Everything with a
 * layout opinion belongs to the pages, not here.
 */

/** Finishing is a settlement: the facts are shown, the retro is required. */
export function FinishDialog({
  block, onClose, onFinish,
}: {
  block: Block
  onClose: () => void
  onFinish: (retro: string) => void
}) {
  const [retro, setRetro] = useState('')
  const [busy, setBusy] = useState(false)
  const over = block.days_left != null && block.days_left < 0
  const budget = Number(block.budget_h) || 0
  const rows: Array<[string, string, boolean]> = [
    [t('planned'), t('{n} days', { n: block.bet_days ?? '—' }), false],
    [t('actual'), t('{n} days', { n: block.ran_days ?? '—' }) + (over ? t(' · {n} over', { n: -(block.days_left ?? 0) }) : ''), over],
    [t('your hours'), (budget ? t('{used} of {budget}h', { used: hm(block.human_min), budget }) : hm(block.human_min)), budget > 0 && block.human_min / 60 > budget],
    [t('agent hours'), hm(block.agent_min), false],
    [t('tasks done'), t('{tasks_done} of {tasks_total}', { tasks_done: block.tasks_done, tasks_total: block.tasks_total }), false],
  ]
  const open = block.tasks.filter((it) => !['done', 'done-archived'].includes(String(it.status || '').toLowerCase()))
  return (
    <Modal label={t('Finish {name}', { name: block.name })} onClose={onClose} width="w-[520px]" padding="p-20">
      <div className="flex flex-col gap-12">
        <div>
          <h3 className="text-20 font-semibold text-primary">{t('Finish “{name}”', { name: block.name })}</h3>
          <p className="text-12 text-tertiary mt-2">{t('{project}. Below are the block\'s final numbers. Write a retro of what happened before ending it, the text is required.', { project: block.project })}</p>
        </div>
        <dl className="grid grid-cols-[110px_1fr] gap-x-12 gap-y-3 text-12">
          {rows.map(([k, v, warn]) => (
            <div key={k} className="contents">
              <dt className="text-11 uppercase tracking-wide font-mono text-tertiary">{k}</dt>
              <dd className={`font-mono ${warn ? 'text-status-red' : 'text-secondary'}`}>{v}</dd>
            </div>
          ))}
        </dl>
        {open.length > 0 && (
          <p className="text-12 text-tertiary rounded-input border border-border-subtle bg-elevated/50 p-8">
            {tn(open.length, '{n} task on this block is not done.', '{n} tasks on this block are not done.')}{' '}{t('Finishing does not move them: they stay attached to this block, and this page stops listing them because it shows running blocks only.')}
          </p>
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
          <button
            type="button"
            disabled={!retro.trim() || busy}
            onClick={() => { setBusy(true); onFinish(retro.trim()) }}
            className="px-16 py-8 rounded-input bg-brand text-on-brand font-mono text-13 font-semibold disabled:opacity-40"
          >
            {busy ? t('Ending…') : t('End this block and save the retro')}
          </button>
        </div>
      </div>
    </Modal>
  )
}

/** A two-tone bar: what is spent against what was promised. */
export function Meter({
  frac, tone, height = 4, over,
}: {
  frac: number
  tone: string
  height?: number
  over?: boolean
}) {
  const pct = Math.max(0, Math.min(1, frac)) * 100
  return (
    <div className="w-full rounded-pill bg-elevated overflow-hidden" style={{ height }}>
      <div
        className="h-full rounded-pill"
        style={{
          width: `${pct}%`,
          backgroundColor: over ? 'var(--status-red)' : tone,
          backgroundImage: over ? 'repeating-linear-gradient(45deg, var(--hatch) 0 3px, transparent 3px 6px)' : undefined,
        }}
      />
    </div>
  )
}

/** The attribution split of a running timer, 10–100%. */
export function ShareSlider({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <label className="inline-flex items-center gap-4 text-10 font-mono text-tertiary" title={t('Share of this time counted for this block')}>
      <input
        type="range" min={10} max={100} step={10} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-[70px] accent-[var(--brand)]"
        aria-label={t('Share of time')}
      />
      <span className={value < 100 ? 'text-status-amber' : 'text-secondary'}>{value}%</span>
    </label>
  )
}

import { StartBlockDialog } from '../project/StartBlockDialog'
import type { Deck } from './deck'

import { t, tn } from '../../i18n/scope/views'
/**
 * Starting a block from a cross-project page: the only extra question is
 * which project it belongs to, and then the real dialog does the rest.
 */
export function StartBlockAnywhere({ deck, onStarted }: { deck: Deck; onStarted: () => void }) {
  const [picking, setPicking] = useState(false)
  const [project, setProject] = useState<string | null>(null)
  // The picked project's tasks: the same read its own panels use.
  const tasks = useProjectTasks(project ?? '', !!project).data
  const backlog = useMemo(() => (tasks ?? [])
    .filter((it) => !it.archived_at && !(it.sprint_id || '') && !['done', 'done-archived'].includes(String(it.status || '').toLowerCase()))
    .slice(0, 40)
    .map((it) => ({ id: String(it.id), title: String(it.title ?? ''), status: String(it.status ?? '') })), [tasks])

  const active = (code: string) => deck.blocks.filter((b) => b.project === code).map((b) => ({
    id: b.id, name: b.name, bet_days: b.bet_days ?? null, budget_h: b.budget_h ?? null,
  }))

  return (
    <>
      <button
        type="button"
        onClick={() => setPicking(true)}
        className="h-20 px-10 rounded-pill border border-border-default text-10 font-mono text-secondary hover:border-brand hover:text-brand"
        title={t('Start a new block of work in one of your projects')}
      >
        {t('+ start a block')}
      </button>
      {picking && !project && (
        <ProjectPickerDialog deck={deck} onPick={setProject} onClose={() => setPicking(false)} />
      )}
      {project && (
        <StartBlockDialog
          projectCode={project}
          active={active(project)}
          backlog={backlog}
          onClose={() => { setProject(null); setPicking(false) }}
          onStarted={() => { setProject(null); setPicking(false); onStarted() }}
        />
      )}
    </>
  )
}

/** The one extra question: which project the new block belongs to. */
function ProjectPickerDialog({ deck, onPick, onClose }: { deck: Deck; onPick: (code: string) => void; onClose: () => void }) {
  return (
    <Modal label={t('Which project')} onClose={onClose} width="w-[380px]">
      <div className="flex flex-col gap-10">
        <div>
          <h3 className="text-14 font-semibold text-primary">{t('Choose a project for the new block')}</h3>
          <p className="text-11 text-tertiary mt-1">{t('Three blocks run in parallel per project at most.')}</p>
        </div>
        <div className="flex flex-col gap-4">
          {deck.projects.map((code) => {
            const n = deck.blocks.filter((b) => b.project === code).length
            const full = n >= 3
            return (
              <button
                key={code}
                type="button"
                disabled={full}
                onClick={() => onPick(code)}
                className={`flex items-baseline gap-8 rounded-input border px-10 py-8 text-left ${full ? 'border-border-subtle opacity-50 cursor-not-allowed' : 'border-border-default hover:border-brand'}`}
              >
                <span className="text-13 text-primary">{code}</span>
                <span className="text-10 font-mono text-tertiary ml-auto">
                  {n} {t('of 3 running ·')}{' '}{deck.backlog[code] ?? 0} {t('waiting')}{full ? ' · full' : ''}
                </span>
              </button>
            )
          })}
        </div>
        <button type="button" onClick={onClose} className="self-end text-11 font-mono text-tertiary hover:text-primary">{t('cancel')}</button>
      </div>
    </Modal>
  )
}
