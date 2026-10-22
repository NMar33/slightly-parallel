import { useEffect, useMemo, useRef, type ReactNode } from 'react'
import { Focus, Sunrise } from 'lucide-react'

import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { DayBookTitle } from '../daybook/DayBookTitle'
import { NoEntriesYet } from '../daybook/NoEntriesYet'
import { MonthBand } from '../daybook/MonthBand'
import { useDayBook } from '../daybook/useDayBook'
import { monthOfDay, projectsByNewest, useDayBookProjects, useReach } from '../daybook/data'
import { MonthFeed } from '../daybook/MonthFeed'
import { ReadingSizeControl, useReadingSize } from '../daybook/readingSize'
import { useTaskOpener } from '../agents/parts'
import { useStandups } from './data'
import { DayEntry } from './daybook/DayEntry'
import { useDayBookEntries } from './daybook/shared'
import { Lead } from './parts'
import { StandupFocus } from './focus/Focus'
import { t, tn } from '../../i18n/scope/system'
import { isTypingTarget } from '../../lib/typing'

/**
 * The diary — the body of /standups (chosen in the Lab on 2026-09-23 from v04)
 * and of its variant.
 *
 * A month grid on top: one cell per day, shaded by how much was said, a dot
 * for a day with a standup. A strip under it lists the days that have a
 * standup and the month's totals. Below, the diary: every day of the month
 * with work is an entry, newest first — the standup with its numbers, or
 * one grey line when nobody wrote one.
 */
const NONE = () => false

/** `project`: a tab of that project's page — its entries only, no project pills, no lead. */
export function StandupsDayBook({ guide, project: inProject }: { guide?: ReactNode; project?: string }) {
  // The rows alone say which projects have a standup: no document is read for this.
  const all = useStandups(NONE)
  const withEntries = useMemo(() => projectsByNewest(all.standups, (s) => s.row.project, (s) => s.row.created_date), [all.standups])
  const known = useDayBookProjects(withEntries)
  const { hash, setHash, q, project, month, showMonth, active, days, keys, pick } = useDayBook(inProject ? [inProject] : known)
  const [reach, setReach] = useReach(month)
  const [size, setSize] = useReadingSize('standups')
  const { shown, byDay, loading, error } = useDayBookEntries(project, q, reach)
  const tasks = useTaskOpener(project)

  const totals = useMemo(() => keys.reduce((t, k) => {
    const n = days[k]; if (!n) return t
    return { standups: t.standups + (byDay.has(k) ? 1 : 0), messages: t.messages + n.messages_n,
      done: t.done + n.tasks_done_n, commits: t.commits + n.commits_n }
  }, { standups: 0, messages: 0, done: 0, commits: 0 }), [keys, days, byDay])
  const marked = useMemo(() => new Set(keys.filter((k) => byDay.has(k))), [keys, byDay])
  const earliest = useMemo(() => monthOfDay([...byDay.keys()].sort()[0] ?? ''), [byDay])

  // Focus: one day's standup alone, full screen (focus/Focus.tsx). In the
  // address with the day, so a reload or a link keeps it; F opens it, Esc leaves.
  const focus = hash.focus === '1'
  const canFocus = withEntries.includes(project)
  const onKeyRef = useRef<(e: KeyboardEvent) => void>(() => {})
  onKeyRef.current = (e: KeyboardEvent) => {
    if (isTypingTarget(e)) return
    if (e.key === 'f' && !e.metaKey && !e.ctrlKey && !e.altKey && canFocus && !focus) { e.preventDefault(); setHash({ focus: '1' }) }
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => onKeyRef.current(e)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex flex-col gap-16">
      <DayBookTitle icon={Sunrise} name={t('Standups')} count={shown.length}
        projects={inProject ? [] : known} project={project} onProject={(v) => setHash({ project: v, day: '' })}
        q={hash.q ?? ''} onFind={(v) => setHash({ q: v })}
        right={<>
          {canFocus && (
            <button type="button" onClick={() => setHash({ focus: '1' })}
              title={t('Focus mode: one day\'s standup alone, full screen (F)')}
              className="inline-flex items-center gap-4 h-24 px-8 rounded-input border border-border-subtle bg-surface text-12 text-secondary hover:text-brand hover:border-brand">
              <Focus size={12} aria-hidden />{t('Focus')}
            </button>
          )}
          <ReadingSizeControl value={size} onChange={setSize} />
        </>} />
      {!inProject && (guide ?? <Lead />)}
      {error && <ErrorBanner title={t('Could not read standups')} hideDismiss />}

      <MonthBand
        month={month} days={days} marked={marked} markWord="standup" active={active}
        onPick={pick} onMonth={showMonth} emptyWord={t('No standup this month.')}
        totals={<>
          <span>{tn(totals.standups, '{n} standup', '{n} standups')}</span><span>{tn(totals.messages, '{n} message', '{n} messages')}</span>
          <span>{tn(totals.done, '{n} task done', '{n} tasks done')}</span><span>{tn(totals.commits, '{n} commit', '{n} commits')}</span>
        </>}
      />

      {loading && <LoadingSkeleton variant="card" count={3} />}
      {!loading && !withEntries.includes(project) && (
        <NoEntriesYet name={t('standups')} project={project} command="#standup" verb={t('write one')}
          when={t('When the first agent of a new day writes the standup')} />
      )}
      {!loading && withEntries.includes(project) && (
        <MonthFeed project={project} earliest={earliest} anchor={month} active={active} onReach={setReach} zoom={size}
          keep={(k, n) => byDay.has(k) || (n?.messages_n ?? 0) > 0 || (n?.commits_n ?? 0) > 0}
          renderDay={(k, n) => <DayEntry day={k} n={n} standups={byDay.get(k) ?? []} onTask={tasks.open} active={active === k} />} />
      )}
      {focus && canFocus && (
        <StandupFocus project={project} day={active} onPick={pick} onOpenTask={tasks.open}
          onClose={(d) => { setHash({ focus: '' }); if (d) pick(d) }} />
      )}
      {tasks.modal}
    </div>
  )
}
