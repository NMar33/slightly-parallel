/**
 * A task's notes in its window (tk_3e544086): the notes written for the task
 * and the ones that name it, in the compact form the design round drew
 * (render/TaskNotes) — what waits on an answer first, the open steps and
 * choices working in place, each note readable here or on the Notes page.
 * Nothing is drawn for a task with no notes.
 */

import { useMemo } from 'react'

import { TaskNotes } from '../render/TaskNotes'
import { toNote, useNotesFeed } from './data'
import { ServerNoteEnv } from './ServerEnv'

export function TaskNotesSection({ taskId }: { taskId: string }) {
  const feed = useNotesFeed({ task: taskId })
  const notes = useMemo(() => (feed.data?.notes ?? []).map((w) => toNote(w)), [feed.data])
  if (!notes.length) return null
  return (
    <ServerNoteEnv feed={feed.data}>
      <TaskNotes key={`${taskId}:${notes.length}`} taskId={taskId} notes={notes} />
    </ServerNoteEnv>
  )
}
