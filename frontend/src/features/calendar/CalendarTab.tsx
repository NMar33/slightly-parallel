import { Suspense, lazy } from 'react'

import { LoadingSkeleton } from '../../components/states'
import { useHashState } from '../../hooks/useHashState'
import type { CalendarView } from './parts'

import { t } from '../../i18n/scope/views'
const MonthPage = lazy(() => import('../../pages/CalendarMonthPage'))
const WeekPage = lazy(() => import('../../pages/CalendarWeekPage'))
const LadderPage = lazy(() => import('../../pages/MilestonesLadderPage'))

/** The calendar's views. */
const PRODUCT_VIEWS: CalendarView[] = [
  { key: 'month', label: t('month'), hint: t('One month') },
  { key: 'week', label: t('week'), hint: t('One week, with the work done each day') },
  { key: 'milestones', label: t('milestones'), hint: t('Milestones in order of their target date') },
]

/**
 * The calendar as the product: month by default, week or milestones on request, the
 * choice in the hash (`view=week`) beside the page's own state. On the
 * project page the project is fixed and the page's chrome stays out of
 * the way; on /calendar there is a project picker.
 */
export function CalendarTab({ projectCode }: { projectCode?: string }) {
  const [hash, setHash] = useHashState()
  const view = hash.view === 'week' || hash.view === 'milestones' ? hash.view : 'month'
  const props = {
    projectCode,
    embedded: !!projectCode,
    views: PRODUCT_VIEWS,
    onView: (v: string) => setHash({ view: v === 'month' ? '' : v }),
  }
  return (
    <Suspense fallback={<LoadingSkeleton variant="card" count={2} />}>
      {view === 'week' ? <WeekPage {...props} /> : view === 'milestones' ? <LadderPage {...props} /> : <MonthPage {...props} />}
    </Suspense>
  )
}
