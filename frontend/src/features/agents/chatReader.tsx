/**
 * The chat reader: the captured turns of one chat, or of a whole history
 * read as one, user and agent in full, with find-in-chat, folds, the
 * prompt tags and what each turn changed.
 */

import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ExternalLink } from 'lucide-react'

import { EmptyState, LoadingSkeleton } from '../../components/states'
import { Button } from '../../components/primitives'
import { fmtDay } from './parts'
import { approx, fmtMinutes, type ProfileSession } from './profile'
import { useSessionTurns } from './sessionTurns'
import { WorkLine } from './workLine'
import { PromptTag, TurnMsg, type PromptMark } from './chatMessage'
import { TEXT_SIZES, useReadingPrefs, useStretches, type ReadingPrefs } from './chatReaderHooks'

import { t } from '../../i18n/scope/views'
export function ChatReader({ sessions, onOpenLens, onOpenTask, fill = false, position, onPrev, onNext, find: findProp, onFind, extra, markTurn, promptMarks, reading, turnExtra }: {
  /** One session — the reader; several — the whole history, oldest first. */
  sessions: ProfileSession[]
  onOpenLens: (lens: string, id: string) => void
  onOpenTask?: (id: string) => void
  fill?: boolean
  position?: { index: number; total: number }
  /** Older / newer session. */
  onPrev?: () => void
  onNext?: () => void
  /** Controlled find — a host with a find of its own (across sessions)
   *  hands the needle down so one box drives both the rail and the text. */
  find?: string
  onFind?: (v: string) => void
  /** Rendered in the header beside the meta line — who this chat is with.
   *  A function gets the chat in view, which in the whole history follows
   *  the scroll. */
  extra?: ReactNode | ((session: ProfileSession) => ReactNode)
  /** The turn a link brought you to — ringed, scrolled into view. */
  markTurn?: number
  /** Turns that carried a prompt, by session then turn: the tag line and the tint. */
  promptMarks?: Record<string, Record<number, PromptMark>>
  /** Set by the host instead of by the reader's own buttons, which hide. */
  reading?: ReadingPrefs
  /** Drawn at the end of a turn's header line — the host's own mark (the ★). */
  turnExtra?: (session: ProfileSession, turn: number, userText: string) => ReactNode
}) {
  const single = sessions.length === 1 ? sessions[0] : undefined
  // One round trip for the whole history: the ids in one request, the turns
  // back keyed by session. 164 sessions used to be 164 requests.
  const batch = useSessionTurns(sessions)
  const details = useMemo(
    () =>
      sessions.map((s) => ({
        data: batch.data ? { turns: batch.data[s.id] ?? [] } : undefined,
        isLoading: batch.isLoading,
        error: batch.error,
      })),
    [sessions, batch.data, batch.isLoading, batch.error],
  )
  const [ownFind, setOwnFind] = useState('')
  const controlled = findProp !== undefined
  const find = controlled ? findProp : ownFind
  // Filtering follows the typed text at low priority — keystrokes stay
  // responsive while a large history re-filters in the background.
  const deferredFind = useDeferredValue(find)
  const setFind = controlled ? (onFind ?? (() => {})) : setOwnFind
  const { md, reverse, size, showWork, flipMd, flipOrder, pickSize } = useReadingPrefs(reading)
  const [expandedTurns, setExpandedTurns] = useState<Set<string>>(new Set())
  // Stable across renders, so the memo'd TurnMsg is not re-rendered by a
  // fresh closure every time the reader re-renders.
  const toggleMsg = useCallback((mk: string) => {
    setExpandedTurns((s) => {
      const n = new Set(s)
      if (n.has(mk)) n.delete(mk); else n.add(mk)
      return n
    })
  }, [])
  const topRef = useRef<HTMLDivElement>(null)
  const key = sessions.map((s) => s.id).join('|')
  useEffect(() => { if (!controlled) setOwnFind(''); setExpandedTurns(new Set()); topRef.current?.scrollTo?.({ top: 0 }) }, [key, controlled])

  // Scroll the marked turn into view once its session has loaded.
  const markedRef = useRef<HTMLElement | null>(null)
  const loadedKey = details.map((d) => (d.data ? '1' : '0')).join('')
  // Once per mark: the turn may be drawn a moment later (a long chat is
  // drawn in stretches), and drawing more must not pull the reader back.
  const scrolledFor = useRef('')
  const markKey = `${markTurn}|${key}|${loadedKey}`
  useEffect(() => {
    if (markTurn == null || scrolledFor.current === markKey || !markedRef.current) return
    markedRef.current.scrollIntoView({ block: 'center' })
    scrolledFor.current = markKey
  })

  const loading = details.some((d) => d.isLoading)
  const failed = details.find((d) => d.error)
  const needle = deferredFind.trim().toLowerCase()
  const LIMIT = 900

  // One flat list: [session header?, turns…] per session, oldest first;
  // the order toggle reverses turns (and sessions with them).
  const ordered = useMemo(() => {
    const groups = sessions.map((s, i) => {
      const turns = (details[i]?.data?.turns ?? []).filter(
        (it) => !needle || `${it.user}\n${it.agent}`.toLowerCase().includes(needle),
      )
      return { session: s, turns: reverse ? turns.slice().reverse() : turns }
    }).filter((g) => g.turns.length > 0)
    return reverse ? groups.slice().reverse() : groups
  }, [sessions, details, needle, reverse])
  const totalShown = ordered.reduce((n, g) => n + g.turns.length, 0)

  const { drawn, shownGroups, turnsLeft, moreTurnsRef, moreRef, drawTo } = useStretches({
    ordered, single: !!single, resetKey: `${key}|${reverse}|${needle}`, markTurn, scroller: topRef,
  })

  // The whole history: the header speaks for the chat at the top of the view.
  const [inView, setInView] = useState('')
  useEffect(() => {
    const root = topRef.current
    if (single || !root) return
    const io = new IntersectionObserver((entries) => {
      const seen = entries.filter((e) => e.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (seen[0]) setInView((seen[0].target as HTMLElement).dataset.session ?? '')
    }, { root, rootMargin: '0px 0px -80% 0px' })
    root.querySelectorAll('[data-session]').forEach((el) => io.observe(el))
    return () => io.disconnect()
  }, [single, key, loadedKey, reverse, drawn]) // chats drawn later are watched too
  const viewIdx = single ? -1 : Math.max(0, sessions.findIndex((s) => s.id === inView))
  const viewing = single ?? sessions[viewIdx]
  const scrollToSession = (i: number) => {
    const s = sessions[i]
    if (!s) return
    const el = topRef.current?.querySelector<HTMLElement>(`[data-session="${s.id}"]`)
    if (el) { el.scrollIntoView({ block: 'start' }); return }
    // Not drawn yet: draw up to it, then go there.
    const at = ordered.findIndex((g) => g.session.id === s.id)
    if (at >= 0) {
      drawTo(at)
      requestAnimationFrame(() => topRef.current?.querySelector<HTMLElement>(`[data-session="${s.id}"]`)?.scrollIntoView({ block: 'start' }))
    }
  }
  const meta = single
    ? `${position ? `${position.total - position.index} of ${position.total} · ` : ''}${single.id} · ${fmtDay(single.created_date)} ${single.start_time}–${single.end_time} · ${single.turns_n} turns · ${sessionTime(single)}`
    : viewing
      ? `${viewIdx + 1} of ${sessions.length} · ${viewing.id} · ${fmtDay(viewing.created_date)} ${viewing.start_time}–${viewing.end_time} · ${viewing.turns_n} turns · ${sessionTime(viewing)}`
      : t('the whole history · {length} sessions · {v} turns', { length: sessions.length, v: sessions.reduce((n, s) => n + s.turns_n, 0) })
  // In the whole history the arrows move from chat to chat within it.
  const older = single ? onPrev : viewIdx > 0 ? () => scrollToSession(viewIdx - 1) : undefined
  const newer = single ? onNext : viewIdx < sessions.length - 1 ? () => scrollToSession(viewIdx + 1) : undefined

  return (
    <div className={`flex flex-col gap-8 min-w-0 rounded-card border border-border-subtle bg-base/40 ${fill ? 'h-full min-h-0' : ''}`}>
      <div className="flex items-center gap-8 px-10 py-6 border-b border-border-subtle flex-wrap">
        {(older || newer || onPrev || onNext) && (
          <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden shrink-0">
            <button type="button" onClick={older} disabled={!older} aria-label={t('Older chat')} title={t('older')} className="px-6 h-20 text-11 text-secondary hover:bg-hover disabled:opacity-40">‹</button>
            <button type="button" onClick={newer} disabled={!newer} aria-label={t('Newer chat')} title={t('newer')} className="px-6 h-20 text-11 text-secondary hover:bg-hover disabled:opacity-40 border-l border-border-subtle">›</button>
          </span>
        )}
        <div className="min-w-0 flex items-center gap-8">
          <div className="text-10 font-mono text-tertiary truncate">{meta}</div>
          {typeof extra === 'function' ? (viewing ? extra(viewing) : null) : extra}
        </div>
        <input
          value={find}
          onChange={(e) => setFind(e.currentTarget.value)}
          placeholder={t('find in chat')}
          aria-label={t('Find in chat')}
          className="ml-auto w-[160px] rounded-input border border-border-subtle bg-surface px-8 py-3 text-12 text-primary placeholder:text-tertiary focus:outline-none focus:border-brand"
        />
        {!reading && <ReaderButtons md={md} size={size} reverse={reverse} onMd={flipMd} onSize={pickSize} onOrder={flipOrder} />}
        {viewing && (
          <button type="button" onClick={() => onOpenLens('sessions', viewing.id)} className="inline-flex items-center gap-4 text-11 font-mono text-secondary hover:text-primary rounded-input px-6 py-3 hover:bg-hover" title={t('Open this chat on the Chats page')}>
            <ExternalLink size={11} aria-hidden /> {t('open')}
          </button>
        )}
      </div>
      <div ref={topRef} className={`flex flex-col gap-10 px-10 pb-10 overflow-y-auto ${fill ? 'flex-1 min-h-0' : 'max-h-[560px]'}`} role="log" aria-label={t('Chat turns')}>
        {loading && <LoadingSkeleton variant="text" count={3} label={t('Loading the chat')} />}
        {failed && <div className="text-12 text-status-red">{t('Could not load the chat:')}{' '}{(failed.error as Error).message}</div>}
        {!loading && totalShown === 0 && needle && <EmptyState compact title={t('No turn contains “{find}”.', { find })} />}
        {shownGroups.map((g) => (
          <div key={g.session.id} data-session={g.session.id} className="flex flex-col gap-10 min-w-0 scroll-mt-4">
            {!single && (
              <button type="button" onClick={() => onOpenLens('sessions', g.session.id)}
                className="text-left text-10 font-mono text-tertiary hover:text-primary border-t border-border-subtle pt-6 truncate"
                title={t('Open this chat on the Chats page')}>
                {fmtDay(g.session.created_date)} {g.session.start_time} · {g.session.id} · {g.session.turns_n} {t('turns ·')}{' '}{g.session.l1}
              </button>
            )}
            {g.turns.map((it) => {
              const tk = `${g.session.id}:${it.n}`
              const sides = ([['user', it.user], ['agent', it.agent]] as const)
                .filter(([, body]) => body.length > 0)
              // Each side folds on its own key; the turn line takes every
              // long side at once, which is what you want when a question
              // and its answer are both walls of text.
              const longKeys = sides
                .filter(([, body]) => body.length > LIMIT)
                .map(([who]) => `${tk}:${who}`)
              const allOpen = longKeys.length > 0 && longKeys.every((k) => expandedTurns.has(k))
              return (
                <article
                  key={tk}
                  ref={markTurn != null && it.n === markTurn ? markedRef : undefined}
                  className={`flex flex-col gap-6 ${markTurn != null && it.n === markTurn ? 'rounded-card ring-2 ring-brand/40 bg-brand-glow p-6 -m-6' : ''}`}
                  // The whole history is hundreds of turns; the browser lays out
                  // and paints only the ones near the viewport.
                  style={{ contentVisibility: 'auto', containIntrinsicSize: 'auto 160px' } as React.CSSProperties}
                  aria-label={t('turn {n}', { n: it.n })}
                  aria-current={markTurn != null && it.n === markTurn ? 'true' : undefined}
                >
                  <div className="text-10 font-mono text-tertiary flex items-center gap-8">
                    <span>{t('turn')}{' '}{it.n} · {it.at}</span>
                    {longKeys.length > 0 && (
                      <Button
                        variant="link"
                        size="bare"
                        aria-expanded={allOpen}
                        title={allOpen ? t('Collapse every long message in this turn') : t('Show every long message in this turn')}
                        onClick={() => setExpandedTurns((s) => {
                          const n = new Set(s)
                          for (const k of longKeys) { if (allOpen) n.delete(k); else n.add(k) }
                          return n
                        })}
                      >
                        {allOpen ? t('collapse turn') : t('whole turn')}
                      </Button>
                    )}
                    {turnExtra?.(g.session, it.n, sides.find(([w]) => w === 'user')?.[1] ?? '')}
                  </div>
                  {promptMarks?.[g.session.id]?.[it.n] && <PromptTag mark={promptMarks[g.session.id]![it.n]!} />}
                  {sides.map(([who, body]) => {
                    const mk = `${tk}:${who}`
                    const open = expandedTurns.has(mk)
                    const isPrompt = who === 'user' && Boolean(promptMarks?.[g.session.id]?.[it.n])
                    return (
                      <div key={who} className={isPrompt ? 'rounded-card border-l-2 border-brand bg-brand-glow pl-6' : undefined}>
                      <TurnMsg
                        who={who}
                        text={open || body.length <= LIMIT ? body : body.slice(0, LIMIT) + '…'}
                        full={body}
                        long={body.length > LIMIT}
                        open={open}
                        msgKey={mk}
                        onToggle={toggleMsg}
                        needle={needle}
                        md={md}
                        size={size}
                        onOpenTask={onOpenTask}
                      />
                      </div>
                    )
                  })}
                  {sides.length === 0 && <div className="text-11 text-tertiary italic">{t('empty turn')}</div>}
                  {it.work && showWork && <WorkLine work={it.work} sessionId={g.session.id} />}
                </article>
              )
            })}
          </div>
        ))}
        {turnsLeft > 0 && (
          <div ref={moreTurnsRef} className="text-11 font-mono text-tertiary text-center py-8">
            {turnsLeft} {t('more turns below…')}
          </div>
        )}
        {turnsLeft === 0 && !single && drawn < ordered.length && (
          <div ref={moreRef} className="text-11 font-mono text-tertiary text-center py-8">
            {ordered.length - drawn} {t('more chats below…')}
          </div>
        )}
      </div>
    </div>
  )
}

/** The reader's own setting buttons — markdown, text size, order — where no host hands them down. */
function ReaderButtons({ md, size, reverse, onMd, onSize, onOrder }: {
  md: boolean
  size: number
  reverse: boolean
  onMd: () => void
  onSize: (px: number) => void
  onOrder: () => void
}) {
  return (
    <>
    <button type="button" onClick={onMd} aria-pressed={md} title={md ? t('Showing formatted text. Click for raw text') : t('Showing raw text. Click for formatted text')}
      className={`h-20 px-6 rounded-input border text-10 font-mono ${md ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle text-tertiary hover:text-primary'}`}>
      {t('md')}
    </button>
    <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden shrink-0" role="group" aria-label={t('Text size')}>
      {TEXT_SIZES.map((it, i) => (
        <button
          key={it.px}
          type="button"
          onClick={() => onSize(it.px)}
          aria-pressed={size === it.px}
          aria-label={it.label}
          title={it.hint}
          style={{ fontSize: it.glyphPx }}
          className={`px-6 h-20 font-mono leading-none ${i > 0 ? 'border-l border-border-subtle' : ''} ${
            size === it.px ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'
          }`}
        >
          {it.glyph}
        </button>
      ))}
    </span>
    <button type="button" onClick={onOrder} aria-pressed={reverse} title={reverse ? t('Newest first. Click for oldest first') : t('Oldest first. Click for newest first')}
      className={`h-20 px-6 rounded-input border text-10 font-mono ${reverse ? 'border-brand bg-brand-glow text-primary' : 'border-border-subtle text-tertiary hover:text-primary'}`}>
      {reverse ? t('↑ new first') : t('↓ oldest first')}
    </button>
    </>
  )
}

/** "1h 10m · agent 40m · waiting 30m" — one session's three times. */
function sessionTime(s: ProfileSession): string {
  if (s.agent_min == null) return fmtMinutes(s.duration_min)
  const a = approx(s.timed === 'approx')
  const helpers = s.helper_min ? ` · helpers ${fmtMinutes(s.helper_min)}` : ''
  return `${fmtMinutes(s.duration_min)} · agent ${a}${fmtMinutes(s.agent_min)} · waiting ${a}${fmtMinutes(s.waiting_min ?? 0)}${helpers}`
}
