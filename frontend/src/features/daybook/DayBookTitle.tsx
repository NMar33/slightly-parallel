import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { Input } from '../../components/primitives'
import { PageHeader } from '../../components/PageHeader'
import { ProjectPills } from '../../components/ProjectPills'

import { t } from '../../i18n/scope/views'
/**
 * The one title row of a day book: the icon and the name, how many entries
 * are on show, the find box, and — under them — the project.
 *
 * Scans, standups and decisions are the same page with different entries,
 * so they introduce themselves the same way. A page adds only what is its
 * own, in `right`: the scans page puts its folded / open switch there.
 *
 * The project picker offers no "All": a day book draws one project's month,
 * and a month of every project at once belongs to nobody. It lists every
 * project, the ones with an entry first, and hides only when there is one.
 */
export function DayBookTitle({
  icon: Icon, name, count, projects, project, onProject, q, onFind, right,
}: {
  icon: LucideIcon
  /** The page's name, plural: Scans, Standups, Decisions. */
  name: string
  /** The entries on show, after the project and the find text. */
  count: number
  /** The projects: those with an entry, newest first, then the rest. */
  projects: string[]
  project: string
  onProject: (project: string) => void
  q: string
  onFind: (q: string) => void
  /** What this page adds to the row. */
  right?: ReactNode
}) {
  const find = t('Find in {v}', { v: name.toLowerCase() })
  return (
    <PageHeader
      variant="lens" icon={Icon} title={name} count={count}
      actions={<>
        {right}
        <Input value={q} onChange={(e) => onFind(e.target.value)} placeholder={find}
          aria-label={find} className="w-[220px] h-24 text-12" />
      </>}
      below={projects.length > 1 ? <ProjectPills projects={projects} value={project} dots onPick={(c) => c && onProject(c)} /> : undefined}
    />
  )
}
