/**
 * Opening a task from a calendar or milestone page: the row is read fresh
 * (the calendar payload carries a trimmed task, the window needs the whole
 * one) and handed to the page's task window. A failed read is one toast.
 */
import { getJson } from '../../lib/getJson'
import { toast } from '../../components/primitives'
import type { TaskRow } from '../project/kanban/model'

import { t } from '../../i18n/scope/views'
async function fetchTaskRow(id: string): Promise<TaskRow> {
  const d = await getJson<{ metadata: TaskRow; description?: string }>(`/api/tasks/${encodeURIComponent(id)}`)
  return { ...d.metadata, description: d.description ?? '' }
}

export async function openTaskRow(id: string, show: (row: TaskRow) => void): Promise<void> {
  try {
    show(await fetchTaskRow(id))
  } catch {
    toast.error(t('Couldn\'t open the task'))
  }
}
