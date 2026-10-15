/**
 * Story notes — the value a task leaves behind, written while it is clear.
 *
 * Shared by the task window (the Story section) and the Storyboard below
 * the board; lives outside TasksKanban so neither imports the other for a
 * constant (which used to be a circular import).
 */

import { persistPref, removePref } from '../../../lib/uiPrefs'
import { t } from '../../../i18n/scope/project'

export type StoryNote = {
  id: string; task_id: string; type: string; template: string; body: string
  created_at: string; updated_at: string; actor: string
}
export const NOTE_TYPES = ['article', 'post', 'release', 'report', 'faq', 'prompt'] as const
export const NOTE_TONE: Record<string, string> = {
  article: 'text-brand', post: 'text-status-purple', release: 'text-status-green',
  report: 'text-secondary', faq: 'text-status-amber', prompt: 'text-tertiary',
}
export const NOTE_HINT: Record<string, string> = {
  article: t('a paragraph for an article (Medium, Habr)'),
  post: t('one line for a post (X, LinkedIn)'),
  release: t('what · why · how to use'),
  report: t('outcome · evidence · next, for a weekly report'),
  faq: t('the question people will ask, and the answer'),
  prompt: t('how to write about this: audience, tone, what to include (for agents)'),
}

/** Local drafts — a story note is slow to write and easy to lose to a
 *  closed popup; every keystroke is kept in localStorage until the note is
 *  saved or the draft is discarded on purpose. Exported for tests. */
export type NoteDraft = { type: string; template: string; body: string; at: string }
export const NOTE_DRAFT_KEY = (taskId: string) => `sp-note-draft:${taskId}`
export const NOTE_EDIT_KEY = (noteId: string) => `sp-note-edit:${noteId}`
export function readDraft<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch { return null }
}
export function writeDraft(key: string, value: unknown): void {
  persistPref(key, JSON.stringify(value))
}
export function clearDraft(key: string): void {
  // The server's copy too: writeDraft keeps one there, and a draft cleared
  // only here came back from it on the next load, after it was saved.
  removePref(key)
}
export const stamp = () => new Date().toTimeString().slice(0, 5)

/** Applying a template can never delete what was typed: an empty box takes
 *  the scaffold; a box that still equals the previous scaffold swaps it;
 *  anything else keeps the text and appends the scaffold below. */
export function applyTemplate(body: string, previousScaffold: string, scaffold: string): string {
  const cur = body.replace(/\s+$/, '')
  if (!cur.trim()) return scaffold
  if (previousScaffold && cur === previousScaffold.replace(/\s+$/, '')) return scaffold
  if (!scaffold) return body
  return `${cur}\n\n${scaffold}`
}

/** Story — the value of the task, written down while it is clear. Typed,
 *  templated, atomic; later arranged into documents on the Storyboard. */
