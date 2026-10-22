/**
 * What the board hands its two grids (swim lanes, plain columns). The
 * board owns every piece of state; the grids only draw it and call back.
 * Kept here so the grids never import TasksKanban.tsx.
 */

import type { ReactNode, RefObject } from 'react'
import type { Axis, Glow, LinkInfo, MentionSummary, SortMode, TaskRow } from '../model'

type BoardColumn = { key: string; label: string; className?: string; strip?: boolean }

/** The lane view's cells, the per-lane totals and the Today band's groups. */
export type ByLaneCol = {
  cells: Map<string, TaskRow[]>
  laneN: Map<string, number>
  todayCols: Map<string, TaskRow[]>
}

/** The link and hover wiring every render of a card gets (the board's linkProps). */
type LinkWiring = {
  onImportant: (t: TaskRow, next: boolean) => void
  link: LinkInfo | undefined
  linksMode: boolean
  armed: boolean
  glow: Glow | undefined
  shadow: boolean
  onHover: ((id: string, on: boolean) => void) | undefined
  onArm: (id: string) => void
  onTarget: ((id: string) => void) | undefined
  onOpenTask: (id: string) => void
}

export type GridProps = {
  gridRef: RefObject<HTMLDivElement>
  columns: BoardColumn[]
  openStrips: Record<string, boolean>
  showArchiveCol: boolean
  showArchived: boolean
  tasksByStatus: Record<string, TaskRow[]>
  toggleStrip: (key: string) => void
  handleDrop: (draggedId: string, targetStatus: string, targetLane?: string, beforeTaskId?: string | null, force?: boolean) => void
  copyMode: boolean
  sorts: Record<string, SortMode>
  setSort: (col: string, mode: SortMode) => void
  setAddingStatus: (status: string | null) => void
  archivedN: number
  toggleArchived: () => void
  todayTasks: TaskRow[]
  byLaneCol: ByLaneCol
  handleDropToday: (draggedId: string, colKey: string, lane?: string) => void
  toggleToday: (task: TaskRow) => Promise<void>
  linkProps: (task: TaskRow, shadow?: boolean) => LinkWiring
  multi: boolean
  axes: Record<Axis, boolean>
  onCardToday: (t: TaskRow) => void
  onCardEdit: (t: TaskRow) => void
  onCardRelease: (t: TaskRow) => void
  showDesc: boolean
  today: string
  selection: string[]
  toggleSelect: (id: string) => void
  tasks: TaskRow[]
  openStacks: Set<string>
  toggleStack: (sid: string) => void
  mentions: Record<string, MentionSummary>
  noteCounts: Record<string, number>
  evidenceCounts: Record<string, number>
  statusSince: Record<string, string>
  archivedTasks: TaskRow[]
  /** The links overlay, drawn inside the grid so lines scroll with the cards. */
  linksLayer: ReactNode
}

export type LanesGridProps = GridProps & {
  lanes: string[]
  collapsedLanes: Set<string>
  toggleLane: (lane: string) => void
  renameLane: (oldName: string, newName: string) => Promise<void>
  deleteLane: (name: string) => void
  moveLaneBefore: (lane: string, target: string) => void
  allCollapsed: boolean
  collapseAll: () => void
  addingLane: boolean
  setAddingLane: (v: boolean) => void
  laneDraft: string
  setLaneDraft: (v: string) => void
  commitAddLane: () => void
  setAddingAssignee: (v: string | null) => void
}

export type ColumnsGridProps = GridProps & {
  doneLimit: number
  doneExpanded: boolean
  setDoneExpanded: (v: boolean) => void
}
