/*
 * The task window's Links section: the task's blocks / parent / relates
 * links, removable, plus a title search to add one. Moved out of
 * TaskEditor.tsx; the board's LinksOverlay is the visual counterpart.
 */

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, toast } from '../../../../components/primitives'
import { OPERATOR_ACTOR } from '../../types'
import { getJson, postJson, refused } from '../../../../lib/getJson'
import { normalizeStatus } from '../model'
import type { LinkKind, TaskLink } from '../model'
import { useProjectTasks, type TaskLinksAnswer } from '../../../tasks/data'
import { LABEL } from '../../../promptlib/taskstyle'
import { t } from '../../../../i18n/scope/project'

/** Links of one task inside the editor: list, remove, add by searching a
 *  title. The board overlay is the visual counterpart. */
export function TaskLinks({ taskId, projectCode, onOpen, onChanged }: { taskId: string; projectCode: string; onOpen: (id: string) => void; onChanged?: () => void }) {
  const qc = useQueryClient()
  const linksKey = ['tasks', 'links', 'task', taskId]
  const links = useQuery({
    queryKey: linksKey,
    queryFn: ({ signal }) => getJson<TaskLinksAnswer>(`/api/tasks/${encodeURIComponent(taskId)}/links`, signal)
      .catch(refused<TaskLinksAnswer>({ links: [] })),
  })
  const rows: TaskLink[] = Array.isArray(links.data?.links) ? links.data.links : []
  const [q, setQ] = useState('')
  const [kind, setKind] = useState<LinkKind>('blocks')
  const reload = () => void qc.invalidateQueries({ queryKey: linksKey })
  // The project's tasks, asked for when the search is first used — not
  // again on every key (and already there if another panel read them).
  const searching = q.trim() !== ''
  const candidates = useProjectTasks(projectCode, searching).data ?? []
  const add = async (to: string) => {
    setQ('')
    try {
      await postJson(`/api/tasks/${encodeURIComponent(taskId)}/link`, { to, kind, actor: OPERATOR_ACTOR })
      onChanged?.()
    } catch (e) {
      toast.error(t('Couldn\'t link: {error}', { error: (e as Error).message }))
    }
    reload()
  }
  const remove = async (id: string) => {
    try {
      await postJson(`/api/tasks/links/${encodeURIComponent(id)}/delete`, { actor: OPERATOR_ACTOR })
      onChanged?.()
    } catch (e) {
      toast.error(t("Couldn't remove the link: {reason}", { reason: (e as Error).message }))
    }
    reload()
  }
  const needle = q.trim().toLowerCase()
  const hits = needle
    ? candidates.filter((t) => t.id !== taskId && (String(t.title || '').toLowerCase().includes(needle) || t.id.includes(needle))).slice(0, 6)
    : []
  const describe = (l: TaskLink) => {
    const other = l.from_id === taskId ? l.to : l.from
    const label =
      l.kind === 'relates' ? t('relates to')
      : l.kind === 'blocks' ? (l.from_id === taskId ? 'blocks' : 'blocked by')
      : (l.from_id === taskId ? t('parent of') : t('sub-task of'))
    return { other, label }
  }
  return (
    <details className="border-t border-border-subtle pt-8" open={rows.length > 0}>
      <summary className={`${LABEL} cursor-pointer hover:text-brand`}>
        {t('Links')} <span className="text-tertiary/70">— {links.isError ? t('The links could not be read') : rows.length === 0 ? 'none' : `${rows.length}`}</span>
      </summary>
      <div className="mt-6 flex flex-col gap-4">
        {rows.map((l) => {
          const { other, label } = describe(l)
          const done = normalizeStatus(other.status) === 'done'
          return (
            <div key={l.id} className="flex items-center gap-8 text-11 font-mono px-6 py-3 rounded-input hover:bg-hover">
              <span className={label === 'blocked by' && !done ? 'text-status-red' : label.startsWith('parent') || label.startsWith('sub') ? 'text-brand' : 'text-tertiary'}>{label}</span>
              <button type="button" onClick={() => onOpen(other.id)} className="text-secondary hover:text-primary truncate text-left" title={t('Open')}>
                {other.title || other.id}
              </button>
              <span className={`text-10 ${done ? 'text-status-green' : 'text-tertiary'}`}>{other.status || ''}</span>
              <Button variant="danger-text" size="bare" onClick={() => void remove(l.id)} className="ml-auto" aria-label={t('Remove link')}>×</Button>
            </div>
          )
        })}
        <div className="flex items-center gap-6 flex-wrap">
          <select value={kind} onChange={(e) => setKind(e.target.value as LinkKind)} className="bg-elevated text-primary border border-border-default rounded-input px-6 py-2 text-11 font-mono" aria-label={t('Link kind')}>
            <option value="blocks">{t('blocks')}</option>
            <option value="parent">{t('parent of')}</option>
            <option value="relates">{t('relates to')}</option>
          </select>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('Search tasks by title or id')}
            aria-label={t('Link target')}
            className="flex-1 min-w-[180px] bg-elevated text-primary border border-border-default rounded-input px-8 py-2 text-11 font-mono"
          />
        </div>
        {hits.length > 0 && (
          <ul className="flex flex-col gap-2">
            {hits.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => void add(t.id)} className="w-full text-left text-11 font-mono px-8 py-3 rounded-input hover:bg-hover flex items-center gap-8">
                  <span className="text-primary truncate">{t.title}</span>
                  <span className="text-tertiary">{t.status}</span>
                  <span className="ml-auto text-tertiary">{t.id}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  )
}
