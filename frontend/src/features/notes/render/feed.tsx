/**
 * The endless feed (design round 2, kept by K). Notes one after another,
 * each whole, drawn a page at a time as the reader nears the end; the note
 * and the section under the reading line (a quarter down the screen) are
 * "in view", and the list and the rail follow them.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowDown } from 'lucide-react'

import { Button } from '../../../components/primitives/Button'
import { LoadingSkeleton } from '../../../components/states'
import { LABEL } from '../../../components/ui'
import { t, tn } from '../../../i18n/scope/notes'
import type { Note } from './model'
import { goTo, Outline, stampOf } from './parts'
import { NoteRead } from './reader'

/** Notes per page of the feed. */
export const PAGE = 3
/** The pause before the next page is drawn, in ms: the reader sees it coming rather than a jump. */
export const PAGE_DELAY = 250

/**
 * How many notes of `ids` are loaded. `more` asks for the next page (it
 * arrives after PAGE_DELAY); `through` loads at once up to a note, for a
 * click in the list or on a tile. A new order starts again at one page.
 */
export function useFeedPages(ids: string[], size = PAGE) {
  const key = ids.join()
  const [state, setState] = useState({ key, count: size, loading: false })
  const cur = state.key === key ? state : { key, count: size, loading: false }
  if (cur !== state) setState(cur)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); timer.current = null }, [key])
  const count = Math.min(cur.count, ids.length)
  const more = useCallback(() => {
    if (timer.current || count >= ids.length) return
    setState((s) => ({ ...s, loading: true }))
    timer.current = setTimeout(() => {
      timer.current = null
      setState((x) => (x.key === key ? { ...x, count: x.count + size, loading: false } : x))
    }, PAGE_DELAY)
  }, [count, ids.length, key, size])
  const through = useCallback((id: string) => {
    const at = ids.indexOf(id)
    if (at >= 0) setState((s) => (s.count > at ? s : { ...s, count: at + 1 }))
  }, [ids])
  return { shown: ids.slice(0, count), count, left: ids.length - count, loading: cur.loading, more, through }
}

/** The note and the section under the reading line. Follows every scroll in the page, the page's own scroller included. */
export function useInView(fallback: string | undefined, again = ''): { note?: string; section?: string } {
  const [at, setAt] = useState<{ note?: string; section?: string }>({ note: fallback })
  useEffect(() => {
    let frame = 0
    const look = () => {
      frame = 0
      const line = window.innerHeight * 0.25
      const notes = [...document.querySelectorAll<HTMLElement>('[data-feed-note]')]
      if (!notes.length) return
      let note = notes[0]!
      for (const el of notes) if (el.getBoundingClientRect().top <= line) note = el
      const id = note.dataset.feedNote
      let section: string | undefined
      for (const s of note.querySelectorAll<HTMLElement>('section[id]')) if (s.getBoundingClientRect().top <= line) section = s.id
      setAt((p) => (p.note === id && p.section === section ? p : { note: id, section }))
    }
    const on = () => { if (!frame) frame = requestAnimationFrame(look) }
    document.addEventListener('scroll', on, true)
    window.addEventListener('resize', on)
    on()
    return () => { document.removeEventListener('scroll', on, true); window.removeEventListener('resize', on); if (frame) cancelAnimationFrame(frame) }
  }, [again])
  return at.note ? at : { note: fallback }
}

/** Bring a note of the feed to the top of the screen. */
export function scrollToNote(id: string, smooth = true) {
  const el = document.querySelector(`[data-feed-note="${id}"]`)
  el?.scrollIntoView?.({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
}

/** Watches the end of the feed and asks for the next page before the reader gets there. */
export function Sentinel({ onSee, loading, left }: { onSee: () => void; loading: boolean; left: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) onSee() }, { rootMargin: '0px 0px 900px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [onSee, left])
  return (
    <div ref={ref} data-testid="feed-end" className="flex flex-col items-center gap-8 py-12 min-w-0">
      {loading && <div className="w-full"><LoadingSkeleton variant="card" count={1} label={t('Loading the next notes')} /></div>}
      {!loading && left > 0 && (
        <Button variant="ghost" size="sm" iconLeft={<ArrowDown size={12} aria-hidden />} onClick={onSee}>
          {tn(left, 'Show more · {n} note left', 'Show more · {n} notes left')}
        </Button>
      )}
    </div>
  )
}

/** Where a note stands among replacements: "replaced by", "replaces". */
export function ReplaceLine({ note, notes, onGo }: { note: Note; notes: Note[]; onGo: (id: string) => void }) {
  const by = note.replacedBy
  const older = note.replaces ?? []
  const name = (id: string) => notes.find((n) => n.id === id)
  if (!by && !older.length) return null
  return (
    <div className="flex flex-col gap-2">
      {by && (
        <p role="note" className="m-0 text-12 text-status-amber">
          {t('Replaced by a newer note:')}{' '}
          <button type="button" className="text-brand hover:underline" onClick={() => onGo(by)}>{name(by)?.title ?? by}</button>
          {name(by) && <span className="text-tertiary font-mono text-11"> · {stampOf(name(by)!.updated)}</span>}. {t('Read that one first.')}
        </p>
      )}
      {older.map((id) => (
        <p key={id} className="m-0 text-12 text-tertiary">
          {t('Replaces an older note:')}{' '}
          <button type="button" className="text-brand hover:underline" onClick={() => onGo(id)}>{name(id)?.title ?? id}</button>
          {name(id) && <span className="font-mono text-11"> · {stampOf(name(id)!.updated)}</span>}
        </p>
      ))}
    </div>
  )
}

/** One note of the feed: its replacement line and the whole note, read as on the Reader. */
export function FeedNote({ note, notes, onGo, index, of, above, omitTask = false }: {
  note: Note; notes: Note[]; onGo: (id: string) => void; index: number; of: number; above?: ReactNode
  /** The task shows in a band above: the note's head leaves it out. */
  omitTask?: boolean
}) {
  const replaced = !!note.replacedBy
  return (
    <div className="flex flex-col gap-12 min-w-0">
      {above}
      <article data-feed-note={note.id} aria-label={note.title}
        className={`min-w-0 w-full rounded-card border bg-surface px-24 py-20 max-sm:px-12 scroll-mt-[12px] flex flex-col gap-12 ${replaced ? 'border-status-amber/40' : 'border-border-subtle'}`}>
        <span className="text-10 font-mono text-tertiary tabular">{t('{i} of {n}', { i: index + 1, n: of })}</span>
        <ReplaceLine note={note} notes={notes} onGo={onGo} />
        <details className="xl:hidden rounded-card border border-border-subtle px-8 py-4">
          <summary className={`${LABEL} cursor-pointer`}>{t('Outline')}</summary>
          <Outline note={note} onGo={goTo} />
        </details>
        <NoteRead note={note} omit={omitTask ? note.task : undefined} />
      </article>
    </div>
  )
}

/** The feed: the shown notes whole, the end that loads the next page, and the line that says it is all. */
export function NoteFeed({ notes, all, pages, onGo, prelude, above }: {
  /** The notes in feed order (after filters). */
  notes: Note[]
  /** Every note, for the replacement lines. */
  all: Note[]
  pages: ReturnType<typeof useFeedPages>
  onGo: (id: string) => void
  prelude?: ReactNode
  /** Something drawn above a note: a task's band in the by-task feed. */
  above?: (note: Note, i: number) => ReactNode
}) {
  const shown = pages.shown.map((id) => notes.find((n) => n.id === id)).filter((n): n is Note => !!n)
  return (
    <div data-testid="note-feed" className="flex flex-col gap-20 min-w-0 max-w-[760px] w-full mx-auto">
      {prelude}
      {shown.map((n, i) => <FeedNote key={n.id} note={n} notes={all} onGo={onGo} index={i} of={notes.length} above={above?.(n, i)} />)}
      {pages.left > 0 || pages.loading
        ? <Sentinel onSee={pages.more} loading={pages.loading} left={pages.left} />
        : notes.length > 0 && <p className="m-0 pt-12 pb-[50vh] text-center text-12 font-mono text-tertiary">{tn(notes.length, 'That is every note: {n}.', 'That is every note: {n}.')}</p>}
    </div>
  )
}
