/**
 * F's lineage, narrowed for the right sidebar: the chat, the tasks it
 * spawned (nested by the board's parent links), the background agents, the
 * chats work was forked to (nested under the task that forked them, with
 * their own tasks), the tasks made from messages, and the messages queued
 * to fork later with a button that hands them to an agent.
 */

import type { ReactNode } from 'react'
import { Bot, GitFork, Play } from 'lucide-react'

import { t } from '../../../../i18n/scope/aqua'
import { MESSAGES, TASKS, sessionOf, type Task } from '../mock'
import { StateDot, shownState, STATE_WORD } from '../parts'
import { flash, toggleForkLater, useAqua } from '../store'

const STATUS: Record<Task['status'], string> = { todo: 'var(--aq-ink3)', doing: 'var(--aq-accent)', done: 'var(--aq-up)' }

function Row({ depth, children }: { depth: number; children: ReactNode }) {
  return (
    <li className="list-none relative" style={{ paddingLeft: depth * 14 }}>
      {depth > 0 && <span aria-hidden className="absolute top-0 bottom-0" style={{ left: depth * 14 - 8, borderLeft: '1.5px solid var(--aq-line)' }} />}
      {children}
    </li>
  )
}

export function LineageTree({ chat, onChat, seen = new Set<string>() }: { chat: string; onChat: (id: string) => void; seen?: Set<string> }) {
  const st = useAqua()
  const s = sessionOf(chat)!
  const tasks = TASKS.filter((x) => x.from === chat && x.chat !== chat)
  const top = tasks.filter((x) => !x.parent || !tasks.some((y) => y.id === x.parent))
  const queued = MESSAGES.filter((m) => m.session === chat && st.forkLater[m.id])
  const made = Object.entries(st.tasked).filter(([mid, tk]) => MESSAGES.find((m) => m.id === mid)?.session === chat && !TASKS.some((x) => x.id === tk))
  const k = shownState(st, s)
  seen.add(chat)

  const task = (x: Task, depth: number): ReactNode => {
    const forked = x.chat && x.chat !== chat && !seen.has(x.chat) ? x.chat : null
    return (
      <Row key={x.id} depth={depth}>
        <div className="flex items-center gap-6 h-[24px] text-12 min-w-0">
          <span className="w-[8px] h-[8px] rounded-[2px] shrink-0" style={{ background: STATUS[x.status] }} />
          <span className="truncate" style={{ color: 'var(--aq-ink)' }} title={x.title}>{x.title}</span>
          {x.via === 'background agent' && <Bot size={11} className="aq-ink3 shrink-0" aria-label={t('background agent')} />}
          <span className="ml-auto text-10 font-mono aq-ink3 shrink-0">{x.status}</span>
        </div>
        <ul className="m-0 p-0">
          {tasks.filter((y) => y.parent === x.id).map((y) => task(y, 1))}
          {forked && <Row depth={1}><LineageTree chat={forked} onChat={onChat} seen={seen} /></Row>}
        </ul>
      </Row>
    )
  }

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <button type="button" className="aq-row px-6 h-[28px]" onClick={() => onChat(chat)} title={STATE_WORD[k]}>
        <StateDot s={s} st={st} /><b className="text-12 truncate" style={{ color: 'var(--aq-ink)' }}>{s.name}</b>
        <span className="ml-auto text-10 font-mono aq-ink3">{STATE_WORD[k]}</span>
      </button>
      <ul className="m-0 p-0 pl-6">
        {top.map((x) => task(x, 1))}
        {s.bg.filter((b) => !b.done).map((b) => (
          <Row key={b.label} depth={1}><div className="flex items-center gap-6 h-[24px] text-12 aq-ink2"><Bot size={11} />{b.label}</div></Row>
        ))}
        {made.map(([mid, tk]) => (
          <Row key={tk} depth={1}><div className="flex items-center gap-6 h-[24px] text-12"><span className="w-[8px] h-[8px] rounded-[2px]" style={{ background: STATUS.todo }} />
            <span className="truncate">{MESSAGES.find((m) => m.id === mid)?.text}</span><span className="aq-chip ml-auto">{tk}</span></div></Row>
        ))}
        {queued.map((m) => (
          <Row key={m.id} depth={1}>
            <div className="flex items-center gap-6 my-2 px-6 py-4 rounded-[6px] text-12" style={{ border: '1.5px dashed var(--aq-fork)' }}>
              <GitFork size={11} style={{ color: 'var(--aq-fork)' }} className="shrink-0" />
              <span className="truncate flex-1" style={{ color: 'var(--aq-ink2)' }}>{m.text}</span>
              <button type="button" className="aq-btn line shrink-0" onClick={() => { toggleForkLater(m.id); flash(t('Handed to a new agent with the chat\'s briefing')) }}><Play size={11} />{t('Hand to an agent')}</button>
            </div>
          </Row>
        ))}
      </ul>
    </div>
  )
}
