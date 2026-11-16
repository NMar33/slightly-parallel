import type { CoreDetail } from '../data'

/** What every way of showing one core is given. The band above it (name,
 *  type, tracking, edit, remove) is CorePage's; a body draws the rest. */
export interface CoreBodyProps {
  projectCode: string
  core: CoreDetail
  show: 'everyone' | 'operator'
  /** Opens a linked task in the task window, in place. */
  onOpenTask: (id: string) => void
  /** Opens the task window for a new task of this core. */
  onNewTask: () => void
}

export type CoreBodyName = 'pages' | 'story' | 'thread' | 'sheet' | 'compare' | 'code' | 'pulse'
