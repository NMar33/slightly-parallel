import { useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { Sun, X } from 'lucide-react'

import { Button } from '../../../components/primitives/Button'
import { IconButton } from '../../../components/primitives/IconButton'
import { Modal } from '../../../components/Modal'
import { dayWord, fromWhen } from './carry'
import { normalizeStatus, type TaskRow } from './model'
import { t, tn } from '../../../i18n/scope/project'

/**
 * The carry-over window — the morning question.
 *
 * Cards planned for an earlier day and still open, grouped by the day they
 * were planned for, one tick each. Ticked cards join today, unticked ones
 * leave the plan. The window says that on its button rather than in a
 * footnote: the copy states the title, the instruction and the action, and
 * nothing else. "Later" changes nothing; the strip on the board reopens it.
 */
export function CarryOverModal({ rows, today, onCarry, onClose }: {
  rows: TaskRow[]
  today: string
  /** Ticked ids join today; the other listed ids are let go. */
  onCarry: (carry: string[], letGo: string[]) => void
  onClose: () => void
}) {
  const [off, setOff] = useState<Set<string>>(() => new Set())
  const picked = rows.filter((r) => !off.has(r.id))
  const groups = useMemo(() => {
    const by = new Map<string, TaskRow[]>()
    for (const r of rows) {
      const k = String(r.today_on)
      by.set(k, [...(by.get(k) ?? []), r])
    }
    return Array.from(by.entries())
  }, [rows])
  const flip = (id: string) => setOff((cur) => {
    const next = new Set(cur)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  const all = (on: boolean) => setOff(on ? new Set() : new Set(rows.map((r) => r.id)))
  const n = rows.length

  return createPortal(
    <Modal tone="window" labelledBy="carry-modal-title" onClose={onClose} isolateKeys
      width="w-full" maxWidth={560} padding="p-14" className="flex flex-col gap-10">
        <div className="flex items-baseline gap-8 min-w-0">
          <span id="carry-modal-title" className="text-16 font-semibold text-primary inline-flex items-center gap-6">
            <Sun size={15} className="text-brand" aria-hidden /> {tn(n, '{n} task from {when}', '{n} tasks from {when}', { when: fromWhen(rows, today) })}
          </span>
          <IconButton label={t('Close')} onClick={onClose} className="ml-auto">
            <X size={14} aria-hidden />
          </IconButton>
        </div>

        <p className="text-12 text-secondary leading-snug">{t('Select the ones to plan for today.')}</p>

        <div className="flex flex-col gap-8">
          {groups.map(([day, list]) => (
            <div key={day} className="flex flex-col gap-2">
              <div className="text-10 uppercase tracking-wider text-tertiary font-medium px-4">{dayWord(day, today)}</div>
              {list.map((r) => {
                const on = !off.has(r.id)
                return (
                  <label key={r.id} className={`flex items-center gap-8 px-8 h-32 rounded-input cursor-pointer ${on ? 'bg-hover' : 'hover:bg-hover'}`}>
                    <input type="checkbox" checked={on} onChange={() => flip(r.id)} className="accent-[var(--brand)]" aria-label={r.title} />
                    <span className={`truncate text-13 ${on ? 'text-primary' : 'text-tertiary'}`}>{r.title}</span>
                    <span className="ml-auto text-10 font-mono text-tertiary shrink-0">{normalizeStatus(r.status)}</span>
                  </label>
                )
              })}
            </div>
          ))}
        </div>

        <div className="flex items-center gap-8">
          <Button variant="text" size="bare" onClick={() => all(true)}>{t('all')}</Button>
          <Button variant="text" size="bare" onClick={() => all(false)}>{t('none')}</Button>
        </div>

        <div className="flex items-center gap-8 flex-wrap pt-4 border-t border-border-subtle">
          <Button
            variant="primary"
            size="sm"
            onClick={() => onCarry(picked.map((r) => r.id), rows.filter((r) => off.has(r.id)).map((r) => r.id))}
            iconLeft={<Sun size={12} aria-hidden />}
          >
            {picked.length === n ? t('Plan {n} for today', { n }) : picked.length === 0 ? t('Clear all {n}', { n }) : t('Plan {plan}, clear {clear}', { plan: picked.length, clear: n - picked.length })}
          </Button>
          <Button size="sm" onClick={onClose} title={t('Ask again tomorrow')}>
            {t('Later')}
          </Button>
        </div>
    </Modal>,
    document.body,
  )
}
