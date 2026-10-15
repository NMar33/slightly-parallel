import { useEffect } from 'react'

import { CalendarTab } from '../features/calendar/CalendarTab'
import { t } from '../i18n/scope/pages'

/** /calendar — the calendar across projects, with a project picker.
 *  The shell draws the header, then the page's guide. */
export default function CalendarPage() {
  useEffect(() => { document.title = `${t('Calendar')} — Slightly Parallel` }, [])
  return (
    <div className="flex flex-col gap-12 min-w-0">
      <CalendarTab />
    </div>
  )
}
