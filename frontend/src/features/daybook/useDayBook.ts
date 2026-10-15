import { useMemo } from 'react'

import { useHashState } from '../../hooks/useHashState'
import { daysOfMonth, monthKey, monthOfDay, useMonth } from './data'

/**
 * What every day book needs: the project, the find text, the month on
 * show, the picked day, and the month's numbers. The page adds only what
 * its own entries are.
 *
 * A day book reads one project at a time: the month band and the day's
 * numbers are that project's own, so "all projects" would draw a month
 * that belongs to nobody. `known` is the projects that have an entry; the
 * page shows the one in the address, else the first of those.
 *
 * The month lives in the address beside the project and the day, so a
 * month someone paged back to survives a reload and can be sent to
 * somebody else. An address with no month means this month.
 *
 * No project known yet (the list is still loading) reads as none: the
 * month's numbers wait for one instead of asking for a project name that
 * may not exist here.
 */
export function useDayBook(known: string[] = [], fallback = '') {
  const [hash, setHash] = useHashState()
  const q = (hash.q ?? '').trim()
  const project = (hash.project && known.includes(hash.project) ? hash.project : '')
    || known[0] || fallback
  const month = hash.month || monthKey()
  const active = hash.day ?? ''
  const cal = useMonth(project, month)
  const days = cal.data?.days ?? {}
  const keys = useMemo(() => daysOfMonth(month).reverse(), [month])

  const pick = (day: string) => {
    const of = monthOfDay(day)
    setHash(of && of !== month ? { day, month: of } : { day })
    requestAnimationFrame(() => document.getElementById(`day-${day}`)?.scrollIntoView({ block: 'start' }))
  }
  const showMonth = (next: string) => setHash({ month: next, day: '' })

  return { hash, setHash, q, project, month, showMonth, active, days, keys, pick }
}
