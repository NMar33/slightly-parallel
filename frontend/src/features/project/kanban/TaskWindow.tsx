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

export function TaskAddModal(props: ComponentProps<typeof import('./TaskEditor').TaskAddModal>) {
  return <Suspense fallback={null}><Window {...props} /></Suspense>
}
