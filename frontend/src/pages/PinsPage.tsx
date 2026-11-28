import { DashboardAgentMention } from '../features/terminal/messageMenu/AgentTerminalMenu'
import { useEffect, useMemo, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Pin, X } from 'lucide-react'

import { PageHeader } from '../components/PageHeader'
import { Input } from '../components/primitives'
import { CopyButton } from '../components/CopyButton'
import { Segmented } from '../components/Segmented'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/states'
import { useHashState } from '../hooks/useHashState'
import { usePinList, useMsgMarkActions, type ForkState, type MsgMark, type PinList } from '../lib/pins'
import { projectColor } from '../utils/projectColor'
import { listedIn, projectCodes, rowProjects } from '../lib/projectCodes'
import { mentionLabel } from '../features/project/mentions'
import { MarkGlyph } from '../features/chats/ChatPins'
import { LABEL, PillGroup } from '../features/promptlib/taskstyle'
import { PINS_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { formatStamp } from '../utils/dateUtils'
import { t } from '../i18n/scope/pages'

/**
 * /pins — the marks on one message, across every project: the pins (#pin,
 * to come back to), the carried messages (#carry, #carry-brief: given back
 * to the agent after a context compaction) and the forks for later
 * (#fork-later: work another agent could take, with the command that
 * starts it). Each row opens the chat on its message; ✕ takes the mark off.
 */

const LISTS: Array<readonly [PinList, string]> = [['pin', t('Pins')], ['carry', t('Carried')], ['fork', t('Fork later')]]

function matches(m: MsgMark, q: string): boolean {
  if (!q) return true
  const hay = `${m.text}\n${m.excerpt}\n${m.brief ?? ''}\n${mentionLabel({ agent_id: m.agent_id, agent: m.agent })}\n${m.target}`
  return hay.toLowerCase().includes(q)
}

export default function PinsPage() {
  useEffect(() => { document.title = `${t('Pins')} — Slightly Parallel` }, [])
  const [hash, setHash] = useHashState()
  const list = (['pin', 'carry', 'fork'].includes(hash.list ?? '') ? hash.list : 'pin') as PinList
  const project = hash.project ?? ''
  const q = (hash.q ?? '').trim().toLowerCase()
  const lists = { pin: usePinList('pin'), carry: usePinList('carry'), fork: usePinList('fork') }
  const cur = lists[list]
  const items = useMemo(() => cur.data?.items ?? [], [cur.data])
  // A mark of a chat's message shows in every project of that chat.
  const projects = useMemo(() => [...new Set(items.flatMap((m) => projectCodes(rowProjects(m))))].sort(), [items])
  const shown = items.filter((m) => (!project || listedIn(m, project)) && matches(m, q))
  const act = useMsgMarkActions()

  return (
    <div className="flex flex-col gap-24 min-w-0">
      <PageHeader variant="lens" icon={Pin} title={t('Pins')} count={cur.isLoading ? '' : items.length}
        actions={<Input value={hash.q ?? ''} onChange={(e) => setHash({ q: e.target.value })} placeholder={t('Find in marked messages')}
          aria-label={t('Find in marked messages')} className="w-[220px] h-24 text-12" />} />
      <PageGuide id="pins" guide={PINS_GUIDE} examples={0} />
      <div className="flex items-center gap-16 flex-wrap">
        <Segmented label={t('Which marks')} value={list} onChange={(v) => setHash({ list: v === 'pin' ? '' : v })}
          options={LISTS.map(([v, w]) => [v, `${w} ${lists[v].data ? lists[v].data.items.length : ''}`.trim()] as const)} />
        {projects.length > 1 && (
          <PillGroup label={t('Project')} value={project} onChange={(v) => setHash({ project: v })}
            options={projects.map((p) => [p, p])} />
        )}
      </div>
      {cur.isLoading && <LoadingSkeleton variant="card" count={2} />}
      {cur.isError && <ErrorBanner title={t('Could not read the marked messages')} onRetry={() => void cur.refetch()} hideDismiss />}
      {!cur.isLoading && items.length === 0 && (
        <EmptyState title={list === 'pin' ? t('No message is pinned.') : list === 'carry' ? t('No message is carried.') : t('No message is kept to fork later.')}
          subtitle={list === 'pin'
            ? t('Type #pin in a message, or click the pin on a message in the chat reader.')
            : list === 'carry'
              ? t('Type #carry or #carry-brief in a message, or click the light on a message in the chat reader.')
              : t('Type #fork-later in a message, or click the fork on a message in the chat reader.')} />
      )}
      {items.length > 0 && shown.length === 0 && <p className="text-12 text-tertiary">{t('Nothing matches.')}</p>}
      {shown.length > 0 && (
        <ul className="rounded-card border border-border-subtle bg-surface divide-y divide-border-subtle">
          {shown.map((m) => (
            <Row key={m.id || `${m.kind}:${m.target}`} m={m} onRemove={() => act.remove(list, m.target)}>
              {list === 'carry' && <CarryLine m={m} />}
              {list === 'fork' && <ForkLine m={m} onState={(s) => act.setState(m.target, s)} />}
            </Row>
          ))}
        </ul>
      )}
    </div>
  )
}

function Row({ m, onRemove, children }: { m: MsgMark; onRemove: () => void; children?: ReactNode }) {
  const line = (m.excerpt || m.text).split('\n').find((l) => l.trim())?.trim() || t('turn {n}', { n: m.turn })
  const who = mentionLabel({ agent_id: m.agent_id, agent: m.agent })
  const to = `/chats#project=${encodeURIComponent(m.project)}&agent=${encodeURIComponent(m.agent_id)}&sel=${encodeURIComponent(m.session_id)}&turn=${m.turn}`
  return (
    <li className="flex flex-col gap-4 px-10 py-6 min-w-0">
      <div className="flex items-center gap-10 min-w-0">
        <MarkGlyph m={m} size={12} />
        <Link to={to} className="min-w-0 flex-1 flex flex-col hover:text-brand">
          <span className="text-13 text-primary truncate">{line}</span>
          <span className="text-11 font-mono text-tertiary truncate">
            <DashboardAgentMention agent={m.agent_id} label={who} fallback={who} /> · {t('turn {n}', { n: m.turn })}{m.side === 'reply' ? ` · ${t('the reply')}` : ''} · {t('{n} characters', { n: m.chars })}
          </span>
        </Link>
        {m.project && (
          <span className="shrink-0 inline-flex items-center gap-4 text-11 font-mono text-tertiary">
            <span className="w-6 h-6 rounded-pill" style={{ background: projectColor(m.project) }} aria-hidden />{m.project}
          </span>
        )}
        <span className="shrink-0 w-[96px] text-right text-11 font-mono text-tertiary tabular">{formatStamp(m.marked_at).slice(5)}</span>
        <button type="button" onClick={onRemove} title={t('Take the mark off')} aria-label={t('Take the mark off')}
          className="shrink-0 p-2 rounded-input text-tertiary hover:text-primary hover:bg-hover">
          <X size={12} aria-hidden />
        </button>
      </div>
      {children}
    </li>
  )
}

function CarryLine({ m }: { m: MsgMark }) {
  const whole = m.kind === 'carry'
  return (
    <div className="flex flex-col gap-2 pl-24 text-11 text-secondary min-w-0">
      <span className="font-mono text-tertiary">
        {whole ? t('given back whole, with the reply') : t('given back as the brief')}
        {m.given_at && ` · ${t('given back after compaction at {at}', { at: formatStamp(m.given_at) })}`}
        {m.left_out_at && (!m.given_at || m.left_out_at > m.given_at) && ` · ${t('left out at {at}: over the budget', { at: formatStamp(m.left_out_at) })}`}
      </span>
      {!whole && (m.brief
        ? <p className="whitespace-pre-wrap break-words leading-relaxed">{m.brief}</p>
        : <p className="text-status-amber">{t('No brief yet: the agent is asked to write it at the next message in that chat.')}</p>)}
    </div>
  )
}

function ForkLine({ m, onState }: { m: MsgMark; onState: (s: ForkState) => void }) {
  return (
    <div className="flex items-center gap-8 pl-24 min-w-0 flex-wrap">
      <span className={LABEL}>{t('State')}</span>
      <Segmented label={t('State')} value={m.state || 'waiting'} height={20}
        onChange={(v) => onState(v === 'waiting' ? '' : v as ForkState)}
        options={[['waiting', t('waiting')], ['started', t('started')], ['dropped', t('dropped')]]} />
      {m.command
        ? (
          <span className="min-w-0 flex-1 inline-flex items-center gap-6">
            <code className="min-w-0 flex-1 truncate text-10 font-mono text-tertiary" title={m.command}>{m.command}</code>
            <CopyButton text={m.command} title={t('Copy the command that starts it: this chat resumed into a new one, with the message as its first prompt')}
              label={t('Copy command')} size={10}
              className="shrink-0 inline-flex items-center gap-4 h-20 px-6 rounded-input border border-border-subtle text-10 font-mono text-secondary hover:text-primary hover:border-brand" />
          </span>
        )
        : <span className="text-11 text-tertiary">{t('No command: the chat\'s tool cannot fork it, or its session and folder are not known.')}</span>}
    </div>
  )
}
