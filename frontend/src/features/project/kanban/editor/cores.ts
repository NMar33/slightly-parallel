/*
 * The task window's cores: the project's cores in view, the ones this task
 * belongs to, and the write after the task lands — the same order as the
 * milestone (./milestone.ts): the pick is kept in the window and written
 * once the task has its id.
 */

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from '../../../../components/primitives'
import { OPERATOR_ACTOR } from '../../types'
import { postJson } from '../../../../lib/getJson'
import { useCores, useTaskCores } from '../../../architecture/cores/data'
import type { TaskRow } from '../model'
import { t } from '../../../../i18n/scope/project'

export interface CoreOption { id: string; name: string; type: string }

const NONE: CoreOption[] = []

export function useTaskCoreField(project: string, existingTask: TaskRow | null | undefined, initial: string[] = []) {
  const qc = useQueryClient()
  const list = useCores(project)
  const options = list.data?.cores?.filter((c) => c.status === 'view').map((c) => ({ id: c.id, name: c.name, type: c.type })) ?? NONE
  const taskId = existingTask?.id ?? ''
  const mine = useTaskCores(taskId)
  const [cores, setPicked] = useState<string[]>(initial)
  const [was, setWas] = useState<string[]>([])
  // A pick made by hand, before or after the task's cores arrived: the read
  // that lands later fills only a field nobody touched.
  const touched = useRef(false)
  const setCores = (v: string[]) => { touched.current = true; setPicked(v) }
  const seeded = useRef('')
  useEffect(() => {
    if (!taskId || !mine.data || seeded.current === taskId) return
    seeded.current = taskId
    const ids = (mine.data.cores ?? []).map((c) => c.id)
    setWas(ids)
    if (!touched.current) setPicked(ids)
  }, [taskId, mine.data])

  /** Write the cores for the tasks that just landed: a new task when any is
   *  picked, an existing one only when the pick changed. */
  const syncCores = async (taskIds: string[]) => {
    const [first, ...steps] = taskIds.filter(Boolean)
    if (!first) return
    const same = cores.length === was.length && cores.every((c) => was.includes(c))
    // The task itself: a new one when any core is picked, an existing one
    // only when the pick changed. Steps made behind it are new: they take
    // the pick whenever there is one.
    const ids = [
      ...((existingTask ? touched.current && !same : cores.length > 0) ? [first] : []),
      ...(cores.length > 0 ? steps : []),
    ]
    if (ids.length === 0) return
    const results = await Promise.all(ids.map((id) =>
      postJson(`/api/tasks/${encodeURIComponent(id)}/cores`, { cores, actor: OPERATOR_ACTOR }).then(() => true, () => false)))
    void qc.invalidateQueries({ queryKey: ['cores'] })
    void qc.invalidateQueries({ queryKey: ['core'] })
    if (results.includes(false)) {
      toast.error(t('The task is saved. Its core was not. Open the task and pick the core again.'))
      return
    }
    if (existingTask) setWas(cores)
  }
  return { coreOptions: options, cores, setCores, syncCores }
}
