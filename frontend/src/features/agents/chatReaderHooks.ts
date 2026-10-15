/**
 * The reader's state that is not the chat itself: the reading settings it
 * keeps when no host hands them down, and how much of a long history is
 * drawn — a few chats and a stretch of turns at a time, more as the
 * reader nears the end.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'

import { persistPref, readPref } from '../../lib/uiPrefs'

import { t } from '../../i18n/scope/views'
/** A reader preference that outlives the session (markdown on, order…) — through uiPrefs. */
export function readPrefOr(key: string, fallback: string): string {
  return readPref(key) ?? fallback
}

/**
 * Reading sizes: the same message, scanned or read. The glyph renders at
 * its own scale, so the control shows what it does — a · A · A.
 */
export const TEXT_SIZES = [
  { px: 12, glyph: 'a', glyphPx: 10, label: t('Small text'), hint: t('small') },
  { px: 14, glyph: 'A', glyphPx: 12, label: t('Medium text'), hint: t('medium') },
  { px: 16, glyph: 'A', glyphPx: 14, label: t('Large text'), hint: t('large') },
] as const

/**
 * Reading settings a host owns. The agent page has no settings panel, so
 * the reader keeps its own buttons there; the chats page holds all of them
 * under one gear and hands the result down, and the buttons go away.
 */
export interface ReadingPrefs {
  /** Text size in px: 12, 14 or 16. */
  size: number
  md: boolean
  /** Newest turn first. */
  reverse: boolean
  /** Show the commits and files a turn made. */
  work: boolean
}

/** The settings in force: the host's when it hands them down, else the reader's own. */
export function useReadingPrefs(reading: ReadingPrefs | undefined) {
  const [ownMd, setMd] = useState(() => readPrefOr('sp-chat-md', 'on') !== 'off')
  const [ownReverse, setReverse] = useState(() => readPrefOr('sp-chat-order', 'normal') === 'reverse')
  const flipMd = () => setMd((v) => { persistPref('sp-chat-md', v ? 'off' : 'on'); return !v })
  const flipOrder = () => setReverse((v) => { persistPref('sp-chat-order', v ? 'normal' : 'reverse'); return !v })
  const [ownSize, setSize] = useState(() => {
    const n = Number(readPrefOr('sp-chat-size', '12'))
    return TEXT_SIZES.some((it) => it.px === n) ? n : 12
  })
  const pickSize = (px: number) => { setSize(px); persistPref('sp-chat-size', String(px)) }
  // A host with a settings panel decides; without one the buttons above do.
  return {
    md: reading ? reading.md : ownMd,
    reverse: reading ? reading.reverse : ownReverse,
    size: reading ? reading.size : ownSize,
    showWork: reading ? reading.work : true,
    flipMd, flipOrder, pickSize,
  }
}

const STEP = 8
const TURN_STEP = 120

interface Group { session: { id: string }; turns: Array<{ n: number }> }

/**
 * The whole history is drawn a few chats at a time, more as the reader
 * nears the end: 270 chats drawn at once froze the page. And a stretch of
 * turns at a time: one chat of 1,500 turns drawn at once is 54,000
 * elements, and the page stops answering while it is built.
 */
export function useStretches<G extends Group>({ ordered, single, resetKey, markTurn, scroller }: {
  ordered: G[]
  /** One chat: every chat of it is drawn, only its turns come in stretches. */
  single: boolean
  /** A new chat, order or find starts again from the top. */
  resetKey: string
  markTurn?: number
  scroller: RefObject<HTMLDivElement>
}) {
  const [drawn, setDrawn] = useState(STEP)
  useEffect(() => setDrawn(STEP), [resetKey])
  const chatGroups = useMemo(() => (single ? ordered : ordered.slice(0, drawn)), [single, ordered, drawn])
  const [turnsDrawn, setTurnsDrawn] = useState(TURN_STEP)
  useEffect(() => setTurnsDrawn(TURN_STEP), [resetKey])
  // The turn a link points at is drawn from the start, with some after it.
  // Drawing only grows, so running again as the chats load is harmless.
  useEffect(() => {
    if (markTurn == null) return
    let before = 0
    for (const g of chatGroups) {
      const at = g.turns.findIndex((it) => it.n === markTurn)
      if (at >= 0) { setTurnsDrawn((d) => Math.max(d, before + at + 40)); return }
      before += g.turns.length
    }
  }, [markTurn, chatGroups])
  const { shownGroups, turnsLeft } = useMemo(() => {
    let room = turnsDrawn
    const out: G[] = []
    for (const g of chatGroups) {
      if (room <= 0) break
      out.push(g.turns.length <= room ? g : { ...g, turns: g.turns.slice(0, room) })
      room -= g.turns.length
    }
    return { shownGroups: out, turnsLeft: chatGroups.reduce((n, g) => n + g.turns.length, 0) - out.reduce((n, g) => n + g.turns.length, 0) }
  }, [chatGroups, turnsDrawn])
  const moreTurnsRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const root = scroller.current, el = moreTurnsRef.current
    if (!root || !el) return
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) setTurnsDrawn((d) => d + TURN_STEP)
    }, { root, rootMargin: '1500px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [scroller, turnsDrawn, turnsLeft])
  const moreRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const root = scroller.current, el = moreRef.current
    if (single || !root || !el) return
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) setDrawn((d) => d + STEP)
    }, { root, rootMargin: '1500px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [scroller, single, drawn, ordered.length])
  /** Draw the history down to the chat at `at` in `ordered` — its turns too. */
  const drawTo = useCallback((at: number) => {
    setDrawn((d) => Math.max(d, at + STEP))
    const before = ordered.slice(0, at).reduce((n, g) => n + g.turns.length, 0)
    setTurnsDrawn((d) => Math.max(d, before + 40))
  }, [ordered])
  return { drawn, shownGroups, turnsLeft, moreTurnsRef, moreRef, drawTo }
}
