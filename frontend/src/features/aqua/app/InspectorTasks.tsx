import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, ListPlus } from 'lucide-react'

import { Markdown } from '../../../components/Markdown'
import { t } from '../../../i18n/scope/aqua'
import { fail, getJson, postJson } from '../../../lib/getJson'
import { useEvidenceAsk } from '../../project/kanban/board/evidenceAsk'
import { readRecord, readStrings } from '../../project/kanban/board/prefs'
import {
  laneOf, laneUpdate, normalizeStatus, orderLanes, readStoredView, sortTasks, taskText, VIEW_COLUMNS, type TaskRow,
} from '../../project/kanban/model'
import { OPERATOR_ACTOR } from '../../project/types'
import { projectTasksKey, useProjectTasks, type TaskAnswer } from '../../tasks/data'

interface Mention { task_id: string; at: string }
type TaskDetail = TaskAnswer & { description?: string }
type TaskPatch = Partial<Pick<TaskRow, 'status' | 'assignee' | 'lane'>>
type Sort = 'created' | 'mentioned'
type Scope = 'project' | 'chat'

const EMPTY_TASKS: TaskRow[] = []
const detailKey = (id: string) => ['tasks', 'inspector-detail', id]
const endpoint = (id: string) => `/api/tasks/${encodeURIComponent(id)}`
const columnLabel = (key: string) => VIEW_COLUMNS.workflow.find((column) => column.key === key)?.label ?? key
const laneLabel = (key: string) => key === 'unassigned' ? t('Unassigned') : key
const selectClass = 'aq-btn line w-full min-w-0 text-12'

export interface InspectorTasksProps {
  project: string
  agent: string
  onAppend: (text: string) => void | Promise<boolean>
}

export function InspectorTasks(props: InspectorTasksProps) {
  return props.project
    ? <ProjectTasks key={props.project} {...props} />
    : <p className="m-0 p-12 text-12 aq-ink3">{t('No project')}</p>
}

function ProjectTasks({ project, agent, onAppend }: InspectorTasksProps) {
  const queryClient = useQueryClient()
  const evidenceAsk = useEvidenceAsk()
  const [scope, setScope] = useState<Scope>('project')
  const [sort, setSort] = useState<Sort>('created')
  const [onlyDone, setOnlyDone] = useState(false)
  const [open, setOpen] = useState('')
  const chatScope = scope === 'chat' && !!agent
  const projectQuery = encodeURIComponent(project)
  const tasksQuery = useProjectTasks(project)
  const tasks = tasksQuery.data ?? EMPTY_TASKS
  const summaryQuery = useQuery({
    queryKey: ['tasks', 'inspector-mentions', project],
    queryFn: ({ signal }) => getJson<{ mentions?: Record<string, { last_at: string }> }>(
      `/api/tasks/mentions/summary?project=${projectQuery}`, signal),
    enabled: !chatScope && sort === 'mentioned',
  })
  const chatQuery = useQuery({
    queryKey: ['tasks', 'inspector-mentions-by-agent', project],
    queryFn: ({ signal }) => getJson<{ agents?: Record<string, Mention[]> }>(
      `/api/tasks/mentions/by-agent?project=${projectQuery}`, signal),
    enabled: chatScope,
  })
  const shown = useMemo(() => {
    const chatMentions = new Map<string, string>()
    if (chatScope) {
      for (const { task_id, at } of chatQuery.data?.agents?.[agent] ?? []) {
        if (at > (chatMentions.get(task_id) ?? '')) chatMentions.set(task_id, at)
      }
    }
    const lastMention = (id: string) => chatScope
      ? chatMentions.get(id) ?? ''
      : summaryQuery.data?.mentions?.[id]?.last_at ?? ''
    const newest = sortTasks(tasks.filter((task) => {
      const status = normalizeStatus(task.status)
      return !task.archived_at && status !== 'done-archived'
        && (!onlyDone || status === 'done') && (!chatScope || chatMentions.has(task.id))
    }), 'newest')
    return sort === 'mentioned' ? newest.sort((a, b) => lastMention(b.id).localeCompare(lastMention(a.id))) : newest
  }, [agent, chatScope, chatQuery.data, onlyDone, sort, summaryQuery.data, tasks])
  const selected = shown.find((task) => task.id === open)
  const details = useQuery({
    queryKey: detailKey(open),
    queryFn: ({ signal }) => getJson<TaskDetail>(endpoint(open), signal),
    enabled: !!selected,
  })
  const move = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: TaskPatch }) =>
      postJson(`${endpoint(id)}/update`, { ...patch, actor: OPERATOR_ACTOR }),
    onSuccess: async (_, { id, patch }) => {
      const queries = { queryKey: ['tasks'] }
      await queryClient.cancelQueries(queries)
      queryClient.setQueryData<TaskRow[]>(projectTasksKey(project), (rows) =>
        rows?.map((task) => task.id === id ? { ...task, ...patch } : task))
      queryClient.setQueryData<TaskDetail>(detailKey(id), (detail) => detail?.metadata
        ? { ...detail, metadata: { ...detail.metadata, ...patch } }
        : detail)
      await queryClient.invalidateQueries(queries)
    },
    onError: fail,
  })
  const append = useMutation({
    mutationFn: async ({ text }: { id: string; text: string }) => onAppend(text),
  })
  const laneNames = orderLanes(
    [...new Set(['unassigned', ...tasks.map(laneOf), ...readStrings(`sp-lanes:${project}`).filter(Boolean)])],
    readStrings(`sp-lanes-order:${project}`),
  )
  const boardColumns = VIEW_COLUMNS[readStoredView(project)]
  const hidden = readRecord<boolean>(`sp-kanban-cols:${project}`)
  const detail = details.data
  const current = detail?.metadata ?? selected
  const currentStatus = normalizeStatus(current?.status)
  const currentLane = current ? laneOf(current) : 'unassigned'
  const columns = boardColumns.filter((column) => !hidden[column.key] || column.key === currentStatus)
  const rounds = detail?.turns?.filter((round) => round.text.trim()) ?? []
  const loading = tasksQuery.isPending || (chatScope && chatQuery.isPending)
    || (!chatScope && sort === 'mentioned' && summaryQuery.isPending)
  const failed = tasksQuery.isError || (chatScope && chatQuery.isError)
    || (!chatScope && sort === 'mentioned' && summaryQuery.isError)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 border-b border-[var(--border-default)] px-8 py-6">
        <div className="grid grid-cols-2 gap-6">
          <select aria-label={t('Task scope')} className={selectClass}
            value={chatScope ? 'chat' : 'project'} onChange={(event) => {
              setScope(event.target.value as Scope)
              setOpen('')
            }}>
            <option value="project">{t('Project')}</option>
            <option value="chat" disabled={!agent}>{t('This chat')}</option>
          </select>
          <select aria-label={t('Sort tasks')} className={selectClass} value={sort}
            onChange={(event) => setSort(event.target.value as Sort)}>
            <option value="created">{t('Newest first')}</option>
            <option value="mentioned">{t('Recently mentioned')}</option>
          </select>
        </div>
        <label className="mt-6 flex items-center gap-6 px-2 text-12 aq-ink2">
          <input type="checkbox" checked={onlyDone} onChange={(event) => setOnlyDone(event.target.checked)} />
          {t('Only done')}
        </label>
      </div>
      <div className="aq-scroll min-h-0 flex-1 p-8">
        {failed && <p role="alert" className="m-0 px-6 py-4 text-12 aq-ink3">{t('Tasks could not be read.')}</p>}
        {loading && !failed && <p role="status" className="m-0 px-6 py-4 text-12 aq-ink3">{t('Reading tasks…')}</p>}
        {!shown.length && !loading && !failed && <p className="m-0 px-6 py-4 text-12 aq-ink3">{t('No tasks match.')}</p>}
        <ul className="m-0 list-none space-y-2 p-0">
          {shown.map((task) => {
            const expanded = selected?.id === task.id
            const status = normalizeStatus(task.status)
            return (
              <li key={task.id} className={expanded ? 'rounded-4 border border-[var(--border-default)]' : ''}>
                <button type="button" className="aq-row min-w-0 gap-6 px-6 py-5 text-left" aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? '' : task.id)}>
                  <ChevronRight size={12} aria-hidden className={`shrink-0 aq-ink3 ${expanded ? 'rotate-90' : ''}`} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-12" title={task.title || task.id}>{task.title || task.id}</span>
                    <span className="block truncate font-mono text-10 aq-ink3">{task.id}</span>
                  </span>
                  <span className="max-w-[90px] truncate text-10 aq-ink3">{columnLabel(status)}</span>
                </button>
                {expanded && (
                  <div className="space-y-8 px-8 pb-8 pt-4">
                    {details.isPending && <p role="status" className="m-0 text-12 aq-ink3">{t('Reading task…')}</p>}
                    {details.isError && <p role="alert" className="m-0 text-12 aq-ink3">{t('This task could not be read.')}</p>}
                    {detail && current && (
                      <>
                        {rounds.length ? rounds.map((round) => (
                          <div key={round.n} className="min-w-0 break-words">
                            {rounds.length > 1 && <span className="aq-label">{t('Round {n}', { n: round.n })}</span>}
                            <Markdown text={round.text} />
                          </div>
                        )) : detail.description && <Markdown text={detail.description} />}
                        <div className="grid grid-cols-2 gap-6">
                          <label className="min-w-0 text-12 aq-ink2">
                            {t('Column')}
                            <select aria-label={t('Column')} className={selectClass} value={currentStatus} disabled={move.isPending}
                              onChange={(event) => {
                                const next = event.target.value
                                if (next !== currentStatus) move.mutate({ id: task.id, patch: { status: next } })
                              }}>
                              {!columns.some(({ key }) => key === currentStatus) &&
                                <option value={currentStatus}>{columnLabel(currentStatus)}</option>}
                              {columns.map(({ key, label }) => <option key={key} value={key}>{label}</option>)}
                            </select>
                          </label>
                          <label className="min-w-0 text-12 aq-ink2">
                            {t('Lane')}
                            <select aria-label={t('Lane')} className={selectClass} value={currentLane} disabled={move.isPending}
                              onChange={(event) => {
                                const next = event.target.value
                                if (next !== currentLane) move.mutate({ id: task.id, patch: laneUpdate(next) })
                              }}>
                              {!laneNames.includes(currentLane) &&
                                <option value={currentLane}>{laneLabel(currentLane)}</option>}
                              {laneNames.map((lane) => <option key={lane} value={lane}>{laneLabel(lane)}</option>)}
                            </select>
                          </label>
                        </div>
                        <button type="button" className="aq-btn line" disabled={append.isPending} onClick={() => {
                          append.mutate({ id: task.id, text: taskText({
                            ...current, description: detail.description, turn_last: detail.turns?.at(-1),
                          }, evidenceAsk) })
                        }}><ListPlus size={13} />{t('Add to draft')}</button>
                        {append.variables?.id === task.id && (append.isError || append.data === false) &&
                          <p role="alert" className="m-0 text-12 aq-ink3">{t('Could not add to draft.')}</p>}
                      </>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
