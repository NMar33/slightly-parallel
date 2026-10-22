import { ExampleSource } from '../example/example'
import { useMemo, type ReactNode } from 'react'
import { Gavel } from 'lucide-react'

import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { DayBookTitle } from '../daybook/DayBookTitle'
import { NoEntriesYet } from '../daybook/NoEntriesYet'
import { DayNumbersRow } from '../daybook/DayNumbers'
import { MonthBand, DaySection, NothingDay } from '../daybook/MonthBand'
import { useDayBook } from '../daybook/useDayBook'
import { inReach, monthOfDay, projectsByNewest, useDayBookProjects, useReach } from '../daybook/data'
import { MonthFeed } from '../daybook/MonthFeed'
import { ReadingSizeControl, useReadingSize } from '../daybook/readingSize'
import { matches, useDecisionRows, useDecisions, type Decision, type DecisionRow } from './data'
import { Alternatives, Excerpt, MetaLine, Why } from './parts'
import { t, tn } from '../../i18n/scope/system'

/**
 * The decisions as a day book: the same month band the standups and the
 * scans draw, then the decisions of each day in full.
 *
 * The document at /decisions reads as a book by month. This reads by day,
 * beside the messages, tasks and commits of the same day, so a decision
 * sits next to the work that produced it.
 */
export function DecisionsDayBook({ guide }: { guide?: ReactNode }) {
  // The rows alone say which projects have a decision; the documents are
  // read only for this project's decisions in the months the feed draws
  // (a find reads the whole project: it looks through the text).
  const rows = useDecisionRows().data?.decisions
  const withEntries = useMemo(() => projectsByNewest(rows ?? [], (r) => r.project ?? "", (r) => r.created_date ?? ''), [rows])
  const known = useDayBookProjects(withEntries)
  const { hash, setHash, q, project, month, showMonth, active, days, keys, pick } = useDayBook(known)
  const [reach, setReach] = useReach(month)
  const [size, setSize] = useReadingSize('decisions')
  const want = (r: DecisionRow) => r.project === project && (q !== '' || inReach(r.created_date, reach))
  const { decisions, loading, error } = useDecisions('', want)

  const mine = useMemo(
    () => decisions.filter((d) => d.row.project === project && matches(d, q)),
    [decisions, project, q],
  )
  const byDay = useMemo(() => {
    const m = new Map<string, Decision[]>()
    for (const d of mine) {
      const day = d.row.created_date
      if (day) m.set(day, [...(m.get(day) ?? []), d])
    }
    return m
  }, [mine])
  const marked = useMemo(() => new Set(keys.filter((k) => byDay.has(k))), [keys, byDay])
  const earliest = useMemo(() => monthOfDay([...byDay.keys()].sort()[0] ?? ''), [byDay])
  const totals = useMemo(() => keys.reduce((t, k) => {
    const of = byDay.get(k) ?? []
    return {
      decisions: t.decisions + of.length,
      major: t.major + of.filter((d) => (d.row.weight ?? '') === 'major').length,
      messages: t.messages + (days[k]?.messages_n ?? 0),
      commits: t.commits + (days[k]?.commits_n ?? 0),
    }
  }, { decisions: 0, major: 0, messages: 0, commits: 0 }), [keys, days, byDay])

  return (
    <div className="flex flex-col gap-16">
      <DayBookTitle icon={Gavel} name={t('Decisions')} count={mine.length}
        projects={known} project={project} onProject={(v) => setHash({ project: v, day: '' })}
        q={hash.q ?? ''} onFind={(v) => setHash({ q: v })}
        right={<ReadingSizeControl value={size} onChange={setSize} />} />
      {guide}
      {error && <ErrorBanner title={t('Could not read decisions')} hideDismiss />}

      <MonthBand
        month={month} days={days} marked={marked} markWord="decision" active={active}
        onPick={pick} onMonth={showMonth} emptyWord={t('No decision this month.')}
        totals={<>
          <span>{tn(totals.decisions, '{n} decision', '{n} decisions')}</span>
          {totals.major > 0 && <span className="text-status-amber">{t('{n} major', { n: totals.major })}</span>}
          <span>{tn(totals.messages, '{n} message', '{n} messages')}</span><span>{tn(totals.commits, '{n} commit', '{n} commits')}</span>
        </>}
      />

      {loading && <LoadingSkeleton variant="card" count={3} />}
      {!loading && !withEntries.includes(project) && (
        <NoEntriesYet name={t('decisions')} project={project} command="#decision" verb={t('log one')}
          when={t('When an agent logs a decision in this project')} />
      )}
      {!loading && withEntries.includes(project) && (
        <MonthFeed project={project} earliest={earliest} anchor={month} active={active} onReach={setReach} zoom={size}
          keep={(k, n) => byDay.has(k) || (n?.commits_n ?? 0) > 0 || (n?.messages_n ?? 0) > 0}
          renderDay={(k, n) => {
            const of = byDay.get(k) ?? []
            if (!of.length) return <NothingDay key={k} day={k} word={t('No decision')} numbers={<DayNumbersRow n={n} compact />} />
            return (
              <DaySection key={k} day={k} active={active === k} heading={<DayNumbersRow n={n} />}>
                {of.map((d) => (
                  <article key={d.row.id} id={d.row.id} className="grid gap-12 md:grid-cols-[120px_minmax(0,1fr)]">
                    <div className="flex flex-col gap-2 min-w-0">
                      <MetaLine d={d} />
                    </div>
                    <div className="flex flex-col gap-10 min-w-0">
                      <h3 className="text-14 text-primary leading-snug">{d.decision}</h3>
                      <Why text={d.why} />
                      <Alternatives items={d.alternatives} />
                      <Excerpt text={d.excerpt} />
                      <ExampleSource kind="decision" project={d.row.project ?? ''} agentId={d.row.agent_id ?? ''} date={d.row.created_date ?? ''} time={d.row.created_time ?? ''} />
                    </div>
                  </article>
                ))}
              </DaySection>
            )
          }} />
      )}
    </div>
  )
}
