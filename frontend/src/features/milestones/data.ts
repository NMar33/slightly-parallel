/**
 * Milestones as their own feature — the ladder above the tasks.
 *
 * The rows are the calendar's milestone rows (one ledger, one API); this
 * layer adds what a ladder page needs: the project's reason, templates a
 * new ladder starts from, and the derived reading of each step — how far,
 * how many tasks stand between, whether it slips.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { daysBetween, isDone, isoToday, type CalTask, type Milestone } from '../calendar/model'
import { useCalendarWrites } from '../calendar/data'
import { getJson, postJson } from '../../lib/getJson'


import { t, tn } from '../../i18n/scope/views'
export type ReasonKind = 'attention' | 'money' | 'time' | 'learning' | 'other'
interface Reason { project: string; kind: ReasonKind | ''; text: string; updated_at: string }

export const REASON_KINDS: Array<{ key: ReasonKind; label: string; hint: string }> = [
  { key: 'attention', label: t('attention'), hint: t('people find it, read it, star it, talk about it') },
  { key: 'money', label: t('money'), hint: t('someone pays for it') },
  { key: 'time', label: t('time saved'), hint: t('a routine takes less of your time') },
  { key: 'learning', label: t('learning'), hint: t('you learn something new') },
  { key: 'other', label: t('other'), hint: t('describe it in the line below') },
]

interface LadderPayload { milestones: Milestone[] }

/** The project's milestones, live. */
export function useMilestones(project: string) {
  return useQuery({
    queryKey: ['milestones', project],
    queryFn: ({ signal }) => getJson<LadderPayload>(`/api/milestones?project=${encodeURIComponent(project)}`, signal),
    enabled: !!project,
    staleTime: 10_000,
  })
}

/** Every task of the project with dates normalised — the calendar read,
 *  over a range wide enough that nothing is clipped. */
export function useProjectTasks(project: string) {
  return useQuery({
    queryKey: ['milestone-tasks', project],
    queryFn: ({ signal }) => getJson<{ tasks: CalTask[]; sprints: unknown[] }>(`/api/calendar?project=${encodeURIComponent(project)}&from=2000-01-01&to=2099-12-31`, signal),
    enabled: !!project,
    staleTime: 10_000,
    select: (d) => d.tasks,
  })
}

export function useReason(project: string) {
  return useQuery({
    queryKey: ['reason', project],
    queryFn: ({ signal }) => getJson<Reason>(`/api/projects/${encodeURIComponent(project)}/reason`, signal),
    enabled: !!project,
    staleTime: 30_000,
  })
}

export function useReasonWrite(project: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { kind: string; text: string }) =>
      postJson<Reason>(`/api/projects/${encodeURIComponent(project)}/reason`, input),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['reason', project] }) },
  })
}

/** The same writers the calendar uses; the ladder pages refresh both. */
export function useMilestoneWrites(project: string) {
  const qc = useQueryClient()
  const w = useCalendarWrites(project)
  const refresh = () => {
    w.refresh()
    void qc.invalidateQueries({ queryKey: ['milestone-tasks'] })
  }
  return { ...w, refresh }
}

// ---------------------------------------------------------------------------
// Templates — a ladder to start from, by reason
// ---------------------------------------------------------------------------

interface LadderStep { title: string; outcome: string; check: string }

export const LADDERS: Record<ReasonKind, LadderStep[]> = {
  attention: [
    { title: t('A stranger can use it'), outcome: t('it works without my help'), check: t('someone who never saw the code installs it from the README and gets a result') },
    { title: t('The article is out'), outcome: t('there is one page to send people to'), check: t('published, linked from the README') },
    { title: t('The post is out'), outcome: t('the people it is for have seen it'), check: t('posted where they read, with the link') },
    { title: t('30 stars'), outcome: t('proof that strangers want it'), check: t('the repo shows 30') },
    { title: t('First outside contributor'), outcome: t('someone else has contributed'), check: t('a merged change from someone else') },
  ],
  money: [
    { title: t('A demo I can show'), outcome: t('there is a working demo to show'), check: t('a ten-minute demo runs without problems') },
    { title: t('First pilot'), outcome: t('one company uses it on their own data'), check: t('they ran it twice without me') },
    { title: t('First payment'), outcome: t('a customer pays for it'), check: t('the first payment arrived') },
    { title: t('First renewal'), outcome: t('the customer stays'), check: t('they paid a second time') },
  ],
  time: [
    { title: t('The routine runs end to end'), outcome: t('the routine runs without manual steps'), check: t('one full run with no manual step') },
    { title: t('Three days in a row'), outcome: t('it works without checking'), check: t('used three days running without opening the code') },
    { title: t('An hour a week back'), outcome: t('the routine no longer takes my time'), check: t('the manual task is off the calendar') },
  ],
  learning: [
    { title: t('I can explain it'), outcome: t('I understand it without the tutorial'), check: t('a page in my own words, not copied') },
    { title: t('Built from memory'), outcome: t('I can build it myself'), check: t('a working version without looking anything up') },
    { title: t('Taught once'), outcome: t('I can answer questions about it'), check: t('walked one person through it') },
  ],
  other: [
    { title: t('Version one'), outcome: t('the first version works'), check: t('describe how to check it') },
    { title: t('Shown to someone'), outcome: t('someone else has seen it'), check: t('one person saw it and said something') },
  ],
}

// ---------------------------------------------------------------------------
// Reading a step
// ---------------------------------------------------------------------------

export interface StepRead {
  milestone: Milestone
  /** Tasks feeding it, from the project's task rows. */
  tasks: CalTask[]
  open: CalTask[]
  doneN: number
  /** Days from today to the target; negative when past; null without a target. */
  daysLeft: number | null
  /** Open tasks past their planned day or due day. */
  slipping: number
  /** The step the project is on: the first not reached, in order. */
  current: boolean
  reached: boolean
  dropped: boolean
}

export function readLadder(milestones: Milestone[], tasks: CalTask[], today: string = isoToday()): StepRead[] {
  const byId = new Map(tasks.map((it) => [it.id, it]))
  const ordered = [...milestones].sort((a, b) => a.position - b.position || (a.target_date || '9999').localeCompare(b.target_date || '9999'))
  let currentSet = false
  return ordered.map((m) => {
    const rows = m.tasks.map((id) => byId.get(id)).filter((it): it is CalTask => !!it)
    const open = rows.filter((it) => !isDone(it) && !it.archived)
    const reached = m.status === 'reached'
    const dropped = m.status === 'dropped'
    const current = !reached && !dropped && !currentSet
    if (current) currentSet = true
    return {
      // Archived-but-not-done is neither open nor done; it does not count as progress.
      milestone: m, tasks: rows, open, doneN: rows.filter(isDone).length,
      daysLeft: m.target_date ? daysBetween(today, m.target_date) : null,
      slipping: open.filter((it) => (it.due && it.due < today) || (it.planned && it.planned < today)).length,
      current, reached, dropped,
    }
  })
}

/** "in 12 days" · "3 days late" · "today" · "no date" */
export function distanceWord(daysLeft: number | null): string {
  if (daysLeft === null) return t('no date')
  if (daysLeft === 0) return t('today')
  if (daysLeft > 0) return tn(daysLeft, 'in {n} day', 'in {n} days')
  return tn(-daysLeft, '{n} day late', '{n} days late')
}
