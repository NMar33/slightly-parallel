import { useEffect, type ReactNode } from 'react'
import { IMPORTANT_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { Link } from 'react-router-dom'
import { Star } from 'lucide-react'

import { PageHeader } from '../components/PageHeader'
import { StarButton } from '../components/StarButton'
import { EmptyState, LoadingSkeleton } from '../components/states'
import { useMarks, useMarkToggle, type Mark } from '../lib/marks'
import { projectColor } from '../utils/projectColor'
import { mentionLabel } from '../features/project/mentions'
import { t } from '../i18n/scope/pages'

import { rich } from '../i18n/rich'
import { dayMonth } from '../lib/months'
/**
 * /important — everything the operator starred, in one place: the messages,
 * the agents and the tasks, newest first. Each row opens what it points at
 * (the chat on that turn, the agent's page, the task on its board); the ★
 * takes the star off. Stars come from #important in a chat, or by hand.
 */

function when(at: string): string {
  if (!at) return ''
  const d = new Date(at)
  return Number.isFinite(d.getTime())
    ? dayMonth(d) + ' ' + d.toTimeString().slice(0, 5)
    : ''
}

const agentName = (m: Mark) => mentionLabel({ agent_id: m.kind === 'agent' ? m.target : m.agent_id, agent: m.agent })

export default function ImportantPage() {
  useEffect(() => { document.title = `${t('Important')} — Slightly Parallel` }, [])
  const { marks, loading } = useMarks()
  const toggle = useMarkToggle()
  const of = (k: Mark['kind']) => marks.filter((m) => m.kind === k)
  const messages = of('message'), agents = of('agent'), tasks = of('task')

  return (
    <div className="flex flex-col gap-24 min-w-0">
      <PageHeader variant="lens" icon={Star} title={t('Important')} count={loading ? '' : marks.length} />
      <PageGuide id="important" guide={IMPORTANT_GUIDE} examples={0} />
      {loading && <LoadingSkeleton variant="card" count={2} />}
      {!loading && marks.length === 0 && (
        <EmptyState
          title={t('Nothing is marked important yet.')}
          subtitle={<>{rich(t('When you type `#important` in a chat, the message, its agent and the task it names appear here. `#important-agent`, `#important-task` and `#important-message` mark one of them.'))}</>}
        />
      )}
      {!loading && marks.length > 0 && (
        <>
          <Section name={t('Messages')} n={messages.length} none={t('No message is marked.')}>
            {messages.map((m) => (
              <Row key={m.id} m={m} onUnstar={() => toggle(false, 'message', m.target)}
                to={`/chats#project=${encodeURIComponent(m.project)}&agent=${encodeURIComponent(m.agent_id)}&sel=${encodeURIComponent(m.session_id)}&turn=${m.turn}`}
                title={m.excerpt || t('turn {n}', { n: m.turn })} meta={`${agentName(m)} · ${t('turn {n}', { n: m.turn })}`} />
            ))}
          </Section>
          <Section name={t('Agents')} n={agents.length} none={t('No agent is marked.')}>
            {agents.map((m) => (
              <Row key={m.id} m={m} onUnstar={() => toggle(false, 'agent', m.target)}
                to={`/agent/${encodeURIComponent(m.target)}`}
                title={agentName(m)} meta={m.excerpt ? `“${m.excerpt}”` : m.target} />
            ))}
          </Section>
          <Section name={t('Tasks')} n={tasks.length} none={t('No task is marked.')}>
            {tasks.map((m) => (
              <Row key={m.target} m={m} onUnstar={() => toggle(false, 'task', m.target)}
                to={`/project/${encodeURIComponent(m.task?.project || m.project)}#tasks&task=${encodeURIComponent(m.target)}`}
                title={m.task?.title || m.target} meta={m.task?.status || ''} />
            ))}
          </Section>
        </>
      )}
    </div>
  )
}

function Section({ name, n, none, children }: { name: string; n: number; none: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-6 min-w-0" aria-label={name}>
      <h2 className="text-14 font-semibold text-primary flex items-baseline gap-8">
        {name} <span className="text-11 font-mono text-tertiary tabular">{n}</span>
      </h2>
      {n === 0
        ? <p className="text-12 text-tertiary">{none}</p>
        : <ul className="rounded-card border border-border-subtle bg-surface divide-y divide-border-subtle">{children}</ul>}
    </section>
  )
}

function Row({ m, to, title, meta, onUnstar }: { m: Mark; to: string; title: string; meta: string; onUnstar: () => void }) {
  const project = m.task?.project || m.project
  return (
    <li className="flex items-center gap-10 px-10 py-6 min-w-0">
      <StarButton on what="it" onToggle={() => onUnstar()} />
      <Link to={to} className="min-w-0 flex-1 flex flex-col hover:text-brand">
        <span className="text-13 text-primary truncate">{title}</span>
        <span className="text-11 font-mono text-tertiary truncate">{meta}</span>
      </Link>
      {project && (
        <span className="shrink-0 inline-flex items-center gap-4 text-11 font-mono text-tertiary">
          <span className="w-6 h-6 rounded-pill" style={{ background: projectColor(project) }} aria-hidden />{project}
        </span>
      )}
      <span className="shrink-0 w-[96px] text-right text-11 font-mono text-tertiary tabular">{when(m.marked_at)}</span>
    </li>
  )
}
