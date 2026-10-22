import { useMemo, useState } from 'react'

import { Input } from '../../components/primitives'
import { fmtDay } from '../agents/parts'
import { GROUP_COLOR } from '../../lib/groups'
import { STAR_COLOR, useMarks } from '../../lib/marks'

import { t } from '../../i18n/scope/views'
/** One agent as the panel lists it: who, where, and how much was said. */
export interface AgentLine {
  id: string
  /** The short name a mention shows. */
  label: string
  /** The long name, for the tooltip. */
  title: string
  project: string
  chats: number
  turns: number
  /** The day of the newest chat, YYMM-DD. */
  last: string
  /** Set on a group's line: how many of its agents are here. */
  group?: number
}

/**
 * The agents, to pick one by.
 *
 * It stands beside the calendar, so the two together cost one band of the
 * page instead of two. One agent to a line — the most talkative first, with
 * its chats, its turns and the day it was last active — and the list
 * scrolls inside a fixed height, so a hundred agents take the same room as
 * ten. The box finds one by name, which is the only way through a long list.
 */
export function AgentPanel({ agents, picked, onPick }: {
  agents: AgentLine[]
  picked: string
  onPick: (id: string) => void
}) {
  const [find, setFind] = useState('')
  const needle = find.trim().toLowerCase()
  const starred = useMarks().has
  // Groups first, then the important agents, then the rest as they came.
  const shown = useMemo(() => {
    const found = needle
      ? agents.filter((a) => `${a.label} ${a.title} ${a.id} ${a.project}`.toLowerCase().includes(needle))
      : agents
    const rank = (a: AgentLine) => (a.group != null ? 0 : starred('agent', a.id) ? 1 : 2)
    return found.map((a, i) => [a, i] as const).sort((x, y) => rank(x[0]) - rank(y[0]) || x[1] - y[1]).map(([a]) => a)
  }, [agents, needle, starred])

  return (
    <section aria-label={t('Agents')} className="rounded-card border border-border-subtle bg-surface flex flex-col min-h-0 h-full">
      <div className="flex items-center gap-8 px-10 py-6 border-b border-border-subtle">
        <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('Agents')}</span>
        <span className="text-11 font-mono text-tertiary tabular">{shown.length}{needle ? ` of ${agents.length}` : ''}</span>
        {picked && (
          <button type="button" onClick={() => onPick('')}
            className="text-10 font-mono text-brand hover:underline">
            {t('every agent')}
          </button>
        )}
        <Input value={find} onChange={(e) => setFind(e.target.value)} placeholder={t('Find an agent')}
          aria-label={t('Find an agent')} className="ml-auto w-[140px] h-20 text-11" />
      </div>
      <ul className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-1 p-6">
        {shown.length === 0 && (
          <li className="text-11 font-mono text-tertiary px-4 py-2">{t('No agent matches.')}</li>
        )}
        {shown.map((a) => {
          const on = a.id === picked
          return (
            <li key={a.id}>
              <button type="button" onClick={() => onPick(on ? '' : a.id)} aria-pressed={on}
                title={t('{title} · {project} · {chats} chats · {turns} turns', { title: a.title, project: a.project, chats: a.chats, turns: a.turns })}
                className={`w-full text-left rounded-input px-8 py-3 flex items-baseline gap-6 ${on ? 'bg-brand-glow' : 'hover:bg-hover'}`}>
                <span className={`text-12 leading-snug truncate ${a.group != null ? 'font-semibold' : on ? 'text-primary' : 'text-secondary'}`}
                  style={a.group != null ? { color: GROUP_COLOR } : undefined}>
                  {starred('agent', a.id) && <span role="img" style={{ color: STAR_COLOR }} aria-label={t('important')}>★ </span>}
                  {a.label}{a.group != null && <span className="font-normal text-10 font-mono"> {t('· group of')}{' '}{a.group}</span>}
                </span>
                <span className="ml-auto shrink-0 text-10 font-mono text-tertiary tabular">
                  {a.turns}{t('t ·')}{' '}{fmtDay(a.last)}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
