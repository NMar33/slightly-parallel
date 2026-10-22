/*
 * The calendar's frame: the title, the project or board picker and the
 * switch between its views. The views draw inside it.
 */
import { useEffect, useMemo, type ReactNode } from 'react'
import { CalendarDays } from 'lucide-react'

import { PageHeader } from '../../components/PageHeader'
import { ProjectPills, type ProjectPillOption } from '../../components/ProjectPills'
import { Segmented } from '../../components/Segmented'
import { CALENDAR_GUIDE } from '../visions/guides'
import { PageGuide } from '../visions/parts'
import { useBoards, useProjectCodes, type Scope } from './data'
import { ProjectDot } from './pills'

import { t } from '../../i18n/scope/views'
export interface CalendarView { key: string; label: string; hint: string }

/** What a calendar view takes from the calendar (CalendarTab): the project
 *  from the route, whether it sits inside another page, and the view switch. */
export interface CalendarPageProps {
  /** Fixed project (the project tab); absent → the hash's `project`. */
  projectCode?: string
  /** Inside another page: no heading, no project picker, no title change. */
  embedded?: boolean
  /** The switch's entries. */
  views: CalendarView[]
  onView: (key: string) => void
}

export function CalendarShell({ view, scope, onScope, right, children, tally, embedded = false, views, onView }: {
  view: string
  scope: Scope
  onScope: (value: string) => void
  /** Right side of the title row: the range nav, the search. */
  right?: ReactNode
  /** One mono line under the title: counts for the range. */
  tally?: string
  children: ReactNode
  embedded?: boolean
  views: CalendarView[]
  onView: (key: string) => void
}) {
  const known = useProjectCodes()
  const boards = useBoards()
  // Every code the picker should offer: the project folders, plus codes a
  // standalone board writes under before its folder exists.
  const codes = useMemo(() => {
    const out = [...known]
    for (const b of boards) for (const c of b.projects) if (!out.includes(c)) out.push(c)
    for (const c of scope.codes) if (!out.includes(c)) out.push(c)
    return out.sort()
  }, [known, boards, scope.codes])
  useEffect(() => {
    if (!embedded) document.title = t('Calendar · {label} — Slightly Parallel', { label: scope.label })
  }, [scope.label, embedded])
  const viewSwitch = (
    <Segmented label={t('View')} value={view} onChange={onView} options={views.map((v) => [v.key, v.label, v.hint] as const)} />
  )
  const tallyText = tally && <span className="text-11 font-mono text-tertiary tabular whitespace-nowrap">{tally}</span>
  if (embedded) {
    return (
      <div className="flex flex-col gap-12 min-w-0">
        <div className="flex items-center gap-12 flex-wrap min-w-0">
          {viewSwitch}
          {tallyText}
          <div className="ml-auto flex items-center gap-8 min-w-0">{right}</div>
        </div>
        {children}
      </div>
    )
  }
  // The scope: every project, one project, or a saved board.
  const savedBoards = boards.filter((b) => !b.standalone)
  const listed = ['', ...codes, ...boards.map((b) => `board:${b.id}`)]
  const scopeOptions: ProjectPillOption[] = [
    ...codes.map((c) => ({ code: c })),
    ...savedBoards.map((b) => ({ code: `board:${b.id}`, text: b.name, count: b.projects.length, noDot: true, hint: t('Saved board: {v}', { v: b.projects.join(', ') }) })),
    ...(!listed.includes(scope.value === 'all' ? '' : scope.value) ? [{ code: scope.value, text: scope.label, noDot: true }] : []),
  ]
  return (
    <div className="flex flex-col gap-12 min-w-0">
      <PageHeader
        variant="lens" icon={CalendarDays} title={t('Calendar')} count={tally}
        actions={right}
        below={(
          <div className="flex items-center gap-8 flex-wrap min-w-0">
            <ProjectPills projects={scopeOptions} value={scope.value === 'all' ? '' : scope.value} all={{}} dots
              onPick={(v) => onScope(v || 'all')} />
            {scope.value.startsWith('board:') && scope.codes.length > 0 && (
              <span className="inline-flex items-center gap-4" aria-label={t('Projects in view')}>
                {scope.codes.map((c) => <ProjectDot key={c} code={c} />)}
              </span>
            )}
          </div>
        )}
      >
        {viewSwitch}
      </PageHeader>
      <PageGuide id="calendar" guide={CALENDAR_GUIDE} examples={0} />
      {children}
    </div>
  )
}
