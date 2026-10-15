/*
 * The task window's milestone link: read the projects' milestones, find
 * the one holding this task, and write a changed pick after the task
 * lands. Moved out of TaskEditor.tsx — the window calls the hook where its
 * state used to sit, so the hook order is unchanged.
 */

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from '../../../../components/primitives'
import { OPERATOR_ACTOR } from '../../types'
import { getJson, postJson } from '../../../../lib/getJson'
import type { TaskRow } from '../model'
import type { MilestoneOption } from './types'
import { t } from '../../../../i18n/scope/project'

const NONE: MilestoneOption[] = []

// The milestone the task feeds. Links live in their own ledger, so the
// window reads the project's milestones and finds the one holding this
// task; a change is written after the task itself lands. The read shares
// its key with the milestone pages (`useMilestones`), so it follows the
// freshness stamp and is one request for both.
export function useMilestone(milestoneProject: string, existingTask: TaskRow | null | undefined) {
  const [milestoneId, setMilestoneId] = useState('')
  const [milestoneWas, setMilestoneWas] = useState('')
  const q = useQuery({
    queryKey: ['milestones', milestoneProject],
    queryFn: ({ signal }) => getJson<{ milestones: MilestoneOption[] }>(
      `/api/milestones?project=${encodeURIComponent(milestoneProject)}`, signal),
    enabled: !!milestoneProject,
    staleTime: 10_000,
  })
  // A refused or failed read leaves the picker empty; the task still saves.
  const milestones = q.data?.milestones ?? NONE
  const taskId = existingTask?.id
  // The pick is seeded once per project and task: a later read (the stamp
  // moved) must not undo what the operator picked meanwhile.
  const seeded = useRef('')
  useEffect(() => {
    if (!q.data) return
    const list = q.data.milestones ?? []
    const key = `${milestoneProject}|${taskId ?? ''}`
    const first = seeded.current !== key
    seeded.current = key
    if (taskId) {
      // The task's own link; a pick made while the list was loading is not overwritten.
      const mine = list.find((m) => m.tasks.includes(taskId))
      if (first) setMilestoneId((cur) => cur || mine?.id || '')
      setMilestoneWas(mine?.id ?? '')
    } else {
      // A new task under another project: a milestone of the old one cannot hold it.
      setMilestoneId((cur) => (list.some((m) => m.id === cur) ? cur : ''))
    }
  }, [q.data, taskId, milestoneProject])
  /** Write the link for the tasks that just landed. New tasks link whenever
   *  a milestone is picked (a chain of them all join it); an existing task
   *  only when the pick changed. A failed write is said, not swallowed. */
  const syncMilestone = async (taskIds: string[]) => {
    const ids = taskIds.filter(Boolean)
    if (ids.length === 0) return
    if (existingTask && milestoneId === milestoneWas) return
    if (!existingTask && !milestoneId) return
    const target = milestoneId || milestoneWas
    const body = milestoneId ? { add: ids, actor: OPERATOR_ACTOR } : { remove: ids, actor: OPERATOR_ACTOR }
    const ok = await postJson(`/api/milestones/${encodeURIComponent(target)}/tasks`, body).then(() => true, () => false)
    if (!ok) {
      toast.error(t('The task is saved. The milestone link failed. Open the task and pick the milestone again.'))
      return
    }
    if (existingTask) setMilestoneWas(milestoneId)
  }
  return { milestones, milestoneId, setMilestoneId, syncMilestone }
}
