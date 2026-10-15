import { useState } from 'react'
import { LoadingSkeleton } from '../../components/states'
import { useQuery } from '@tanstack/react-query'

import { getJson, refused } from '../../lib/getJson'

import { CopyButton } from '../../components/CopyButton'
import { LensDrawer } from '../../lenses/LensDrawer'
import { LENSES } from '../../lenses/config'
import type { Agent, AgentDetailAnswer, AgentRecord } from './types'
import { LABEL } from '../promptlib/taskstyle'
import { t, tn } from '../../i18n/scope/project'

/**
 * AgentDrill — everything one agent left behind, in one place.
 *
 * A switcher under the agent card: the scans it posted, its file entries, its captured sessions (the chat), and
 * how to resume it — tool, folder, full session id, and the command to
 * pick the session back up, built from the origin the capture hook records.
 */

type View = 'scans' | 'files' | 'chat' | 'resume'

type ListRow = {
  id: string
  created_date?: string
  created_time?: string
  start_time?: string
  l1?: string
  turns_n?: number
  duration_min?: number
}

const LIST_SOURCES: Record<'scans' | 'files' | 'chat', { url: (aid: string) => string; key: string; lens: string; empty: string }> = {
  scans: {
    url: (aid) => `/api/scans?agent_id=${encodeURIComponent(aid)}&limit=200`,
    key: 'scans', lens: 'scans',
    empty: t('No scans from this agent yet. #scan posts one.'),
  },
  files: {
    url: (aid) => `/api/files?agent_id=${encodeURIComponent(aid)}&limit=200`,
    key: 'files', lens: 'files',
    empty: t('No file entries yet. Each #scan writes one.'),
  },
  chat: {
    url: (aid) => `/api/sessions?agent_id=${encodeURIComponent(aid)}`,
    key: 'sessions', lens: 'sessions',
    empty: t('No chats for this agent yet.'),
  },
}

/** Resume command per tool; '' = unknown tool, show the facts only. */
export function resumeCommand(tool: string, cwd: string, sessionRef: string): string {
  if (!sessionRef) return ''
  const cd = cwd ? `cd "${cwd}" && ` : ''
  if (tool === 'claude-code') return `${cd}claude -r ${sessionRef}`
  if (tool === 'codex') return `${cd}codex resume ${sessionRef}`
  if (tool === 'opencode') return `${cd}opencode --session ${sessionRef}`
  return ''
}

const VIEWS: View[] = ['scans', 'files', 'chat', 'resume']

function AgentDrill({ agent }: { agent: Agent }) {
  const [view, setView] = useState<View>(VIEWS[0]!)
  return (
    <div className="border-t border-border-subtle pt-8 mt-4 flex flex-col gap-8">
      <div role="tablist" aria-label={t('Agent detail')} className="inline-flex self-start rounded-input border border-border-subtle overflow-hidden">
        {VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() => setView(v)}
            className={`px-10 h-24 text-11 font-mono transition-colors ${
              view === v ? 'bg-hover text-primary' : 'text-tertiary hover:text-secondary'
            }`}
          >
            {v}
          </button>
        ))}
      </div>
      {(view === 'scans' || view === 'files' || view === 'chat') && (
        <DrillList key={view} agentId={agent.id} kind={view} />
      )}
      {view === 'resume' && <ResumePanel agent={agent} />}
    </div>
  )
}

function DrillList({ agentId, kind }: { agentId: string; kind: 'scans' | 'files' | 'chat' }) {
  const src = LIST_SOURCES[kind]
  const [open, setOpen] = useState<string | null>(null)
  // A lens key: the list follows the freshness stamp of its own area.
  const list = useQuery({
    queryKey: ['lens', src.lens, 'by-agent', agentId],
    queryFn: ({ signal }) =>
      getJson<Record<string, unknown>>(src.url(agentId), signal)
        .then((d) => (Array.isArray(d?.[src.key]) ? d[src.key] as ListRow[] : [])),
  })
  // A list that could not be read shows as none, as before.
  const rows = list.data ?? (list.isError ? [] : null)
  if (rows === null) return <LoadingSkeleton variant="text" count={3} label={t('Loading')} />
  if (rows.length === 0) return <div className="text-12 text-tertiary italic">{src.empty}</div>
  return (
    <>
      <ol className="flex flex-col gap-2 max-h-[280px] overflow-y-auto pr-2">
        {rows.map((r) => (
          <li key={r.id}>
            <button
              type="button"
              onClick={() => setOpen(r.id)}
              className="w-full text-left text-12 font-mono flex items-baseline gap-8 px-6 py-3 rounded-input hover:bg-hover"
              title={t('Open')}
            >
              <span className="text-tertiary tabular shrink-0">
                {r.created_date} {r.created_time || r.start_time || ''}
              </span>
              <span className="text-secondary truncate">{r.l1 || r.id}</span>
              {kind === 'chat' && r.turns_n != null && (
                <span className="ml-auto text-tertiary shrink-0">{tn(r.turns_n, '{n} turn', '{n} turns')} · {t('{n}m', { n: r.duration_min ?? 0 })}</span>
              )}
            </button>
          </li>
        ))}
      </ol>
      {open && (
        <LensDrawer lens={LENSES[src.lens]!} id={open} presentation="reading" onClose={() => setOpen(null)} />
      )}
    </>
  )
}

const TOOL_LABEL: Record<string, string> = {
  'claude-code': 'Claude Code', codex: 'Codex', opencode: 'OpenCode', cursor: 'Cursor',
}

function ResumePanel({ agent }: { agent: Agent }) {
  const tool = agent.tool || (agent.id.startsWith('cc-') ? 'claude-code' : agent.id.startsWith('codex-') ? 'codex' : agent.id.startsWith('oc-') ? 'opencode' : agent.id.startsWith('cursor-') ? 'cursor' : '')
  const cmd = resumeCommand(tool, agent.cwd || '', agent.session_ref || '')
  const rows: Array<[string, string]> = [
    ['tool', TOOL_LABEL[tool] || tool || 'unknown'],
    [t('agent id'), agent.id],
    ['session', agent.session_ref || '—'],
    ['folder', agent.cwd || '—'],
    [t('last active'), agent.last_active || '—'],
  ]
  return (
    <div className="flex flex-col gap-8">
      <dl className="grid grid-cols-[auto_1fr] gap-x-12 gap-y-3 text-12">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className={LABEL}>{k}</dt>
            <dd className="font-mono text-secondary break-all">{v}</dd>
          </div>
        ))}
      </dl>
      {cmd ? (
        <div className="flex items-start gap-8 rounded-input border border-border-subtle bg-base px-10 py-8">
          <code className="text-12 font-mono text-primary break-all flex-1">{cmd}</code>
          <CopyButton
            text={cmd}
            title={t('Copy resume command')}
            size={11}
            className="shrink-0 h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover"
          />
        </div>
      ) : (
        <p className="text-12 text-tertiary leading-relaxed">
          {agent.session_ref
            ? t('Unknown tool. To resume, use the chat id and folder above.')
            : t('Not recorded. Chats started before 2608-19 have only an id.')}
        </p>
      )}
      {tool === 'opencode' && cmd && (
        <p className="text-11 text-tertiary">{t('Flag names vary between OpenCode versions — check `opencode --help` if `--session` is not accepted.')}</p>
      )}
    </div>
  )
}


/**
 * AgentDrillById — the drill for hosts that only know the agent id (the
 * sprint chart). Fetches the agent's meta, and degrades to an id-only agent
 * when the fetch fails.
 */
export function AgentDrillById({ agentId }: { agentId: string }) {
  const read = useQuery({
    queryKey: ['agent', agentId],
    queryFn: ({ signal }) => getJson<AgentDetailAnswer>(`/api/agent/${encodeURIComponent(agentId)}`, signal).catch(refused(null)),
  })
  if (read.isLoading) return null
  // A refused or failed read still offers the drill, on the id alone.
  const a: Partial<AgentRecord> = read.data?.agent ?? {}
  const agent: Agent = {
    id: String(a.agent_id ?? agentId),
    agent_name: String(a.agent_name ?? agentId),
    chat_title: String(a.chat_title ?? ''),
    tool: String(a.tool ?? ''),
    session_ref: String(a.session_ref ?? ''),
    cwd: String(a.cwd ?? ''),
    l1_headline: a.l1_headline ?? null,
    parent_agent_id: a.parent_agent_id ?? null,
    created_date: String(a.created_date ?? ''),
    last_active: a.last_active ?? null,
    message_count: Number(a.message_count) || 0,
    files_touched: Array.isArray(a.files_touched) ? a.files_touched : [],
  }
  return <AgentDrill agent={agent} />
}
