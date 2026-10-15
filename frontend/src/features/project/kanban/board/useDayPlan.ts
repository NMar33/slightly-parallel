/**
 * Today: the plan for the day, marked per task with today's date — the
 * cards planned, the toggle on a card, the day's two actions (all done,
 * dismiss), and the carry-over of cards planned for an earlier day.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from '../../../../components/primitives'
import { fail, postJson } from '../../../../lib/getJson'
import { OPERATOR_ACTOR } from '../../types'
import { carrySeenToday, leftovers, markCarrySeen } from '../carry'
import { isToday, normalizeStatus, todayISO } from '../model'
import type { TaskRow } from '../model'
import type { Patch } from './writes'
import { t, tn } from '../../../../i18n/scope/project'

export function useDayPlan({ tasks, setTasks, patchMany, bump }: {
  tasks: TaskRow[]
  setTasks: (u: TaskRow[] | ((cur: TaskRow[]) => TaskRow[])) => void
  patchMany: (rows: Patch[]) => Promise<void>
  bump: () => void
}) {
  const today = todayISO()
  const toggleToday = async (task: TaskRow) => {
    const on = isToday(task, today)
    const next = on ? '' : today
    setTasks((cur) => cur.map((t) => (t.id === task.id ? { ...t, today_on: next } : t)))
    await postJson(`/api/tasks/${encodeURIComponent(task.id)}/update`, { today_on: next, actor: OPERATOR_ACTOR }).catch(fail)
    bump()
  }
  // Memoized: byLaneCol folds these into its per-column map, and a fresh
  // array every render would rebuild that map every render.
  const todayTasks = useMemo(() => tasks.filter((t) => isToday(t, today) && !t.archived_at), [tasks, today])
  const unfinished = todayTasks.filter((t) => !['done', 'done-archived'].includes(normalizeStatus(t.status)))

  // A day's worth of writes takes a moment; the buttons stay out of the way
  // until it lands, so a second click cannot interleave with the first.
  const [dayBusy, setDayBusy] = useState(false)
  /** The day landed: every planned card goes to Done. */
  const todayAllDone = async () => {
    const moving = unfinished
    if (moving.length === 0 || dayBusy) return
    setDayBusy(true)
    const before = moving.map((t) => ({ id: t.id, patch: { status: String(t.status || 'unclassified') } }))
    await patchMany(moving.map((t) => ({ id: t.id, patch: { status: 'done' } })))
    setDayBusy(false)
    toast.success(tn(moving.length, '{n} task moved to Done', '{n} tasks moved to Done'), {
      action: { label: t('Undo'), onClick: () => void patchMany(before) },
    })
  }
  /** The plan is over: clear the lane, leave every task where it lives. */
  const todayDismiss = async () => {
    const clearing = todayTasks
    if (clearing.length === 0 || dayBusy) return
    setDayBusy(true)
    const before = clearing.map((t) => ({ id: t.id, patch: { today_on: today } }))
    await patchMany(clearing.map((t) => ({ id: t.id, patch: { today_on: '' } })))
    setDayBusy(false)
    toast.success(t('Removed {tasks} from today\'s plan.', { tasks: tn(clearing.length, '{n} task', '{n} tasks') }), {
      action: { label: t('Undo'), onClick: () => void patchMany(before) },
    })
  }

  // Carry-over: cards planned for an earlier day and still open. At midnight
  // the Today lane empties on its own, which used to be the whole story —
  // the cards went quiet in their columns and nobody was told. Now the
  // board asks, once a day, and the strip below the header asks again on
  // demand. Nothing moves until the operator says so.
  const leftover = useMemo(() => leftovers(tasks, today), [tasks, today])
  const [carryOpen, setCarryOpen] = useState(false)
  // Asked once per day: a board left open across midnight asks again.
  const carryAskedRef = useRef('')
  useEffect(() => {
    if (carryAskedRef.current === today || leftover.length === 0 || carrySeenToday(today)) return
    carryAskedRef.current = today
    setCarryOpen(true)
  }, [leftover.length, today])
  const closeCarry = () => { setCarryOpen(false); markCarrySeen(today) }
  const carryOver = async (carry: string[], letGo: string[]) => {
    const rows = leftover.filter((t) => carry.includes(t.id) || letGo.includes(t.id))
    if (rows.length === 0) { closeCarry(); return }
    const before = rows.map((t) => ({ id: t.id, patch: { today_on: t.today_on || '' } }))
    const writes = rows.map((t) => ({ id: t.id, patch: { today_on: carry.includes(t.id) ? today : '' } }))
    closeCarry()
    await patchMany(writes)
    const carried = carry.length ? `${carry.length} planned for today` : ''
    const gone = letGo.length ? `${letGo.length} dropped` : ''
    toast.success([carried, gone].filter(Boolean).join(', '), {
      action: { label: t('Undo'), onClick: () => void patchMany(before) },
    })
  }

  return {
    today, toggleToday, todayTasks, unfinished, dayBusy, todayAllDone, todayDismiss,
    leftover, carryOpen, setCarryOpen, closeCarry, carryOver,
  }
}

export type DayPlan = ReturnType<typeof useDayPlan>
