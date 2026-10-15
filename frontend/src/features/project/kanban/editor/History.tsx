/*
 * The task window's read-only sections: the History of field changes and
 * the chat mentions of the task's id. Moved out of TaskEditor.tsx; the
 * window shows them in edit mode when the section is switched on.
 */

import { LoadingSkeleton } from '../../../../components/states'
import { useQuery } from '@tanstack/react-query'
import { MentionsPanel } from '../../mentions'
import { formatStamp } from '../../../../utils/dateUtils'
import { getJson, refused } from '../../../../lib/getJson'
import { LABEL } from '../../../promptlib/taskstyle'
import { t } from '../../../../i18n/scope/project'

type TaskEvent = {
  event_id: string
  task_id: string
  timestamp: string
  actor: string
  field: string
  old_value?: string
  new_value?: string
}

/** Where this task's id showed up in captured chats — newest first; each
 *  row names the agent, copies it, and opens the chat on that turn.
 *  The rows themselves live in ./mentions, shared with the timeline. */
export function TaskMentions({ taskId }: { taskId: string }) {
  return <MentionsPanel taskId={taskId} />
}

/** GET /api/tasks/{id}/events (routers/tasks_extra.py `tasks_events`), newest first. */
type EventsAnswer = { total: number; events: TaskEvent[] }

export function TaskEventsTimeline({ taskId }: { taskId: string }) {
  const q = useQuery({
    queryKey: ['tasks', 'events', taskId],
    queryFn: ({ signal }) => getJson<EventsAnswer>(`/api/tasks/${encodeURIComponent(taskId)}/events`, signal)
      .catch(refused({ total: 0, events: [] })),
  })
  const loading = q.isLoading
  const events = Array.isArray(q.data?.events) ? q.data.events : []

  if (loading) {
    return <LoadingSkeleton variant="text" count={2} label={t('Loading history')} />
  }
  if (events.length === 0) {
    return (
      <details className="border-t border-border-subtle pt-8">
        <summary className={`${LABEL} cursor-pointer hover:text-brand`}>
          {t('History')} <span className="text-tertiary/70">— {q.isError ? t('The history could not be read') : t('No changes yet')}</span>
        </summary>
      </details>
    )
  }
  return (
    <details className="border-t border-border-subtle pt-8">
      <summary className={`${LABEL} cursor-pointer hover:text-brand`}>
        {t('History')} <span className="text-tertiary/70">— {events.length} {t('event')}{events.length === 1 ? '' : 's'}</span>
      </summary>
      <div className="mt-6 flex flex-col gap-2 max-h-[200px] overflow-y-auto">
        {events.map((ev) => (
          <div
            key={ev.event_id}
            className="flex items-baseline gap-6 text-11 font-mono py-2 border-b border-border-subtle last:border-b-0"
          >
            <span className="text-tertiary min-w-[130px]">{formatStamp(ev.timestamp)}</span>
            <span className="text-secondary min-w-[50px]">{ev.actor}</span>
            <span className="text-brand min-w-[72px]">{ev.field}</span>
            {ev.old_value ? (
              <>
                <span className="text-tertiary line-through max-w-[140px] truncate" title={ev.old_value}>{ev.old_value}</span>
                <span className="text-tertiary">→</span>
              </>
            ) : (
              <span className="text-tertiary">→</span>
            )}
            <span className="text-primary truncate" title={ev.new_value}>{ev.new_value || '(cleared)'}</span>
          </div>
        ))}
      </div>
    </details>
  )
}
