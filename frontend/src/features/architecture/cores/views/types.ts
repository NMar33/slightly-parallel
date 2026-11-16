import type { CoreSummary } from '../data'

/** What every view of the cores page is given: the project, its cores (in
 *  view and out of view, as GET /api/cores answers), whose notes to show,
 *  and how to open one core (the page then shows CorePage). */
export interface CoreViewProps {
  projectCode: string
  cores: CoreSummary[]
  show: 'everyone' | 'operator'
  onOpen: (id: string) => void
}

export type CoreViewName = 'tiles' | 'roadmap' | 'map'
