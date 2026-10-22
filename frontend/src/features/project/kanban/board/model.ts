/**
 * Board-only pure pieces: the order writer, the shared empty cell, and the
 * archive column's key. The feature's wider model is ../model.ts.
 */

import { OPERATOR_ACTOR } from '../../types'
import type { TaskRow } from '../model'

/**
 * Write new positions, one request each, and say how many did not land.
 * The board keeps its optimistic order only while every write succeeded.
 */
export async function writeOrder(
  writes: Array<{ id: string; position: number }>,
  post: (path: string, body: unknown) => Promise<unknown>,
): Promise<number> {
  const results = await Promise.allSettled(
    writes.map((w) => post(`/api/tasks/${encodeURIComponent(w.id)}/update`, { position: w.position, actor: OPERATOR_ACTOR })),
  )
  return results.filter((r) => r.status === 'rejected').length
}

/** One empty list for every empty cell — a fresh [] per cell per render
 *  would hand the memoized cards a new prop each time. */
export const EMPTY_ROWS: TaskRow[] = []

/** The archive column's key — a drop target, never a status. */
export const ARCHIVE = '__archive__'
