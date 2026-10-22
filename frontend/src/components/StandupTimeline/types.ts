/**
 * Types for the Standup Timeline (list view with per-row drill).
 *
 * Mirrors `backend/models.py::StandupRow` + `StandupDetail`. L1 is the
 * one-sentence day summary (always present in the index); L2/L3/L4 are
 * hydrated lazily from `/api/standups/{id}`:
 *   L2 = "since last standup" prose
 *   L3 = open-goal bullet lines
 *   L4 = today's plan (goal focus, time budget, blockers)
 */

export interface StandupRow {
  id: string
  created_date: string // YYMM-DD
  created_time?: string // HH:MM
  project: string // may be "_all" for cross-project standups
  agent_id: string | null // null when operator-authored
  l1: string
  goals_open_n: number
  goals_closed_n: number
  blockers_n: number
  hours_today: number
  md_ref?: string
}

export interface StandupsListResponse {
  total: number
  standups: StandupRow[]
}

export interface StandupDetail {
  metadata: StandupRow
  /** "Since last standup" prose. */
  l2: string
  /** Open-goal bullet lines. */
  l3: string[]
  /** Today's plan prose (multi-paragraph string). */
  l4: string
}

export type FetchStandupDetail = (
  id: string,
  signal?: AbortSignal,
) => Promise<StandupDetail>
