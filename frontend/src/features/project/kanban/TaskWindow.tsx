/*
 * The task window, loaded when it is first opened.
 *
 * The window is the largest thing a page can show — the editor, the
 * evidence panel, the story, the agent's dossier — and nine pages open it
 * from a click. Imported directly, each of them carried all of it from
 * its first draw. Here it is its own chunk: a page pays for the window
 * when somebody opens one. Nothing is drawn while it arrives.
 */

import { Suspense, lazy, type ComponentProps } from 'react'

const Window = lazy(() => import('./TaskEditor').then((m) => ({ default: m.TaskAddModal })))

/**
 * Keyed by the task: the editor reads a task into its fields once, when it
 * mounts. A page that swaps the task in an open window (a linked task
 * opened from it) kept the first task's title and text under the second
 * one's id, and Save wrote them there.
 */
export function TaskAddModal(props: ComponentProps<typeof import('./TaskEditor').TaskAddModal>) {
  return <Suspense fallback={null}><Window key={props.existingTask?.id ?? 'new'} {...props} /></Suspense>
}
