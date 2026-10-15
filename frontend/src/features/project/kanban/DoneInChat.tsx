import { duration } from '../../../utils/format'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { getJson } from '../../../lib/getJson'
import { t, tn } from '../../../i18n/scope/project'

interface Stretch {
  agent_id: string
  start: number
  end: number
  turns: number
  chats: number
  minutes: number
  first: string
  done_at: string
  result: string
}


/**
 * The operator's #done in a chat: where it was typed and what its stretch of
 * the chat adds up to — messages, time, from the first message to the #done
 * (backend donelib.py). Nothing shows for a task never closed that way.
 */
export function DoneInChat({ taskId }: { taskId: string }) {
  const q = useQuery({
    queryKey: ['tasks', 'done-in-chat', taskId],
    queryFn: ({ signal }) => getJson<{ stretches: Stretch[]; reopened: boolean }>(`/api/tasks/${encodeURIComponent(taskId)}/done`, signal),
  })
  const rows = q.data?.stretches ?? []
  if (!rows.length) return null
  return (
    <div className="text-11 font-mono flex flex-col gap-2">
      {rows.map((s) => (
        <div key={`${s.agent_id}#${s.end}`} className="flex items-baseline gap-6 flex-wrap" style={{ color: 'var(--status-green)' }}>
          <span>{t('✓ #done in the chat')}{s.result === 'moved' ? '' : s.result === 'already' ? t(' (already done)') : t(' (archived)')}</span>
          <span className="text-secondary tabular-nums">{tn(s.turns, '{n} message', '{n} messages')} · {duration(s.minutes * 60)}{s.chats > 1 ? ` · ${tn(s.chats, '{n} chat', '{n} chats')}` : ''}</span>
          <span className="text-tertiary tabular-nums">{s.first.replace('T', ' ')} → {s.done_at.replace('T', ' ').slice(0, 16)}</span>
          <Link to={`/agent/${encodeURIComponent(s.agent_id)}`} className="text-tertiary hover:text-primary underline-offset-2 hover:underline">
            {t('turns {start}–{end} of {agent}', { start: s.start, end: s.end, agent: s.agent_id })}
          </Link>
        </div>
      ))}
      {q.data?.reopened && <span style={{ color: 'var(--status-amber)' }}>{t('moved out of done later')}</span>}
    </div>
  )
}
