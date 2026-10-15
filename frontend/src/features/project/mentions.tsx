import { useState, type ReactNode } from 'react'
import { LoadingSkeleton } from '../../components/states'
import { TerminalSquare } from 'lucide-react'
import { showTerminal, terminalOfAgent, useTerminalActions, useTerminals } from '../../lib/terminal'
import { StateDot } from '../terminal/parts'
import { IconButton } from '../../components/primitives'
import { useQuery } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'

import { ChatReader } from '../agents/dossier'
import type { ProfileSession } from '../agents/profile'
import { LensDrawer } from '../../lenses/LensDrawer'
import { LENSES } from '../../lenses/config'
import { CopyButton } from '../../components/CopyButton'
import { useCopy } from '../../lib/useCopy'
import { agentLabel } from '../../utils/agentLabel'
import { formatStamp } from '../../utils/dateUtils'
import { resumeCommand } from './AgentDrill'
import { Modal } from '../../components/Modal'
import { getJson, refused } from '../../lib/getJson'
import { LABEL } from '../promptlib/taskstyle'
import { t } from '../../i18n/scope/project'

/**
 * Chat mentions of a task — one component for every place that draws them.
 *
 * A mention is a captured turn that named a task id: the operator handing
 * the task to an agent (◆), or the agent answering about it (◇). The row
 * says who in words, not only the raw id, carries both to the clipboard,
 * and offers the command that picks that chat back up in a terminal.
 * Clicking it opens the chat on the very turn that named the task.
 *
 * The task window, the task timeline and the card chip all read from here,
 * so the way a mention reads cannot drift apart between them again.
 */

/** What the server knows about the agent behind a mention. */
export type MentionAgent = {
  agent_id: string
  agent_name?: string | null
  chat_title?: string | null
  created_date?: string | null
  /** Origin the capture hook recorded — enough to resume the chat. */
  tool?: string | null
  cwd?: string | null
  session_ref?: string | null
  /** The operator's group for this lane, when it has one. */
  agent_group?: string | null
}

export type Mention = {
  at: string
  role: 'user' | 'agent'
  agent_id: string
  session_id: string
  turn: number
  excerpt?: string
  project?: string
  /** Absent on older payloads; the label then falls back to the id. */
  agent?: MentionAgent | null
}

/** The agent's name in words. Falls back to the tool and the id. */
export function mentionLabel(m: { agent_id: string; agent?: MentionAgent | null }): string {
  return agentLabel(m.agent ?? { agent_id: m.agent_id })
}

/** "Name · id" for a tooltip; the id alone when the name is the id. */
export function mentionWho(m: { agent_id: string; agent?: MentionAgent | null }): string {
  const label = mentionLabel(m)
  return label === m.agent_id ? m.agent_id : `${label} · ${m.agent_id}`
}

/** The command that resumes this agent's chat; '' when it cannot be built. */
export function mentionResume(agent?: MentionAgent | null): string {
  if (!agent) return ''
  return resumeCommand(agent.tool ?? '', agent.cwd ?? '', agent.session_ref ?? '')
}

function mentionTime(at: string): string {
  return formatStamp(at)
}

/** A word that copies itself. */
function CopyWord({ text, title, className = '' }: { text: string; title: string; className?: string }) {
  const { copied, copy } = useCopy()
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={(e) => { e.stopPropagation(); void copy(text) }}
      className={`inline-flex items-baseline gap-3 min-w-0 rounded-input px-3 -mx-3 hover:bg-hover hover:text-primary ${className}`}
    >
      <span className="truncate">{text}</span>
      {copied && <Check size={10} className="text-status-green shrink-0" aria-hidden />}
    </button>
  )
}

/**
 * Resume: the agent comes back in a Slightly Parallel terminal, in its own folder —
 * or its open terminal comes forward. The small copy button beside it
 * keeps the command for a terminal of your own. Absent when the chat
 * cannot be resumed.
 */
export function ResumeButton({ agent, className = '' }: { agent?: MentionAgent | null; className?: string }) {
  const cmd = mentionResume(agent)
  const act = useTerminalActions()
  const list = useTerminals().data
  if (!cmd || !agent) return null
  const live = terminalOfAgent(list?.sessions, agent.agent_id)
  return (
    <span className={`shrink-0 inline-flex items-center h-20 rounded-input border border-border-subtle overflow-hidden text-10 font-mono ${className}`}>
      <button type="button" onClick={() => live ? showTerminal(live.id) : act.open({ kind: 'resume', agent_id: agent.agent_id })}
        title={live ? t('Show its terminal ({state})', { state: live.state === 'waiting' ? t('waiting for you') : live.state }) : t('Resume in a terminal: {cmd}', { cmd })}
        className="inline-flex items-center gap-3 h-full px-6 text-tertiary hover:text-primary hover:bg-hover">
        {live ? <><StateDot state={live.state} size={6} /> {t('terminal')}</> : <><TerminalSquare size={10} aria-hidden /> {t('Resume')}</>}
      </button>
      <CopyButton text={cmd} title={cmd} ariaLabel={t('Copy the resume command')} size={10}
        className="inline-flex items-center h-full px-4 border-l border-border-subtle text-tertiary hover:text-primary hover:bg-hover" />
    </span>
  )
}

export function MentionRow({ m, onOpen }: { m: Mention; onOpen: () => void }) {
  const user = m.role === 'user'
  const label = mentionLabel(m)
  return (
    <div className="flex items-baseline gap-8 px-6 py-3 rounded-input text-11 font-mono min-w-0 hover:bg-hover">
      <span className={`shrink-0 ${user ? 'text-status-amber' : 'text-brand'}`}>
        {user ? t('◆ sent to') : t('◇ reply from')}
      </span>
      <CopyWord text={label} title={`Copy ${label}`} className="text-secondary shrink-0 max-w-[160px]" />
      {label !== m.agent_id && (
        <CopyWord text={m.agent_id} title={`Copy ${m.agent_id}`} className="text-tertiary shrink-0" />
      )}
      <button
        type="button"
        onClick={onOpen}
        title={t('Open this chat')}
        className="flex-1 min-w-0 text-left flex items-baseline gap-8"
      >
        <span className="text-tertiary shrink-0">{mentionTime(m.at)} {t('· turn')} {m.turn}</span>
        {m.excerpt && <span className="text-tertiary truncate">“{m.excerpt}”</span>}
      </button>
      <ResumeButton agent={m.agent} />
    </div>
  )
}

/**
 * The chat behind a mention, opened on the turn that named the task.
 *
 * The grown-up reader from the agent page — markdown, find, both orders,
 * a size — with the agent and the way to resume it in the header.
 */
export function MentionChat({
  mention, onClose, onOpenTask,
}: {
  mention: Mention
  onClose: () => void
  onOpenTask?: (id: string) => void
}) {
  const [lens, setLens] = useState<{ lens: string; id: string } | null>(null)
  const { data, isLoading, isError } = useQuery({
    queryKey: ['mention-session', mention.session_id],
    queryFn: ({ signal }) => getJson<{ metadata: ProfileSession }>(`/api/sessions/${encodeURIComponent(mention.session_id)}`, signal),
    staleTime: 60_000,
  })
  const session = data?.metadata
  const label = mentionLabel(mention)
  const cmd = mentionResume(mention.agent)
  const folder = mention.agent?.cwd ?? ''

  return (
    <Modal label={t('Chat')} onClose={onClose} width="w-[900px]" padding="p-0" top>
      <aside className="h-[80vh] min-h-0 outline-none flex flex-col">
        <div className="flex items-center gap-8 px-16 py-10 border-b border-border-subtle">
          <span className="text-11 font-mono text-tertiary truncate">{mention.session_id}</span>
          <IconButton label={t('Close the chat')} onClick={onClose} className="ml-auto">
            <X size={14} aria-hidden />
          </IconButton>
        </div>
        <div className="flex-1 min-h-0 p-12">
          {isLoading && <LoadingSkeleton variant="text" count={3} label={t('Loading')} />}
          {isError && <div className="text-12 text-tertiary">{t('This chat could not be read.')}</div>}
          {session && (
            <ChatReader
              sessions={[session]}
              onOpenLens={(l, id) => setLens({ lens: l, id })}
              onOpenTask={onOpenTask}
              markTurn={mention.turn}
              fill
              extra={
                <span className="inline-flex items-center gap-6 text-10 font-mono shrink-0 min-w-0">
                  <span className="text-secondary truncate max-w-[160px]" title={mention.agent_id}>{label}</span>
                  {folder && (
                    <span className="text-tertiary truncate max-w-[220px]" title={folder}>{folder}</span>
                  )}
                  {cmd
                    ? <ResumeButton agent={mention.agent} />
                    : <span className="text-tertiary">{t('No chat id recorded.')}</span>}
                </span>
              }
            />
          )}
        </div>
      </aside>
      {lens && LENSES[lens.lens] && (
        <LensDrawer lens={LENSES[lens.lens]!} id={lens.id} presentation="reading" onClose={() => setLens(null)} />
      )}
    </Modal>
  )
}

/** Every captured turn that named this task, newest first. */
export function MentionsPanel({ taskId }: { taskId: string }) {
  const [open, setOpen] = useState<Mention | null>(null)
  // A refused read (the task is gone) is no mentions; a failed one says so.
  const read = useQuery({
    queryKey: ['tasks', taskId, 'mentions'],
    queryFn: ({ signal }) =>
      getJson<{ total?: number; mentions?: Mention[] }>(`/api/tasks/${encodeURIComponent(taskId)}/mentions`, signal)
        .catch(refused({ mentions: [] })),
  })
  if (read.isLoading) return null
  const rows = Array.isArray(read.data?.mentions) ? read.data.mentions : []
  return (
    <details className="border-t border-border-subtle pt-8" open={rows.length > 0 && rows.length <= 3}>
      <summary className={`${LABEL} cursor-pointer hover:text-brand`}>
        {t('Chat')} <span className="text-tertiary/70">— {read.isError ? t('The mentions could not be read.') : rows.length === 0 ? t('No chats mention this task.') : `${rows.length} mention${rows.length === 1 ? '' : 's'}`}</span>
      </summary>
      {rows.length > 0 && (
        <div className="mt-6 flex flex-col gap-2 max-h-[200px] overflow-y-auto">
          {rows.map((m, i) => (
            <MentionRow key={`${m.session_id}-${m.turn}-${i}`} m={m} onOpen={() => setOpen(m)} />
          ))}
        </div>
      )}
      {rows.length === 0 && !read.isError && (
        <p className="mt-4 text-11 text-tertiary">{t('Copy the task with copy on and paste it to an agent. The task id goes with the text, and the chat appears here.')}</p>
      )}
      {open && <MentionChat mention={open} onClose={() => setOpen(null)} />}
    </details>
  )
}

/** Shared by hosts that render their own trigger and just need the chat. */
export function useMentionChat(): {
  open: (m: Mention) => void
  chat: ReactNode
} {
  const [mention, setMention] = useState<Mention | null>(null)
  return {
    open: (m: Mention) => setMention(m),
    chat: mention ? <MentionChat mention={mention} onClose={() => setMention(null)} /> : null,
  }
}
