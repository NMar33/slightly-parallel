import { entryText } from '../../lib/entryText'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { fail, postJson } from '../../lib/getJson'
import { useSprintDetail } from './sprintsModel'

import { Confirm } from '../../components/Confirm'
import { Modal } from '../../components/Modal'
import { Button } from '../../components/primitives'
import { nowStamp, OPERATOR_ACTOR } from './types'
import { LABEL } from '../promptlib/taskstyle'
import { t, tn, locale } from '../../i18n/scope/project'

/**
 * StartBlockDialog — starting a sprint should feel like placing a bet,
 * not filling a form.
 *
 * The dialog shows the three slots (who's running, which slot this block
 * takes), lets the bet be picked in one click (day chips → a real end
 * date), reads the hours budget back as a per-day intensity ("≈1.7h/day —
 * side-project pace"), and can take backlog tasks aboard immediately.
 * The footer says the whole bet in one sentence before it's placed.
 */

type ActiveSprint = { id: string; name: string }
type BacklogTask = { id: string; title: string }

const DAY_CHIPS = [3, 5, 7, 14, 21]
const HOUR_CHIPS = [4, 8, 12, 20, 40]
const NAME_HINTS = [t('Bug fixing'), t('Run to MVP'), t('Polish pass'), t('Release v0.2'), t('Docs & onboarding')]

function endDateOf(betDays: number): string {
  const d = new Date()
  d.setDate(d.getDate() + betDays)
  return d.toLocaleDateString(locale(), { weekday: 'short', month: 'short', day: 'numeric' })
}

function intensityOf(budgetH: number, betDays: number): string {
  if (!budgetH || !betDays) return ''
  const perDay = budgetH / betDays
  const label =
    perDay < 1 ? 'light'
    : perDay < 3 ? t('side-project pace')
    : perDay < 6 ? 'heavy'
    : t('full time')
  return t('≈{n}h a day — {label}', { n: Math.round(perDay * 10) / 10, label })
}

/** Collapsed by default: the block's goals (one per line — the finish
 *  dialog reads them back at settlement) and free-form notes. */
function GoalsNotesSection({
  goals, notes, onGoals, onNotes, startOpen,
}: {
  goals: string
  notes: string
  onGoals: (v: string) => void
  onNotes: (v: string) => void
  startOpen?: boolean
}) {
  const [open, setOpen] = useState(!!startOpen)
  useEffect(() => { if (startOpen) setOpen(true) }, [startOpen])
  return (
    <div className="flex flex-col gap-6">
      <Button
        variant="text"
        size="bare"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="self-start uppercase tracking-wide"
      >
        {open ? '▾' : '▸'} {t('goals & notes')} <span className="normal-case tracking-normal">{t('— optional')}</span>
      </Button>
      {open && (
        <div className="flex flex-col gap-8">
          <div className="flex flex-col gap-2">
            <span className="text-11 text-tertiary">{t('Goals: what must be done when the block ends, one per line. They are shown again when you finish it.')}</span>
            <textarea
              value={goals}
              onChange={(e) => onGoals(e.target.value)}
              rows={3}
              placeholder={t('auth works end to end\nno known login bugs')}
              aria-label={t('Block goals')}
              className="bg-elevated text-primary border border-border-default rounded-input px-10 py-6 text-12 leading-relaxed font-mono"
            />
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-11 text-tertiary">{t('Notes: context and links.')}</span>
            <textarea
              value={notes}
              onChange={(e) => onNotes(e.target.value)}
              rows={2}
              aria-label={t('Block notes')}
              className="bg-elevated text-primary border border-border-default rounded-input px-10 py-6 text-12 leading-relaxed"
            />
          </div>
        </div>
      )}
    </div>
  )
}

export function StartBlockDialog({
  projectCode, active, backlog, onClose, onStarted,
}: {
  projectCode: string
  /** The running blocks — they fill the slots strip. */
  active: ActiveSprint[]
  /** Open tasks without a sprint — candidates to take aboard. */
  backlog: BacklogTask[]
  onClose: () => void
  onStarted: () => void
}) {
  const [name, setName] = useState('')
  const [bet, setBet] = useState(7)
  const [betCustom, setBetCustom] = useState('')
  const [budget, setBudget] = useState<number | null>(null)
  const [budgetCustom, setBudgetCustom] = useState('')
  const [aboard, setAboard] = useState<Set<string>>(new Set())
  const [goals, setGoals] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  const betDays = betCustom !== '' ? Number(betCustom) || 0 : bet
  const budgetH = budgetCustom !== '' ? Number(budgetCustom) || 0 : (budget ?? 0)
  const slots = [...active.map((s) => s.name), name.trim() || null, null, null].slice(0, 3)
  const full = active.length >= 3
  const intensity = intensityOf(budgetH, betDays)

  const summary = useMemo(() => {
    if (!name.trim()) return null
    const parts = [`${betDays} day${betDays === 1 ? '' : 's'}`]
    if (budgetH) parts.push(`${budgetH} hours of yours`)
    if (aboard.size) parts.push(`${aboard.size} task${aboard.size === 1 ? '' : 's'}`)
    return `${name.trim()} — ${parts.join(', ')}.`
  }, [name, betDays, budgetH, aboard])

  const start = async () => {
    if (!name.trim() || betDays <= 0 || saving || full) return
    setSaving(true)
    const { dateStr } = nowStamp()
    let res: { metadata?: { id?: string } }
    try {
      res = await postJson('/api/sprints', {
        created_date: dateStr, started_date: dateStr, name: name.trim(),
        projects: projectCode, status: 'active', agent_id: OPERATOR_ACTOR,
        bet_days: betDays, time_budget_h: budgetH || '',
        l2: `Block of work: ${name.trim()}. Planned: ${betDays} days${budgetH ? `, ${budgetH} human hours (${intensity})` : ''}. Ends around ${endDateOf(betDays)}.`,
        l3: goals.split('\n').map((g) => g.trim()).filter(Boolean),
        l4: notes.trim(),
      })
    } catch (e) { fail(e); setSaving(false); return }
    const sid = res?.metadata?.id
    if (sid && aboard.size) {
      const moved = await Promise.all([...aboard].map((tid) =>
        postJson(`/api/tasks/${encodeURIComponent(tid)}/update`, { sprint_id: sid, actor: OPERATOR_ACTOR }).then(() => true, () => false),
      ))
      // The block stands; the tasks that did not move stay in the backlog.
      if (moved.some((ok) => !ok)) toast.error(t('The block is started. Some tasks could not be moved onto it.'))
    }
    onStarted()
  }

  return (
    <Modal label={t('Start a block of work')} onClose={onClose} width="w-[560px]" padding="p-20">
      <div className="flex flex-col gap-14">
        <div>
          <h2 className="text-20 font-semibold text-primary">{t('Start a block of work')}</h2>
          <p className="text-12 text-tertiary mt-2">{t('This creates a sprint, a named block of work with a length in days and an optional budget of your hours. Give it a name, pick the days, tick any backlog tasks it should carry, and confirm.')}</p>
        </div>

        {/* The three slots */}
        <div className="flex items-center gap-6" aria-label={t('Sprint slots')}>
          {slots.map((s, i) => {
            const isThis = !full && i === active.length
            return (
              <div
                key={i}
                className={`flex-1 h-32 rounded-input border flex items-center justify-center px-8 text-11 font-mono truncate ${
                  isThis ? 'border-brand text-brand border-dashed' : s ? 'border-border-default bg-elevated text-secondary' : 'border-border-subtle text-tertiary border-dashed'
                }`}
              >
                {isThis ? (name.trim() || t('this block')) : s || t('free slot')}
              </div>
            )
          })}
        </div>
        {full && (
          <p className="text-12 text-status-red font-mono -mt-6">{t('Three blocks are running. Finish one, with its retro, to start another.')}</p>
        )}

        {/* Name */}
        <div className="flex flex-col gap-6">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('Name of the block')}
            aria-label={t('Block name')}
            className="bg-elevated text-primary border border-border-default rounded-input px-12 py-8 text-14 font-medium outline-none focus:border-brand"
          />
          <div className="flex items-center gap-4 flex-wrap">
            {NAME_HINTS.map((h) => (
              <button key={h} type="button" onClick={() => setName(h)} className="h-20 px-8 rounded-pill border border-border-subtle text-10 font-mono text-tertiary hover:text-primary hover:border-border-strong">
                {h}
              </button>
            ))}
          </div>
        </div>

        <ChipRow label={t('length')} hint={t('planned days')} chips={DAY_CHIPS} unit="d"
          on={(d) => betCustom === '' && bet === d} onPick={(d) => { setBet(d); setBetCustom('') }}
          custom={betCustom} onCustom={(v) => setBetCustom(v.replace(/\D/g, ''))} customLabel={t('Custom length, days')}
          after={<span className="text-12 text-secondary ml-4">{t('→ ends around')} <strong className="text-primary">{endDateOf(betDays)}</strong></span>} />

        <ChipRow label={t('your hours')} hint={t('hour budget')} chips={HOUR_CHIPS} unit="h"
          on={(h) => budgetCustom === '' && budget === h}
          onPick={(h) => { setBudget(h === budget && budgetCustom === '' ? null : h); setBudgetCustom('') }}
          custom={budgetCustom} onCustom={(v) => setBudgetCustom(v.replace(/[^\d.]/g, ''))} customLabel={t('Custom budget, hours')}
          after={intensity
            ? <span className="text-12 text-secondary ml-4">{intensity}</span>
            : <span className="text-12 text-tertiary ml-4">{t('Optional. The timer compares against it.')}</span>} />

        {/* Tasks aboard */}
        {backlog.length > 0 && (
          <div className="flex flex-col gap-4">
            <div className="flex items-baseline gap-8">
              <span className={LABEL}>{t('tasks from the backlog')}</span>
              <span className="text-11 text-tertiary">{aboard.size ? t('{n} of {total}', { n: aboard.size, total: backlog.length }) : t('{n} in the backlog. Optional, tasks can be added later.', { n: backlog.length })}</span>
            </div>
            <div className="max-h-[140px] overflow-y-auto flex flex-col gap-2 rounded-input border border-border-subtle bg-elevated/50 p-8">
              {backlog.map((t) => (
                <label key={t.id} className="flex items-center gap-8 text-12 cursor-pointer px-4 py-2 rounded-input hover:bg-hover">
                  <input
                    type="checkbox"
                    checked={aboard.has(t.id)}
                    onChange={() => setAboard((cur) => {
                      const next = new Set(cur)
                      if (next.has(t.id)) next.delete(t.id); else next.add(t.id)
                      return next
                    })}
                    className="accent-[var(--brand)]"
                  />
                  <span className="text-secondary truncate">{t.title}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        <GoalsNotesSection goals={goals} notes={notes} onGoals={setGoals} onNotes={setNotes} />

        {/* Footer: the bet in one sentence */}
        <div className="flex items-center gap-12 border-t border-border-subtle pt-12">
          <span className="text-12 text-secondary flex-1 min-w-0 truncate italic">
            {summary ?? t('Name the block to see the summary.')}
          </span>
          <button type="button" onClick={onClose} className="text-12 font-mono text-tertiary hover:text-primary shrink-0">{t('cancel')}</button>
          <Button
            variant="primary"
            size="md"
            onClick={() => void start()}
            disabled={!name.trim() || betDays <= 0 || saving || full}
            className="shrink-0"
          >
            {saving ? 'Starting…' : t('Start the block')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/**
 * EditBlockDialog — the same language as starting one: rename, move the
 * bet, resize the budget. Delete lives here too, quiet and red — for
 * blocks that should not exist; real endings go through finish + retro.
 */
export function EditBlockDialog({
  sprint, onClose, onSaved,
}: {
  sprint: { id: string; name: string; bet_days?: number | string | null; budget_h?: number | string | null; tasks_total: number }
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(sprint.name)
  const [bet, setBet] = useState<number | null>(DAY_CHIPS.includes(Number(sprint.bet_days)) ? Number(sprint.bet_days) : null)
  const [betCustom, setBetCustom] = useState(DAY_CHIPS.includes(Number(sprint.bet_days)) ? '' : String(sprint.bet_days ?? ''))
  const [budget, setBudget] = useState<number | null>(HOUR_CHIPS.includes(Number(sprint.budget_h)) ? Number(sprint.budget_h) : null)
  const [budgetCustom, setBudgetCustom] = useState(HOUR_CHIPS.includes(Number(sprint.budget_h)) || !sprint.budget_h ? '' : String(sprint.budget_h))
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)
  const [goals, setGoals] = useState('')
  const [notes, setNotes] = useState('')
  const [l2, setL2] = useState('')
  const [hadContent, setHadContent] = useState(false)
  // The fields are filled once from the block's entry; a later read (the
  // stamp moved) must not undo what is being typed.
  const detail = useSprintDetail(sprint.id)
  const [seededFor, setSeededFor] = useState('')
  useEffect(() => {
    if (!detail.data || seededFor === sprint.id) return
    const held = entryText(detail.data)
    const g = held.list.join('\n')
    setGoals(g)
    setNotes(held.long)
    setL2(held.text)
    setHadContent(!!(g || held.long))
    setSeededFor(sprint.id)
  }, [detail.data, sprint.id, seededFor])
  // A save rewrites the whole entry: before the entry is read it would
  // write the goals and notes back empty. Read is not enough — the fields
  // are filled by the effect above, one render after the read lands, and a
  // Save enabled on the read alone posts that render's empty fields. So Save
  // waits for the fields, which arrive in the same render as ``seededFor``.
  const unread = seededFor !== sprint.id

  const betDays = betCustom !== '' ? Number(betCustom) || 0 : (bet ?? 0)
  const budgetH = budgetCustom !== '' ? Number(budgetCustom) || 0 : (budget ?? 0)
  const intensity = intensityOf(budgetH, betDays)

  const save = async () => {
    if (!name.trim() || betDays <= 0 || busy || unread) return
    setBusy(true)
    try {
      await postJson(`/api/sprints/${encodeURIComponent(sprint.id)}/update`, {
        name: name.trim(), bet_days: betDays, time_budget_h: budgetH || '',
        // The update rewrites the whole detail doc — send l2 back with it.
        l2, l3: goals.split('\n').map((g) => g.trim()).filter(Boolean), l4: notes.trim(),
      })
    } catch (e) { fail(e); setBusy(false); return }
    onSaved()
  }
  const del = async () => {
    if (busy) return
    setBusy(true)
    try {
      await postJson(`/api/sprints/${encodeURIComponent(sprint.id)}/delete`, {})
    } catch (e) { fail(e); setBusy(false); return }
    onSaved()
  }

  return (
    <Modal label={`Edit ${sprint.name}`} onClose={onClose} width="w-[520px]" padding="p-20">
      <div className="flex flex-col gap-14">
        <h3 className="text-20 font-semibold text-primary">{t('Edit block')}</h3>

        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          aria-label={t('Block name')}
          className="bg-elevated text-primary border border-border-default rounded-input px-12 py-8 text-14 font-medium outline-none focus:border-brand"
        />

        <ChipRow label={t('length')} chips={DAY_CHIPS} unit="d"
          on={(d) => betCustom === '' && bet === d} onPick={(d) => { setBet(d); setBetCustom('') }}
          custom={betCustom} onCustom={(v) => setBetCustom(v.replace(/\D/g, ''))} customLabel={t('Custom length, days')} />

        <ChipRow label={t('your hours')} chips={HOUR_CHIPS} unit="h"
          on={(h) => budgetCustom === '' && budget === h}
          onPick={(h) => { setBudget(h === budget && budgetCustom === '' ? null : h); setBudgetCustom('') }}
          custom={budgetCustom} onCustom={(v) => setBudgetCustom(v.replace(/[^\d.]/g, ''))} customLabel={t('Custom budget, hours')}
          after={intensity && <span className="text-12 text-secondary ml-4">{intensity}</span>} />

        <GoalsNotesSection goals={goals} notes={notes} onGoals={setGoals} onNotes={setNotes} startOpen={hadContent} />
        {detail.isError && (
          <p className="text-11 text-status-red">{t('The block\'s goals and notes could not be read. Save is off so they are not erased.')}</p>
        )}

        <div className="flex items-center gap-12 border-t border-border-subtle pt-12">
          {confirmDelete ? (
            <Confirm
              text={t('Delete this block permanently.') + ' ' + (sprint.tasks_total > 0 ? t('{tasks} return to the backlog.', { tasks: tn(sprint.tasks_total, '{n} task', '{n} tasks') }) : t('It has no tasks.'))}
              action={t('Delete')}
              busy={busy}
              onYes={() => void del()}
              onNo={() => setConfirmDelete(false)}
            />
          ) : (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="text-11 font-mono text-status-red/70 hover:text-status-red"
              title={t('For blocks made by mistake. To end a block, finish it and write the retro.')}
            >
              {t('delete')}
            </button>
          )}
          <button type="button" onClick={onClose} className="ml-auto text-12 font-mono text-tertiary hover:text-primary">{t('cancel')}</button>
          <Button
            variant="primary"
            size="md"
            onClick={() => void save()}
            disabled={!name.trim() || betDays <= 0 || busy || unread}
          >
            {t('Save')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/** A label, a row of chips (days, hours) and a field for any other number. */
function ChipRow({ label, hint, chips, unit, on, onPick, custom, onCustom, customLabel, after }: {
  label: string
  hint?: string
  chips: readonly number[]
  unit: string
  on: (n: number) => boolean
  onPick: (n: number) => void
  custom: string
  onCustom: (v: string) => void
  customLabel: string
  after?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline gap-8">
        <span className={LABEL}>{label}</span>
        {hint && <span className="text-11 text-tertiary">{hint}</span>}
      </div>
      <div className="flex items-center gap-4 flex-wrap">
        {chips.map((n) => (
          <button key={n} type="button" onClick={() => onPick(n)} aria-pressed={on(n)}
            className={`h-32 px-12 rounded-pill border text-12 font-mono ${on(n) ? 'border-brand bg-brand text-on-brand' : 'border-border-default text-secondary hover:border-brand'}`}>
            {n}{unit}
          </button>
        ))}
        <input value={custom} onChange={(e) => onCustom(e.target.value)} placeholder="…" aria-label={customLabel}
          className={`h-32 w-48 rounded-pill border text-12 font-mono text-center outline-none bg-transparent ${custom !== '' ? 'border-brand text-primary' : 'border-border-default text-tertiary'}`} />
        {after}
      </div>
    </div>
  )
}
