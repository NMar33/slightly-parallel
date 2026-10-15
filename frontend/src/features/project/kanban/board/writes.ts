/**
 * The board's writes that touch many cards at once, each optimistic: the
 * cards change in the cache at once, the server is told, and a refetch
 * (`bump`) brings back the truth — which is also the rollback when a write
 * was refused. Built each render over the board's current setters, as
 * boardDrops is.
 */

import { toast } from '../../../../components/primitives'
import { postJson } from '../../../../lib/getJson'
import { isoDay, pad2 } from '../../../../utils/dateUtils'
import { OPERATOR_ACTOR } from '../../types'
import type { TaskRow } from '../model'
import { t } from '../../../../i18n/scope/project'

export type Patch = { id: string; patch: Record<string, string> }

/** This moment as the server stamps an archive: local time, to the second. */
export function localStamp(d: Date = new Date()): string {
  return `${isoDay(d)}T${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

export function boardWrites({ setTasks, bump }: {
  setTasks: (u: TaskRow[] | ((cur: TaskRow[]) => TaskRow[])) => void
  /** Ask the board's queries again. */
  bump: () => void
}) {
  /** Write a field across many tasks at once — used by the day's actions,
   *  which are undoable rather than confirmed: the board's own philosophy. */
  const patchMany = async (rows: Patch[]) => {
    setTasks((cur) => cur.map((t) => {
      const hit = rows.find((r) => r.id === t.id)
      return hit ? { ...t, ...hit.patch } : t
    }))
    let failed = 0
    for (const r of rows) {
      const ok = await postJson(`/api/tasks/${encodeURIComponent(r.id)}/update`, { ...r.patch, actor: OPERATOR_ACTOR })
        .then(() => true, () => false)
      if (!ok) failed += 1
    }
    if (failed) toast.error(t('{failed} of {total} didn\'t save', { failed, total: rows.length }))
    bump()
  }

  const setArchived = async (ids: string[], on: boolean) => {
    // Optimistic: the card leaves (or returns) at once; the server confirms.
    const stamp = localStamp()
    setTasks((cur) => cur.map((t) => (ids.includes(t.id) ? { ...t, archived_at: on ? stamp : '' } : t)))
    const results = await Promise.all(ids.map((id) =>
      postJson(`/api/tasks/${encodeURIComponent(id)}/${on ? 'archive' : 'restore'}`, { actor: OPERATOR_ACTOR })
        .then(() => true, () => false),
    ))
    if (results.some((ok) => !ok)) toast.error(on ? t('Couldn\'t archive every task') : t('Couldn\'t restore every task'))
    bump()
  }

  return { patchMany, setArchived }
}
