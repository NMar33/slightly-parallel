import type { Deck, useDeck } from './deck'

/**
 * What a sprints view is handed. The page shell owns the header, the range
 * and the single read of the deck; a view renders a body and nothing else,
 * so switching between them cannot move a control or change a range.
 */
export type ViewProps = {
  deck: Deck | null
  err: boolean
  nowMs: number
  refresh: () => void
  actions: ReturnType<typeof useDeck>['actions']
  range: 7 | 30
}

/** The fleet-wide facts the header states, whichever view is showing. */
export function fleetTotals(deck: Deck | null) {
  const bs = deck?.blocks ?? []
  return {
    human: bs.reduce((a, b) => a + b.human_min, 0),
    agent: bs.reduce((a, b) => a + b.agent_min, 0),
    open: bs.reduce((a, b) => a + (b.tasks_total - b.tasks_done), 0),
    today: bs.reduce((a, b) => a + b.today_n, 0),
    running: bs.filter((b) => b.timer && !b.timer.paused_at).length,
    landed: bs.reduce((a, b) => a + b.tasks_done, 0),
  }
}
