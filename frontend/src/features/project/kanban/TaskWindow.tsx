/*
 * The task window, loaded when it is first opened.
 *
 * The window is the largest thing a page can show — the editor, the
 * evidence panel, the story, the agent's dossier — and nine pages open it
 * from a click. Imported directly, each of them carried all of it from
 * its first draw. Here it is its own chunk: a page pays for the window
 * when somebody opens one. Nothing is drawn while it arrives.
 */

import { Suspense, lazy, useState, type ComponentProps } from 'react'

import { openTaskRow } from '../../calendar/tasks'
import type { TaskRow } from './model'

const Window = lazy(() => import('./TaskEditor').then((m) => ({ default: m.TaskAddModal })))

/**
 * Keyed by the task: the editor reads a task into its fields once, when it
 * mounts. A page that swaps the task in an open window (a linked task
 * opened from it) kept the first task's title and text under the second
 * one's id, and Save wrote them there.
 */
export function TaskAddModal(props: ComponentProps<typeof import('./TaskEditor').TaskAddModal>) {
  // A linked task (or the one a duplicate title names) opens here, in the
  // same window, on every page: only the board passed its own opener, so
  // on the other ten pages the link did nothing.
  const [other, setOther] = useState<TaskRow | null>(null)
  const openOther = props.onOpenOther ?? ((id: string) => { void openTaskRow(id, setOther) })
  const task = other ?? props.existingTask
  return (
    <Suspense fallback={null}>
      <Window key={task?.id ?? 'new'} {...props} existingTask={task} onOpenOther={openOther} />
    </Suspense>
  )
}
