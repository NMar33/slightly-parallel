/**
 * Task turns — one task, several rounds of instruction.
 *
 * You write what you want, an agent does it, and the next thing belongs
 * to the same task: that next thing is a **turn**. The server owns the
 * format (`backend/backend/turns.py`: a `## Description` section, then
 * `## Turn N · date time` sections) and hands the rounds over as a list —
 * `GET /api/tasks/{id}` → `turns`, the board list → `turn_last` /
 * `turns_n`. This module only carries the list around and names a turn
 * the way it is copied: `tk_28b1b490.2` — turn 1 keeps the bare id, so a
 * single-turn copy reads exactly as before, and the chat-mention
 * harvester ties the suffix back to the round that asked for it.
 */

export type Turn = { n: number; date: string; time: string; text: string }

/** How turn `n` is written when it is copied: `tk_…` or `tk_….2`. */
export function turnRef(taskId: string, n: number): string {
  return n <= 1 ? taskId : `${taskId}.${n}`
}

/** The rounds with the newest one re-worded — an edit, not a new round. */
export function replaceLast(turns: Turn[], text: string): Turn[] {
  const body = (text ?? '').trim()
  if (turns.length === 0) return body ? [{ n: 1, date: '', time: '', text: body }] : []
  return turns.map((t, i) => (i === turns.length - 1 ? { ...t, text: body } : t))
}
