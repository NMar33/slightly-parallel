import { useCallback, useState } from 'react'

import { AgentPanel } from './AgentPanel'
import { ofAgent } from './data'
import { ChatsWorkbench } from './ChatsWorkbench'
import { OutcomePanel } from './OutcomePanel'
import { applyChips, keeps, toggleChip, type ChipId } from './outcome'

/**
 * The chat page — chosen from the Lab on 2026-09-24 (v01), and shared with
 * that variant.
 *
 * The strip of day chips is gone: the month grid is the way into a day, so
 * the room beside it holds two blocks instead. The agents on the left, one
 * to a line, the most talkative first. On the right, what a chat holds:
 * what came out of it, what it came from, and its weight, each chip with
 * the count of the chats it would keep. The band scrolls inside itself, so
 * it never grows past the grid.
 */
export function ChatsPage({ fixedProject }: {
  /** The project's own Chats tab. */
  fixedProject?: string
} = {}) {
  const [picked, setPicked] = useState<ChipId[]>([])
  const sift = useCallback((s: Parameters<typeof keeps>[0]) => keeps(s, picked), [picked])
  return (
    <ChatsWorkbench
      showDays={false}
      fixedProject={fixedProject}
      sift={sift}
      aside={({ ofProject, agents, picked: agentId, onPick }) => {
        // The counts are of this project's chats with the picked agent's, if
        // one is picked — the base the chips cut into.
        const base = agentId ? ofProject.filter((s) => ofAgent(s, agentId)) : ofProject
        return (
          <div className="grid gap-12 min-w-0 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] h-[152px]">
            <AgentPanel agents={agents} picked={agentId} onPick={onPick} />
            <OutcomePanel
              rows={base}
              picked={picked}
              left={applyChips(base, picked).length}
              onToggle={(id) => setPicked((p) => toggleChip(p, id))}
              onClear={() => setPicked([])}
            />
          </div>
        )
      }}
    />
  )
}
