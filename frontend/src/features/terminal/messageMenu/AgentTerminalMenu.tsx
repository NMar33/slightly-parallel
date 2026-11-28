import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { ChevronRight, CornerDownRight, SquareTerminal } from 'lucide-react'

import { t } from '../../../i18n/scope/msgmenu'
import { agentTerminals, isAgentMention, requestAgentTerminal, useDashboardAgentMenus } from '../../aqua/app/agentTerminals'
import { useSessions } from '../../aqua/app/api'
import { useTabInfo } from '../../aqua/app/tabs/facts'
import { place, useFirstFocus } from './pop'

const goLabel = () => t("Go to agent's terminal")
const pageRow = 'flex items-center gap-8 w-full min-h-28 rounded-input px-8 py-4 text-left hover:bg-hover focus-visible:bg-hover'

export function AgentTerminalActions({ agent, close, row = 'lab-list-row' }: {
  agent: string; close: () => void; row?: string
}) {
  const { sessions, loaded } = useSessions()
  const tabs = useTabInfo()
  const choices = agentTerminals(agent, sessions, tabs)
  const [expanded, setExpanded] = useState(false)
  const firstChoice = useRef<HTMLDivElement>(null)
  useEffect(() => { if (expanded) firstChoice.current?.querySelector('button')?.focus() }, [expanded])

  const select = (tab?: string) => {
    close()
    requestAgentTerminal(agent, tab)
  }
  if (!loaded) return <button type="button" role="menuitem" className={row} disabled>{goLabel()}</button>
  if (choices.length <= 1) return (
    <button type="button" role="menuitem" className={row} onClick={() => select(choices[0]?.id)}>
      <SquareTerminal size={15} aria-hidden />
      {choices.length ? goLabel() : t("Open / resume agent's terminal")}
    </button>
  )
  return (
    <>
      <button type="button" role="menuitem" aria-haspopup="menu" aria-expanded={expanded} className={row}
        onClick={() => setExpanded((open) => !open)}>
        <SquareTerminal size={15} aria-hidden />
        {goLabel()}
        <ChevronRight className="ml-auto" size={14} aria-hidden />
      </button>
      {expanded && <div ref={firstChoice} role="menu" aria-label={goLabel()} className="ml-10 pl-4 border-l border-border-subtle">
        {choices.map((choice) => (
          <button key={choice.id} type="button" role="menuitem" className={row}
            title={choice.project || undefined} onClick={() => select(choice.id)}>
            <CornerDownRight size={13} aria-hidden />
            <span className="truncate">{choice.label || choice.id}</span>
          </button>
        ))}
      </div>}
    </>
  )
}

/** Use an agent mention's existing text as the trigger on the native dashboard. */
export function DashboardAgentMention({ agent, label, className, fallback, extra }: {
  agent: string; label: string; className?: string; fallback: ReactNode; extra?: ReactNode
}) {
  const dashboard = useDashboardAgentMenus()
  const [at, setAt] = useState<{ x: number; y: number } | null>(null)
  const trigger = useRef<HTMLSpanElement>(null)
  const box = useRef<HTMLDivElement>(null)
  useFirstFocus(box, at)
  useEffect(() => {
    if (!at) return
    const outside = (event: PointerEvent) => {
      const target = event.target as Node
      if (!box.current?.contains(target) && !trigger.current?.contains(target)) setAt(null)
    }
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.stopPropagation()
      setAt(null)
      trigger.current?.focus()
    }
    window.addEventListener('pointerdown', outside, true)
    window.addEventListener('keydown', key, true)
    return () => {
      window.removeEventListener('pointerdown', outside, true)
      window.removeEventListener('keydown', key, true)
    }
  }, [at])
  if (!dashboard || !isAgentMention(agent)) return fallback

  const open = () => {
    const rect = trigger.current?.getBoundingClientRect()
    if (rect) setAt({ x: rect.left, y: rect.bottom + 4 })
  }
  return (
    <>
      <span ref={trigger} role="button" tabIndex={0} title={agent} aria-haspopup="menu" aria-expanded={!!at}
        data-agent-terminal={agent} className={`cursor-pointer hover:underline ${className ?? ''}`}
        onClick={(event) => { event.preventDefault(); event.stopPropagation(); open() }}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          event.stopPropagation()
          open()
        }}>{label}</span>
      {at && createPortal(
        <div ref={box} role="menu" aria-label={label}
          className="fixed z-[100] rounded-input border border-border-subtle bg-base p-4 text-12 text-primary shadow-lg"
          style={place(at.x, at.y, 272, 168, window.innerWidth, window.innerHeight)}
          onClick={(event) => event.stopPropagation()}>
          <AgentTerminalActions agent={agent} close={() => setAt(null)} row={pageRow} />
          {extra && <div className="border-t border-border-subtle mt-4 pt-4" onClick={() => setAt(null)}>{extra}</div>}
        </div>, document.body)}
    </>
  )
}
