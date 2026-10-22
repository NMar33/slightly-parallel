import { useMemo } from 'react'

import { matches, type Standup, type StandupRow, useStandups } from '../data'
import { dayBefore, inReach, monthOfDay } from '../../daybook/data'

/**
 * The day a standup covers: `for_date` when it says so; an older one names
 * no day and covers the day before it was written.
 */
export function covers(s: Standup): string {
  const forDate = (s.row as { for_date?: string | null }).for_date
  return forDate || dayBefore(s.row.created_date) || s.row.created_date
}

/**
 * The standups filtered by project and find text, keyed by the day each
 * covers. `reach` is the oldest month the feed draws: only this project's
 * standups from there on are read in full. A find reads the whole project
 * in full — it looks through the text.
 */
export function useDayBookEntries(project: string, q: string, reach = '') {
  const want = (r: StandupRow) => r.project === project && (q !== '' || inReach(r.created_date, reach))
  const { standups, loading, error } = useStandups(want)
  const shown = useMemo(
    () => standups.filter((s) => (!project || s.row.project === project) && matches(s, q)),
    [standups, project, q],
  )
  const byDay = useMemo(() => {
    const m = new Map<string, Standup[]>()
    for (const s of shown) {
      const d = covers(s)
      m.set(d, [...(m.get(d) ?? []), s].sort((a, b) => a.at - b.at))
    }
    return m
  }, [shown])
  const months = useMemo(
    () => [...new Set([...byDay.keys()].map(monthOfDay).filter(Boolean))].sort().reverse(),
    [byDay],
  )
  return { standups, shown, byDay, months, loading, error }
}
