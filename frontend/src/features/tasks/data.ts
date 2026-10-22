/**
 * The tasks and sprints of a project, read once and typed once.
 *
 * Seven places used to ask `/api/tasks` for the same list, each under a
 * key of its own, each with its own limit (300, 500, 2000, 5000) and most
 * of them as `any` — so a project past the smallest limit showed different
 * tasks in different panels, and nothing was shared. Here: one answer
 * shape, one limit, one cache entry a project (and one for "every task").
 * The board keeps its own queries (kanban/boardData.ts: several projects
 * merged, bodies on demand) and reads with the same limit.
 */

import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'
import type { TaskLink, TaskRow } from '../project/kanban/model'
import type { Turn } from './turns'

/** What `/api/tasks` answers with. */
interface TasksAnswer { tasks?: TaskRow[] }
/** What `/api/tasks/{id}` answers with: the row, and the rounds of its text. */
export interface TaskAnswer { metadata?: TaskRow; turns?: Turn[] }
/** What `/api/tasks/links` and `/api/tasks/{id}/links` answer with. */
export interface TaskLinksAnswer { links?: TaskLink[] }

/** A sprint as `/api/sprints/board` gives it: the row plus its derived numbers. */
export interface SprintBoardRow {
  id: string
  name: string
  started_date: string
  bet_days?: number | string | null
  days_left?: number | null
  budget_h?: number | string | null
  tasks_total: number
  tasks_done: number
  human_min: number
  agent_min: number
}
export interface SprintBoardAnswer { sprints?: SprintBoardRow[]; /** Open tasks on no sprint. */ no_sprint?: number }

/** A sprint as `/api/sprints` lists it. */
interface SprintListRow { id: string; name: string; projects?: string; status?: string }
export interface SprintsAnswer { sprints?: SprintListRow[] }

/** A project's tasks in one read. The server allows up to 5000. */
export const PROJECT_TASKS_LIMIT = 2000
/** Every project's tasks in one read: the server's ceiling. */
const ALL_TASKS_LIMIT = 5000

const rows = (d: TasksAnswer | null | undefined): TaskRow[] => (Array.isArray(d?.tasks) ? d.tasks : [])

/** Under "tasks": the freshness stamp asks again when a task is written. */
export const projectTasksKey = (project: string) => ['tasks', 'project', project] as const
const ALL_TASKS_KEY = ['tasks', 'all'] as const

const fetchProjectTasks = (project: string, signal?: AbortSignal): Promise<TaskRow[]> =>
  getJson<TasksAnswer>(`/api/tasks?project=${encodeURIComponent(project)}&limit=${PROJECT_TASKS_LIMIT}`, signal).then(rows)

/** One task as it is now (the editor needs the row, not a list's copy of it). */
export const fetchTask = (id: string, signal?: AbortSignal): Promise<TaskRow | null> =>
  getJson<TaskAnswer>(`/api/tasks/${encodeURIComponent(id)}`, signal).then((d) => (d?.metadata ? { ...d.metadata } : null))

/** Every task of one project, archived ones included. `enabled` holds the read until it is wanted. */
export function useProjectTasks(project: string, enabled = true) {
  return useQuery({
    queryKey: projectTasksKey(project),
    queryFn: ({ signal }) => fetchProjectTasks(project, signal),
    enabled: enabled && !!project,
  })
}

/** Every task of every project — for the pages that name a task by its id. */
export function useAllTasks() {
  return useQuery({
    queryKey: ALL_TASKS_KEY,
    queryFn: ({ signal }) => getJson<TasksAnswer>(`/api/tasks?limit=${ALL_TASKS_LIMIT}`, signal).then(rows),
    staleTime: 60_000,
  })
}

export const sprintBoardKey = (project: string) => ['sprints', 'board', project] as const

/** The project's running sprints with their numbers. */
export function useSprintBoard(project: string) {
  return useQuery({
    queryKey: sprintBoardKey(project),
    queryFn: ({ signal }) =>
      getJson<SprintBoardAnswer>(`/api/sprints/board?project=${encodeURIComponent(project)}`, signal)
        .then((d) => (Array.isArray(d?.sprints) ? d.sprints : [])),
    enabled: !!project,
  })
}
