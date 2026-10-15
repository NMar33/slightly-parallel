/**
 * Types for the C12 Decision Log.
 *
 * Mirrors the `decisions.csv` schema in architecture.md §4.1:
 *   id, decision_text, rationale, source, agent_id, related_goal_id, tags, created_date
 *
 * `project` is added by the backend when serving cross-project payloads
 * (`/api/decisions`). It is the project code (e.g. "WT", "quizforge").
 */
export type DecisionSource = 'explicit' | 'auto'

export interface Decision {
  id: string
  decision_text: string
  rationale: string
  source: DecisionSource
  agent_id: string
  related_goal_id?: string | null
  tags?: string[]
  created_date: string // YYMM-DD
  project?: string // present in cross-project responses
}
