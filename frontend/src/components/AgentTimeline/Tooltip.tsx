/**
 * The timeline's hover tooltip: the placement hook (cursor position kept in
 * a ref and painted as a transform inside rAF — mouse moves never touch
 * React state), the positioned layer, and the card itself for a lane, a
 * task-mark cluster or an operator link.
 */

import { useCallback, useEffect, useRef, type MutableRefObject, type RefObject } from 'react'

import { formatStamp } from '../../utils/dateUtils'
import { GROUP_COLOR } from '../../lib/groups'
import type { AgentTimelineProps, TooltipState } from './types'
import { locale, t } from '../../i18n/scope/shell'

/** Tooltip position: written straight to the DOM inside rAF, never state. */
export function useTipPlacement(wrapperRef: RefObject<HTMLDivElement | null>) {
  const tipRef = useRef<HTMLDivElement | null>(null)
  const tipPosRef = useRef({ x: 0, y: 0 })
  const tipRafRef = useRef(0)

  /** Record the cursor position and paint the tooltip's transform on the
   *  next frame — the React tree is untouched. */
  const placeTip = useCallback((evt: { clientX: number; clientY: number }) => {
    const rect = wrapperRef.current?.getBoundingClientRect()
    if (!rect) return
    tipPosRef.current = {
      x: evt.clientX - rect.left + 12,
      y: evt.clientY - rect.top + 12,
    }
    if (tipRafRef.current) return
    tipRafRef.current = requestAnimationFrame(() => {
      tipRafRef.current = 0
      const el = tipRef.current
      if (el) el.style.transform = `translate(${tipPosRef.current.x}px, ${tipPosRef.current.y}px)`
    })
  }, [wrapperRef])

  useEffect(() => () => {
    if (tipRafRef.current) cancelAnimationFrame(tipRafRef.current)
  }, [])

  return { tipRef, tipPosRef, placeTip }
}

/** Hover tooltip (HTML, positioned inside wrapper via transform on a
 *  ref'd element — mouse moves never touch React state) */
export function TooltipLayer({
  tipRef,
  pos,
  state,
  swatch,
}: {
  tipRef: MutableRefObject<HTMLDivElement | null>
  pos: { x: number; y: number }
  state: TooltipState
  swatch?: AgentTimelineProps['markSwatch']
}): JSX.Element {
  return (
    <div
      ref={tipRef}
      className="pointer-events-none absolute left-0 top-0 z-dropdown"
      style={{ transform: `translate(${pos.x}px, ${pos.y}px)` }}
    >
      <Tooltip state={state} swatch={swatch} />
    </div>
  )
}

const KIND_WORD: Record<string, string> = {
  branch: 'branched from',
  subagent: 'spawned subagent',
  handoff: t('handed over to'),
  'same-work': t('same work as'),
  relates: 'relates to',
}

function Tooltip({ state, swatch }: { state: TooltipState; swatch?: AgentTimelineProps['markSwatch'] }): JSX.Element {
  const { agent, cluster, link } = state
  if (link) {
    const { link: lk, from, to } = link
    const fromName = from.agent_name || from.agent_id
    const toName = to.agent_name || to.agent_id
    const when = (s?: string) => formatStamp(s)
    return (
      <div
        role="tooltip"
        className="max-w-[360px] rounded-card border border-border-strong bg-elevated p-12 shadow-lg"
      >
        <div className="text-11 font-mono text-tertiary uppercase tracking-wide mb-4">
          {lk.kind} · {lk.style}
        </div>
        <div className="text-12 text-primary">
          <span className="font-medium">{lk.kind === 'branch' ? toName : fromName}</span>
          <span className="text-tertiary"> {KIND_WORD[lk.kind] ?? lk.kind} </span>
          <span className="font-medium">{lk.kind === 'branch' ? fromName : toName}</span>
        </div>
        {lk.note && (
          <div className="mt-6 text-12 text-secondary leading-relaxed whitespace-pre-line">{lk.note}</div>
        )}
        {(lk.from_at || lk.to_at) && (
          <div className="mt-6 text-10 font-mono text-tertiary">
            {when(lk.from_at)}{lk.from_at && lk.to_at ? ' → ' : ''}{when(lk.to_at)}
          </div>
        )}
        <div className="mt-6 text-10 text-tertiary">{t('Click to edit or remove')}</div>
      </div>
    )
  }
  if (cluster) {
    const when = cluster.at.toLocaleString(locale(), {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
    })
    // One line per task; a task named by both sides in the hour shows once.
    const seen = new Map<string, { title: string; roles: Set<string> }>()
    for (const m of cluster.marks) {
      const e = seen.get(m.task_id) ?? { title: m.title || m.task_id, roles: new Set() }
      e.roles.add(m.role)
      seen.set(m.task_id, e)
    }
    return (
      <div
        role="tooltip"
        className="max-w-[360px] rounded-card border border-border-strong bg-elevated p-12 shadow-lg"
      >
        <div className="mb-4 text-11 font-mono text-tertiary">
          {agent.agent_name || agent.agent_id} · {when}
        </div>
        <ul className="flex flex-col gap-3">
          {[...seen.entries()].map(([id, e]) => {
            const sw = swatch?.(id)
            return (
            <li key={id} className="text-12 text-primary flex items-start gap-6">
              {sw ? <span className="mt-2 shrink-0" aria-hidden>{sw.node}</span> : (
              <span className={e.roles.has('user') ? 'text-status-amber' : 'text-brand'} aria-hidden>
                {e.roles.has('user') ? '◆' : '◇'}
              </span>
              )}
              <span>
                {e.title}
                {sw && <span className="ml-6 text-10 font-mono text-secondary">{sw.label}</span>}
                <span className="ml-6 text-10 font-mono text-tertiary">
                  {e.roles.has('user') && e.roles.has('agent')
                    ? t('handed · replied')
                    : e.roles.has('user') ? 'handed over' : 'reply'}
                </span>
              </span>
            </li>
            )
          })}
        </ul>
        <div className="mt-6 text-10 text-tertiary">{t('click:')} {seen.size === 1 ? t('open the task') : t('open the chat')}</div>
      </div>
    )
  }
  return (
    <div
      role="tooltip"
      className="max-w-[320px] rounded-card border border-border-strong bg-elevated p-12 shadow-lg"
    >
      <div className="mb-4 text-13 font-semibold text-primary">
        {agent.agent_name || agent.agent_id}
      </div>
      <div className="mb-4 font-mono text-11 text-tertiary flex flex-wrap gap-x-8">
        {agent.project && <span>{agent.project}</span>}
        {agent.agent_group && <span>group: {agent.agent_group}</span>}
        {agent.tool && <span>{agent.tool}</span>}
      </div>
      {agent.members && (
        <div className="mb-8 text-12 text-secondary">
          <span style={{ color: GROUP_COLOR }}>group of {agent.members.length}</span>: {agent.members.join(' · ')}
        </div>
      )}
      {agent.l1_headline && (
        <div className="mb-8 text-12 italic text-secondary">
          {agent.l1_headline}
        </div>
      )}
      <div className="flex flex-wrap gap-x-12 gap-y-4 text-11 tabular-nums text-tertiary">
        <span>
          <span className="text-secondary">{t('created')}</span>{' '}
          <span className="font-mono">{agent.created_date}</span>
        </span>
        <span>
          <span className="text-secondary">{t('active')}</span>{' '}
          <span className="font-mono">{agent.last_active}</span>
        </span>
        {typeof agent.message_count === 'number' && (
          <span>
            <span className="text-secondary">{t('msgs')}</span>{' '}
            <span className="font-mono">{agent.message_count}</span>
          </span>
        )}
        {agent.parent_agent_id && (
          <span>
            <span className="text-secondary">{t('parent')}</span>{' '}
            <span className="font-mono">{agent.parent_agent_id}</span>
          </span>
        )}
      </div>
      {agent.cwd && (
        <div className="mt-6 text-10 font-mono text-tertiary break-all">
          <span className="text-secondary">{t('folder')}</span> {agent.cwd}
        </div>
      )}
    </div>
  )
}
