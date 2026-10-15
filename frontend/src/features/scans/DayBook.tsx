import { useMemo, useState, type ReactNode } from 'react'
import { Telescope } from 'lucide-react'

import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { DayBookTitle } from '../daybook/DayBookTitle'
import { NoEntriesYet } from '../daybook/NoEntriesYet'
import { DayNumbersRow } from '../daybook/DayNumbers'
import { MonthBand, DaySection, NothingDay } from '../daybook/MonthBand'
import { useDayBook } from '../daybook/useDayBook'
import { monthOfDay, projectsByNewest, useDayBookProjects } from '../daybook/data'
import { MonthFeed } from '../daybook/MonthFeed'
import { ReadingSizeControl, useReadingSize } from '../daybook/readingSize'
import { Segmented } from '../../components/Segmented'
import { persistPref, readPref } from '../../lib/uiPrefs'
import { landedWords, matches, useScans, type Landed, type Scan } from './data'
import { ChangeBar, LandedChips, Lines, ScanBody, Who } from './parts'
import { t, tn } from '../../i18n/scope/system'

const OPEN_KEY = 'sp-scans-daybook-open'

/**
 * The scans as a day book: the same month band the standups and the
 * decisions draw, then the scans of each day in full.
 *
 * The table at /scans answers "what has shipped, in order". This answers
 * "what happened on a day" — the scan beside the messages, tasks and
 * commits of the same day, so a day reads as one thing wherever it is
 * opened.
 */
export function ScansDayBook({ guide }: { guide?: ReactNode }) {
  const { scans, loading, error } = useScans()
  const withEntries = useMemo(() => projectsByNewest(scans, (s) => s.row.project, (s) => s.row.created_date), [scans])
  const known = useDayBookProjects(withEntries)
  const { hash, setHash, q, project, month, showMonth, active, days, keys, pick } = useDayBook(known)
  const [size, setSize] = useReadingSize('scans')
  const [detail, setDetail] = useState<'folded' | 'open'>(
    () => (readPref(OPEN_KEY) === 'open' ? 'open' : 'folded'),
  )
  const fold = detail === 'folded'

  const mine = useMemo(
    () => scans.filter((s) => s.row.project === project && matches(s, q)),
    [scans, project, q],
  )
  const byDay = useMemo(() => {
    const m = new Map<string, Scan[]>()
    for (const s of mine) m.set(s.row.created_date, [...(m.get(s.row.created_date) ?? []), s])
    return m
  }, [mine])
  const marked = useMemo(() => new Set(keys.filter((k) => byDay.has(k))), [keys, byDay])
  const earliest = useMemo(() => monthOfDay([...byDay.keys()].sort()[0] ?? ''), [byDay])
  const totals = useMemo(() => keys.reduce((t, k) => {
    const n = days[k]
    const of = byDay.get(k) ?? []
    return {
      scans: t.scans + of.length,
      files: t.files + of.reduce((x, s) => x + s.row.files_n, 0),
      add: t.add + of.reduce((x, s) => x + s.row.lines_add, 0),
      del: t.del + of.reduce((x, s) => x + s.row.lines_del, 0),
      commits: t.commits + (n?.commits_n ?? 0),
    }
  }, { scans: 0, files: 0, add: 0, del: 0, commits: 0 }), [keys, days, byDay])
  const widest = Math.max(1, ...mine.map((s) => s.row.lines_add + s.row.lines_del))
  /** What landed in the whole month, counted by type: the page's statistics. */
  const landedMonth = useMemo(() => {
    const all: Landed[] = []
    for (const k of keys) for (const s of byDay.get(k) ?? []) all.push(...s.landed)
    return landedWords(all)
  }, [keys, byDay])

  return (
    <div className="flex flex-col gap-16">
      <DayBookTitle icon={Telescope} name={t('Scans')} count={mine.length}
        projects={known} project={project} onProject={(v) => setHash({ project: v, day: '' })}
        q={hash.q ?? ''} onFind={(v) => setHash({ q: v })}
        right={<><ReadingSizeControl value={size} onChange={setSize} /><Segmented label={t('Detail')} shape="pill" value={detail}
          onChange={(v) => { setDetail(v); persistPref(OPEN_KEY, v) }}
          options={[['folded', t('collapsed'), t('Files and Changes are collapsed until you open them')],
                    ['open', t('open all'), t('Every scan shows its files and changes')]] as const} /></>} />
      {guide}
      {error && <ErrorBanner title={t('Could not read scans')} hideDismiss />}

      <MonthBand
        month={month} days={days} marked={marked} markWord={t('scan')} active={active}
        onPick={pick} onMonth={showMonth} emptyWord={t('No scan this month.')}
        totals={<>
          <span>{tn(totals.scans, '{n} scan', '{n} scans')}</span><span>{tn(totals.files, '{n} file', '{n} files')}</span>
          <span><Lines add={totals.add} del={totals.del} /></span>
          <span>{tn(totals.commits, '{n} commit', '{n} commits')}</span>
          {landedMonth.length > 0 && <span className="text-secondary">{landedMonth.slice(0, 4).join(' · ')}</span>}
        </>}
      />

      {loading && <LoadingSkeleton variant="card" count={3} />}
      {!loading && !withEntries.includes(project) && (
        <NoEntriesYet name={t('scans')} project={project} command="#scan" verb={t('make one')}
          when={t('When an agent makes a scan in this project')} />
      )}
      {!loading && withEntries.includes(project) && (
        <MonthFeed project={project} earliest={earliest} anchor={month} active={active} zoom={size}
          keep={(k, n) => byDay.has(k) || (n?.commits_n ?? 0) > 0 || (n?.messages_n ?? 0) > 0}
          renderDay={(k, n) => {
            const of = byDay.get(k) ?? []
            if (!of.length) return <NothingDay key={k} day={k} word={t('No scan')} numbers={<DayNumbersRow n={n} compact />} />
            return (
              <DaySection key={k} day={k} active={active === k} heading={<DayNumbersRow n={n} />}>
                {of.map((s) => (
                  <article key={s.row.id} id={s.row.id} className="grid gap-12 md:grid-cols-[120px_minmax(0,1fr)]">
                    <div className="flex flex-col gap-3 min-w-0 text-11 font-mono text-tertiary">
                      <Who s={s} stacked />
                      <span className="tabular">{s.row.created_time}</span>
                      <ChangeBar add={s.row.lines_add} del={s.row.lines_del} max={widest} width={100} />
                      <span className="tabular">{tn(s.row.files_n, '{n} file', '{n} files')}</span>
                      <span><Lines add={s.row.lines_add} del={s.row.lines_del} /></span>
                      {s.row.decisions_n > 0 && <span className="tabular">{tn(s.row.decisions_n, '{n} decision', '{n} decisions')}</span>}
                    </div>
                    <div className="flex flex-col gap-10 min-w-0">
                      <h3 className="text-14 text-primary leading-snug">{s.summary}</h3>
                      <LandedChips landed={s.landed} limit={6} />
                      <ScanBody s={s} fold={fold} />
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
