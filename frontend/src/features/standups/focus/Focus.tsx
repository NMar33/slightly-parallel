/**
 * Standup focus — one day's standup, full screen, in the chats focus shell
 * (variant D of the 2026-10-08 mockup, kept at tag pre-release-cleanup):
 * the days that have a standup on the left with a find box, the day in one
 * reading column as wide as you set it, the day drawn small by section down
 * the right edge, one day or all of them read as one, the same keys.
 */

import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { ChevronDown, ChevronUp, Menu, Minimize2, Search, Settings2 } from 'lucide-react'

import { IconButton } from '../../../components/primitives'
import { Markdown } from '../../../components/Markdown'
import { Segmented } from '../../../components/Segmented'
import { dayHeading } from '../../../utils/dateUtils'
import { fmtDay } from '../../agents/parts'
import {
  Column, EdgeHandle, FocusSettings, Frame, SizeSwitch, readFocusPrefs, storeFocusPrefs, useFocusKeys, type FocusPrefs,
} from '../../chats/focus/shared'
import { DayNumbersRow } from '../../daybook/DayNumbers'
import { monthOfDay, monthQuery, ZERO, type DayNumbers } from '../../daybook/data'
import { matches, useDayRecord, type DayRecord, type Standup } from '../data'
import { DayAgents, DayCreated, DayTasks, KindChip, TextWithTasks } from '../daybook/DayEntry'
import { groupByKind } from '../daybook/kinds'
import { useDayBookEntries } from '../daybook/shared'
import { Who } from '../parts'
import { DayMap } from './DayMap'
import { bulletsOf, needsOf, sectionsOf, type SectionKind } from './sections'
import { t, tn } from '../../../i18n/scope/system'
import { isTypingTarget } from '../../../lib/typing'

const PREF = 'sp-standup-focus'
/** The days list is narrower than the chats list: a date and a summary. */
const BASE: Partial<FocusPrefs> = { listWidth: 300 }

export interface StandupFocusProps {
  project: string
  /** The day to open on; the newest standup when it has none. */
  day: string
  /** Another day picked in "one day". */
  onPick: (day: string) => void
  /** Focus closed, on the day that was being read. */
  onClose: (day: string) => void
  onOpenTask: (id: string) => void
}

/** Each day's numbers, from the month calendars the page already reads. */
function useDayNumbers(project: string, days: string[]): Map<string, DayNumbers> {
  const months = useMemo(() => [...new Set(days.map(monthOfDay).filter(Boolean))], [days])
  const qs = useQueries({ queries: months.map((m) => monthQuery(project, m)) })
  const stamp = qs.map((q) => q.dataUpdatedAt).join(',')
  return useMemo(() => {
    const out = new Map<string, DayNumbers>()
    for (const q of qs) for (const [k, n] of Object.entries(q.data?.days ?? {})) out.set(k, n)
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `stamp` stands for the answers
  }, [stamp])
}

export function StandupFocus(p: StandupFocusProps) {
  // Every standup of the project, read in full: the list finds in the text and "all" reads it.
  const { byDay, loading } = useDayBookEntries(p.project, '', '')
  // A standup with no readable date has no day to stand under.
  const days = useMemo(() => [...byDay.keys()].filter((d) => /^\d{4}-\d{2}$/.test(d ?? '')).sort().reverse(), [byDay])
  const numbers = useDayNumbers(p.project, days)
  return <FocusLook {...p} days={days} byDay={byDay} numbers={numbers} loading={loading} />
}

/* ------------------------------------------------------------------ list */

function DayList({ days, byDay, numbers, current, onPick, size }: {
  days: string[]; byDay: Map<string, Standup[]>; numbers: Map<string, DayNumbers>
  current: string; onPick: (day: string) => void; size: number
}) {
  const [find, setFind] = useState('')
  const shown = useMemo(() => {
    const q = find.trim()
    return q ? days.filter((d) => (byDay.get(d) ?? []).some((s) => matches(s, q) || s.story.toLowerCase().includes(q.toLowerCase()))) : days
  }, [days, byDay, find])
  const list = useRef<HTMLOListElement>(null)
  useEffect(() => { list.current?.querySelector('[aria-current="true"]')?.scrollIntoView?.({ block: 'nearest' }) }, [current])
  return (
    <div className="flex flex-col min-h-0 h-full">
      <label className="shrink-0 mx-12 my-8 flex items-center gap-6 h-[28px] px-8 rounded-input border border-border-default bg-surface">
        <Search size={12} className="text-tertiary" aria-hidden />
        <input value={find} onChange={(e) => setFind(e.target.value)} placeholder={t('Find a day')} aria-label={t('Find a day')}
          className="flex-1 min-w-0 bg-transparent text-12 text-primary outline-none" />
      </label>
      <ol ref={list} className="flex-1 min-h-0 overflow-y-auto" aria-label={t('Days with a standup')}>
        {shown.map((d) => {
          const n = numbers.get(d)
          const first = byDay.get(d)?.[0]
          return (
            <li key={d}>
              <button type="button" aria-current={d === current} onClick={() => onPick(d)}
                className={`w-full text-left px-12 py-6 flex flex-col gap-2 border-l-2 ${d === current ? 'border-brand bg-brand-glow' : 'border-transparent hover:bg-hover'}`}>
                <span className="font-mono text-tertiary tabular-nums" style={{ fontSize: Math.max(10, size - 2) }}>
                  {fmtDay(d)}
                  {n && n.messages_n > 0 && <> · {tn(n.messages_n, '{n} msg', '{n} msg')}</>}
                  {n && n.commits_n > 0 && <> · {tn(n.commits_n, '{n} commit', '{n} commits')}</>}
                </span>
                <span className="text-primary leading-snug" style={{ fontSize: size, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {first?.summary || '—'}
                </span>
              </button>
            </li>
          )
        })}
        {shown.length === 0 && <li className="px-12 py-8 text-12 text-tertiary">{t('No standup has that in it.')}</li>}
      </ol>
    </div>
  )
}

/* --------------------------------------------------------------- reading */

/** A section's heading: its name, how many, and a rule to the edge. */
function SecHead({ label, count, children }: { label: string; count?: number; children?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-8 flex-wrap text-11 font-mono text-tertiary">
      <span className="uppercase tracking-wide">{label}{count != null && count > 0 && <> · {count}</>}</span>
      {children}
      <span className="flex-1 min-w-[24px] h-[1px] bg-border-subtle" aria-hidden />
    </div>
  )
}

/** "… · operator, 12:02": the decision, then who and when, quieter. */
function splitBy(line: string): [string, string] {
  const i = line.lastIndexOf(' · ')
  return i > 0 && line.length - i < 48 ? [line.slice(0, i), line.slice(i + 3)] : [line, '']
}

const ITEM = 'grid grid-cols-[88px_minmax(0,1fr)] gap-12 leading-relaxed text-primary'
const ID = 'text-[0.85em]'

function sectionLabel(kind: SectionKind, day: string, dated: boolean): string {
  switch (kind) {
    // In "all" the day's heading above already carries the date.
    case 'day': return dated ? t('The day') : t('The day · {date}', { date: dayHeading(day) })
    case 'needs': return t('Needs your answer')
    case 'wrong': return t('What went wrong')
    case 'moved': return t('What moved')
    case 'decisions': return t('Decisions')
    case 'tasks': return t('Tasks of the day')
    case 'agents': return t('Agents of the day')
    case 'created': return t('Created')
    case 'forgotten': return t('Maybe forgotten')
    case 'more': return t('More')
  }
}

function StandupRead({ s, si, day, rec, n, size, several, dated, onTask }: {
  /** The day's date is already shown above ("all"). */
  dated: boolean
  s: Standup; si: number; day: string; rec?: DayRecord; n: DayNumbers; size: number
  /** More than one standup covers the day (older days: one per agent). */
  several: boolean
  onTask: (id: string) => void
}) {
  const { needs, rest } = needsOf(s.detail)
  const wrong = bulletsOf(s.deviation)
  const body = (kind: SectionKind) => {
    switch (kind) {
      case 'day': return (
        <>
          {several && <span className="flex items-center gap-8"><Who s={s} /></span>}
          <p data-lead className="border-l-2 border-status-amber/60 pl-14 font-semibold text-primary" style={{ fontSize: Math.round(size * 1.25), lineHeight: 1.45 }}>{s.summary}</p>
          {s.story && <div className="chat-size text-primary flex flex-col gap-6" style={{ fontSize: size + 1, lineHeight: 1.7 }}><Markdown text={s.story} /></div>}
          {!s.loaded && <p className="text-12 font-mono text-tertiary">{t('Loading the standup…')}</p>}
        </>
      )
      case 'needs': return needs.map((x, i) => (
        <div key={i} className={ITEM}>
          <span className="pt-2"><span className="inline-flex items-center h-16 px-6 rounded-pill text-10 font-mono font-medium uppercase tracking-wide text-status-amber bg-status-amber/12">{t('answer')}</span></span>
          <span><TextWithTasks line={x} onTask={onTask} idClass={ID} /></span>
        </div>
      ))
      case 'wrong': return (
        <ul className="flex flex-col gap-10">
          {wrong.map((x, i) => <li key={i} className="border-l-2 border-status-amber/40 pl-12 leading-relaxed text-primary"><TextWithTasks line={x} onTask={onTask} idClass={ID} /></li>)}
        </ul>
      )
      case 'moved': return groupByKind(s.movement).flatMap((g) => g.items.map((x, i) => (
        <div key={`${g.kind}:${i}`} className={g.kind ? ITEM : 'leading-relaxed text-primary'}>
          {g.kind && <span className="pt-2"><KindChip kind={g.kind} toned /></span>}
          <span><TextWithTasks line={x} onTask={onTask} idClass={ID} /></span>
        </div>
      )))
      case 'decisions': return (
        <ul className="flex flex-col gap-10">
          {s.decisions.map((d, i) => {
            const [what, by] = splitBy(d)
            return (
              <li key={i} className="leading-relaxed text-primary">
                <TextWithTasks line={what} onTask={onTask} idClass={ID} />
                {by && <span className="ml-6 font-mono text-tertiary text-[0.8em]">{by}</span>}
              </li>
            )
          })}
        </ul>
      )
      case 'tasks': return rec ? <DayTasks rec={rec} onTask={onTask} text="" /> : null
      case 'agents': return rec ? <DayAgents rec={rec} text="" /> : null
      case 'created': return rec ? <DayCreated rec={rec} text="" /> : null
      case 'forgotten': return (
        <ul className="flex flex-col gap-10">
          {s.forgotten.map((d, i) => <li key={i} className="leading-relaxed text-secondary"><TextWithTasks line={d} onTask={onTask} idClass={ID} /></li>)}
        </ul>
      )
      case 'more': return <div className="chat-size text-secondary"><Markdown text={rest} /></div>
    }
  }
  return (
    <>
      {sectionsOf(s, rec).map(({ kind, count }) => {
        const label = sectionLabel(kind, day, dated)
        return (
          <section key={kind} data-sec-key={`${day}|${si}|${kind}`} data-sec={kind} data-day={day} data-label={label}
            className="scroll-mt-24 flex flex-col gap-12" style={{ fontSize: size }}>
            <SecHead label={label} count={kind === 'day' || kind === 'more' ? undefined : count}>
              {kind === 'day' && <DayNumbersRow n={n} agents={false} />}
            </SecHead>
            {body(kind)}
          </section>
        )
      })}
    </>
  )
}

function DayRead({ project, day, standups, n, size, head, onTask }: {
  project: string; day: string; standups: Standup[]; n: DayNumbers; size: number
  /** In "all", the day opens with its date and summary. */
  head: boolean
  onTask: (id: string) => void
}) {
  const rec = useDayRecord(project, day, true).data
  return (
    <div data-day={day} className="flex flex-col gap-32">
      {head && (
        <header data-day-head={day} className="flex flex-col gap-2 pt-16 border-t-2 border-border-default">
          <h2 className="text-16 font-semibold text-primary leading-snug">{dayHeading(day)}</h2>
        </header>
      )}
      {standups.map((s, si) => (
        // The record is the day's: drawn once, under the first standup.
        <StandupRead key={s.row.id} s={s} si={si} day={day} rec={si === 0 ? rec : undefined} n={n} size={size}
          several={standups.length > 1} dated={head} onTask={onTask} />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ look */

interface LookProps extends StandupFocusProps {
  days: string[]
  byDay: Map<string, Standup[]>
  numbers: Map<string, DayNumbers>
  loading: boolean
}

function FocusLook(p: LookProps) {
  const [prefs, setPrefs] = useState<FocusPrefs>(() => readFocusPrefs(PREF, BASE))
  const set = (x: Partial<FocusPrefs>) => { const next = { ...prefs, ...x }; setPrefs(next); storeFocusPrefs(next, PREF) }
  const [gear, setGear] = useState(false)
  const all = prefs.scope === 'all'
  const { days, byDay } = p
  const cur = days.includes(p.day) ? p.day : days[0] ?? ''

  // "All" draws the days around the one being read and adds more as the
  // reader nears either end, as the chats map does.
  const curIdx = Math.max(0, days.indexOf(cur))
  const [range, setRange] = useState<[number, number]>([0, 1])
  const shownDays = all ? days.slice(range[0], range[1]) : cur ? [cur] : []
  const pending = useRef<string | null>(null)
  const anchor = useRef<{ height: number; top: number } | null>(null)

  const scroller = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLElement>(null)
  const [at, setAt] = useState('')
  const [here, setHere] = useState(cur)
  // The sections drawn, in order, read from the page: they appear as the
  // standup and the day's record arrive.
  const [secs, setSecs] = useState<Array<{ key: string; day: string }>>([])
  const [version, setVersion] = useState(0)
  useLayoutEffect(() => {
    const root = scroller.current
    if (!root) return
    let frame = 0
    const read = () => {
      frame = 0
      const next = [...root.querySelectorAll<HTMLElement>('[data-sec-key]')].map((el) => ({ key: el.dataset.secKey ?? '', day: el.dataset.day ?? '' }))
      setSecs((prev) => (prev.length === next.length && prev.every((x, i) => x.key === next[i]!.key) ? prev : next))
      setVersion((v) => v + 1)
    }
    read()
    const mo = new MutationObserver(() => { if (!frame) frame = requestAnimationFrame(read) })
    mo.observe(root, { childList: true, subtree: true })
    return () => { mo.disconnect(); if (frame) cancelAnimationFrame(frame) }
  }, [])

  const hold = useRef(0)
  const scrollToSel = (sel: string, smooth: boolean) => {
    scroller.current?.querySelector<HTMLElement>(sel)?.scrollIntoView?.({ block: 'start', behavior: smooth ? 'smooth' : 'auto' })
  }
  const goTo = useCallback((key: string) => {
    hold.current = Date.now() + 700
    setAt(key)
    const day = key.split('|')[0] ?? ''
    if (day) setHere(day)
    scrollToSel(`[data-sec-key="${key}"]`, true)
  }, [])

  // Opening a day (or "all") lands on it: once per day and scope.
  const landed = useRef('')
  useEffect(() => {
    if (!cur) return
    const key = `${prefs.scope}|${cur}`
    if (landed.current === key) return
    landed.current = key
    setHere(cur)
    setAt(`${cur}|0|day`)
    if (all) {
      pending.current = cur
      setRange([Math.max(0, curIdx - 1), Math.min(days.length, curIdx + 3)])
    } else if (scroller.current) {
      scroller.current.scrollTop = 0
    }
  }, [cur, all, curIdx, days.length, prefs.scope])

  useLayoutEffect(() => {
    const root = scroller.current
    if (pending.current != null) {
      const d = pending.current
      pending.current = null
      root?.querySelector<HTMLElement>(`[data-day-head="${d}"]`)?.scrollIntoView?.({ block: 'start' })
    } else if (anchor.current && root) {
      // Days drawn above: keep the text under the eye where it was.
      root.scrollTop = anchor.current.top + (root.scrollHeight - anchor.current.height)
      anchor.current = null
    }
  }, [range])
  const more = useCallback((side: 'up' | 'down') => {
    const root = scroller.current
    if (side === 'up') {
      if (range[0] <= 0) return
      if (root) anchor.current = { height: root.scrollHeight, top: root.scrollTop }
      setRange(([a, b]) => [Math.max(0, a - 3), b])
    } else if (range[1] < days.length) {
      setRange(([a, b]) => [a, Math.min(days.length, b + 3)])
    }
  }, [range, days.length])
  const topEdge = useRef<HTMLDivElement>(null)
  const bottomEdge = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const root = scroller.current
    if (!root || !all || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) more(e.target === topEdge.current ? 'up' : 'down')
    }, { root, rootMargin: '1200px 0px' })
    if (topEdge.current) io.observe(topEdge.current)
    if (bottomEdge.current) io.observe(bottomEdge.current)
    return () => io.disconnect()
  }, [all, more, shownDays.length])

  // The section in view: the last one whose top has passed the reading
  // line near the top. A section just moved to by key holds for a moment,
  // so a smooth scroll on its way there does not pick the ones it passes.
  const readAt = useCallback(() => {
    const root = scroller.current
    if (!root || Date.now() < hold.current) return
    const line = root.getBoundingClientRect().top + 40
    let pick: HTMLElement | undefined
    // A day's heading past the line stands for the day's first section.
    let head = false
    for (const el of root.querySelectorAll<HTMLElement>('[data-sec-key], [data-day-head]')) {
      const past = el.getBoundingClientRect().top <= line
      if (el.dataset.dayHead != null) { if (!past) break; head = true; continue }
      if (past || head) { pick = el; if (!past) break; head = false } else break
    }
    pick ??= root.querySelector<HTMLElement>('[data-sec-key]') ?? undefined
    if (pick?.dataset.secKey) { setAt(pick.dataset.secKey); if (pick.dataset.day) setHere(pick.dataset.day) }
  }, [])
  useEffect(() => {
    const root = scroller.current
    if (!root) return
    let frame = 0
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; readAt() }) }
    root.addEventListener('scroll', onScroll, { passive: true })
    return () => { root.removeEventListener('scroll', onScroll); if (frame) cancelAnimationFrame(frame) }
  }, [readAt])

  const day = all ? (days.includes(here) ? here : cur) : cur
  const dayIdx = days.indexOf(day)
  const older = dayIdx >= 0 && dayIdx < days.length - 1 ? days[dayIdx + 1] : undefined
  const newer = dayIdx > 0 ? days[dayIdx - 1] : undefined
  /** In "all", scroll to the day (drawing it first when it is far off); in one, open it. */
  const openDay = (d: string) => {
    if (!all) { p.onPick(d); return }
    const i = days.indexOf(d)
    if (i < 0) return
    setHere(d)
    setAt(`${d}|0|day`)
    if (i < range[0] || i >= range[1]) {
      pending.current = d
      setRange([Math.max(0, i - 1), Math.min(days.length, i + 3)])
      return
    }
    scrollToSel(`[data-day-head="${d}"]`, true)
  }
  const ofDay = secs.filter((x) => x.day === day)
  const secIdx = ofDay.findIndex((x) => x.key === at)
  const step = (by: 1 | -1) => {
    const i = secs.findIndex((x) => x.key === at)
    const next = secs[Math.max(0, Math.min(secs.length - 1, (i < 0 ? 0 : i) + by))]
    if (next) goTo(next.key)
  }
  // Back to one day from "all": the day that was being read.
  const setScope = (v: 'one' | 'all') => {
    if (v === 'one' && all && day && day !== cur) p.onPick(day)
    set({ scope: v })
  }
  // Leaving "all" returns to the day that was being read.
  const leave = () => p.onClose(day)

  useFocusKeys((e) => {
    if (isTypingTarget(e)) return
    if (e.metaKey || e.ctrlKey || e.altKey) return
    if (e.key === 'Escape') { e.preventDefault(); if (gear) setGear(false); else leave() }
    else if (e.key === 'j') { e.preventDefault(); step(1) }
    else if (e.key === 'k') { e.preventDefault(); step(-1) }
    else if (e.key === ']' && older) openDay(older)
    else if (e.key === '[' && newer) openDay(newer)
    else if (e.key === 'c') { e.preventDefault(); set({ drawer: !prefs.drawer }) }
    else if (e.key === 'a') { e.preventDefault(); setScope(all ? 'one' : 'all') }
  })

  const summary = byDay.get(day)?.[0]?.summary ?? ''
  const title = day ? `${dayHeading(day)} · ${summary}` : t('Standups')
  return (
    <Frame label={title}>
      <header className="relative shrink-0 h-[40px] px-12 flex items-center gap-8 border-b border-border-subtle">
        <IconButton onClick={leave} label={t('Leave focus (Esc)')}><Minimize2 size={13} /></IconButton>
        <IconButton onClick={() => set({ drawer: !prefs.drawer })} label={t('The days list (C)')} active={prefs.drawer}><Menu size={14} /></IconButton>
        <Segmented label={t('Show')} shape="pill" height={20} value={prefs.scope} onChange={setScope}
          options={[['one', t('one day'), t('This day only')], ['all', t('all'), t('Every day with a standup, newest first, as one read (A)')]] as const} />
        <h1 className="min-w-0 flex-1 text-13 font-semibold text-primary truncate">{title}</h1>
        <span className="text-11 font-mono text-tertiary tabular-nums whitespace-nowrap">
          {dayIdx >= 0 && t('day {n} of {total}', { n: dayIdx + 1, total: days.length })}
          {dayIdx >= 0 && ofDay.length > 0 && ` · ${t('section {n} of {total}', { n: Math.max(0, secIdx) + 1, total: ofDay.length })}`}
        </span>
        <SizeSwitch size={prefs.size} onSize={(s) => set({ size: s })} />
        <IconButton onClick={() => setGear((v) => !v)} label={t('Settings')} active={gear}><Settings2 size={14} /></IconButton>
        {gear && <FocusSettings prefs={prefs} set={set} onClose={() => setGear(false)} listTitle={t('Days list')} />}
      </header>
      <div className="flex-1 min-h-0 flex">
        {prefs.drawer && (
          <aside ref={listRef} className="relative shrink-0 border-r border-border-subtle min-h-0 flex flex-col" style={{ width: prefs.listWidth }}>
            <div className="shrink-0 px-12 pt-8 flex items-center gap-6 text-10 uppercase tracking-wide font-mono text-tertiary">
              {t('Standups · {n}', { n: days.length })}
              <span className="ml-auto normal-case tracking-normal">
                <IconButton onClick={() => newer && openDay(newer)} disabled={!newer} label={t('The day after ([)')}><ChevronUp size={12} /></IconButton>
                <IconButton onClick={() => older && openDay(older)} disabled={!older} label={t('The day before (])')}><ChevronDown size={12} /></IconButton>
              </span>
            </div>
            <div className="flex-1 min-h-0">
              <DayList days={days} byDay={byDay} numbers={p.numbers} current={day} onPick={openDay} size={prefs.listSize} />
            </div>
            <EdgeHandle panel={listRef} value={prefs.listWidth} onWidth={(w) => set({ listWidth: w })} min={220} max={720} label={t('Change the width of the days list')} />
          </aside>
        )}
        <div ref={scroller} data-focus-reader className="flex-1 min-w-0 min-h-0 overflow-y-auto">
          <Column width={prefs.width} onWidth={(w) => set({ width: w })} className="py-32 flex flex-col gap-32">
            {p.loading && !days.length && <p className="text-12 font-mono text-tertiary">{t('Loading the standups…')}</p>}
            {!p.loading && !days.length && <p className="text-12 font-mono text-tertiary">{t('No standup for this project yet.')}</p>}
            {all && range[0] > 0 && <div ref={topEdge} className="text-11 font-mono text-tertiary text-center">{tn(range[0], '{n} newer day above…', '{n} newer days above…')}</div>}
            {shownDays.map((d) => (
              <Fragment key={d}>
                <DayRead project={p.project} day={d} standups={byDay.get(d) ?? []} n={p.numbers.get(d) ?? ZERO} size={prefs.size}
                  head={all} onTask={p.onOpenTask} />
              </Fragment>
            ))}
            {all && range[1] < days.length && <div ref={bottomEdge} className="text-11 font-mono text-tertiary text-center">{tn(days.length - range[1], '{n} older day below…', '{n} older days below…')}</div>}
            {days.length > 0 && (!all || range[1] >= days.length) && (
              // Room under the end, so the last sections can come up to the reading line.
              <p className="text-11 font-mono text-tertiary text-center" style={{ paddingBottom: '50vh' }}>{all ? t('The oldest standup ends here.') : t('The end of the day.')}</p>
            )}
          </Column>
        </div>
        {secs.length > 0 && <DayMap scroller={scroller} at={at} goTo={goTo} version={version} />}
      </div>
      <footer className="shrink-0 h-24 px-16 flex items-center gap-12 border-t border-border-subtle text-10 font-mono text-tertiary">
        <span>{t('the map on the right: click or drag')}</span><span>{t('j k — sections')}</span><span>{t('[ ] — days')}</span>
        <span>{t('A — one day / all')}</span><span>{t('C — the list')}</span><span>{t('Esc — leave')}</span>
      </footer>
    </Frame>
  )
}
