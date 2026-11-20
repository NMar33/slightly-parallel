import { GitFork, Pin } from 'lucide-react'
import { Link } from 'react-router-dom'

import { CARRY_COLOR } from '../../components/MsgMarkButtons'
import { useMsgMarks, type MsgMark } from '../../lib/pins'
import { formatStamp } from '../../utils/dateUtils'

import { t } from '../../i18n/scope/views'

/** The glyph of a mark, the same as on its button. */
export function MarkGlyph({ m, size = 10 }: { m: Pick<MsgMark, 'kind'>; size?: number }) {
  if (m.kind === 'pin') return <Pin size={size} className="text-brand shrink-0" fill="currentColor" aria-hidden />
  if (m.kind === 'fork') return <GitFork size={size} className="text-brand shrink-0" aria-hidden />
  return (
    <span aria-hidden className="rounded-pill shrink-0"
      style={{ width: size - 2, height: size - 2, background: CARRY_COLOR[m.kind === 'carry' ? 'carry' : 'brief'] }} />
  )
}

const ORDER: Record<MsgMark['kind'], number> = { pin: 0, carry: 1, 'carry-brief': 1, fork: 2 }

/**
 * This chat's marked messages in one line above the reader: pins, carried
 * messages, forks for later, in turn order. A click goes to the message.
 * The last time the carried messages were given back after a compaction
 * closes the line. Nothing is drawn for a chat with no mark.
 */
export function ChatPins({ agentId, onGo }: { agentId: string; onGo: (m: MsgMark) => void }) {
  const { all, deliveries } = useMsgMarks()
  const mine = all.filter((m) => m.agent_id === agentId)
    .sort((a, b) => ORDER[a.kind] - ORDER[b.kind] || a.turn - b.turn || a.side.localeCompare(b.side))
  if (mine.length === 0) return null
  const given = deliveries.find((d) => d.agent_id === agentId && d.given.length > 0)
  return (
    <div className="flex items-center gap-6 flex-wrap text-10 font-mono" role="list" aria-label={t('Marked messages in this chat')}>
      <span className="uppercase tracking-wide text-tertiary">{t('Marked')}</span>
      {mine.map((m) => {
        const kind = m.kind === 'pin' ? t('pinned') : m.kind === 'fork' ? t('fork later')
          : m.kind === 'carry' ? t('carried whole') : t('carried as a brief')
        const line = (m.excerpt || m.text).split('\n').find((l) => l.trim())?.trim() ?? ''
        return (
          <button key={m.id || `${m.kind}:${m.target}`} type="button" role="listitem" onClick={() => onGo(m)}
            title={`${kind} · ${t('turn {n}', { n: m.turn })}${m.side ? ` · ${t('reply')}` : ''}\n${line}`}
            className="inline-flex items-center gap-4 h-20 px-6 max-w-[260px] rounded-pill border border-border-subtle bg-surface text-secondary hover:text-primary hover:border-brand">
            <MarkGlyph m={m} />
            <span className="tabular shrink-0">{m.turn}{m.side ? '↩' : ''}</span>
            <span className="truncate font-sans text-11">{line}</span>
          </button>
        )
      })}
      {given && (
        <span className="text-tertiary" title={t('The carried messages were given back to the agent after a context compaction')}>
          {t('given back after compaction at {at}', { at: formatStamp(given.at) })}
        </span>
      )}
      <Link to="/pins" className="ml-auto text-tertiary hover:text-brand">{t('all marks')}</Link>
    </div>
  )
}
