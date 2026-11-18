/**
 * Beats: while you give input and this page (or the terminal window) is in
 * front, tell the server which project — and task — you are on. The server
 * counts auto time from these beats (backend/backend/timeauto.py): a beat,
 * then the grace (60 s); the input counts while it is recent (two minutes),
 * so reading without touching anything stops counting after that, as on
 * every page.
 *
 * Every 20 s while you are here, and at once on the first input after a
 * quiet spell or when the work in front changes (another tab, another
 * project), so the time lands on the right project from the first second.
 */

import { useEffect, useRef } from 'react'

import { postJson } from '../../lib/getJson'
import type { WorkContext } from '../../lib/timer'

export const BEAT_MS = 20_000
/** Reading counts: input this recent still means you are here. */
export const READING_MS = 120_000

/** Who sends the beat: the app's pages, or the terminal window (/term). */
export type BeatSource = 'page' | 'window'

type Send = (work: WorkContext, source: BeatSource) => void

const sendBeat: Send = (work, source) => {
  // A lost beat is covered by the next one, a few seconds later; nothing to say.
  void postJson('/api/time/auto/beat', { project: work.project, task_id: work.taskId ?? '', source }).catch(() => undefined)
}

const inFront = () => typeof document !== 'undefined' && document.visibilityState === 'visible' && document.hasFocus()

/** The rule, apart from the page: tests drive it with their own clock. */
export class Beater {
  private lastInput = -Infinity
  private lastSent = -Infinity

  constructor(
    private source: BeatSource,
    private send: Send = sendBeat,
    private now: () => number = () => Date.now(),
    private present: () => boolean = inFront,
  ) {}

  /** A key, a click, the wheel, a paste, the pointer moving. */
  input(work: WorkContext | null) {
    const quiet = this.now() - this.lastSent >= BEAT_MS
    this.lastInput = this.now()
    if (quiet) this.beat(work)
  }

  /** Beat if you are here: in front, with recent input. True when sent. */
  beat(work: WorkContext | null): boolean {
    if (!work?.project || !this.present()) return false
    if (this.now() - this.lastInput > READING_MS) return false
    this.lastSent = this.now()
    this.send(work, this.source)
    return true
  }
}

/**
 * Beats from this page. `work` is read at each beat; `key` names the work
 * in front (project and task) — when it changes, a beat goes at once.
 */
export function useWorkBeats(work: () => WorkContext | null, source: BeatSource = 'page', key = '') {
  const workRef = useRef(work)
  workRef.current = work
  const beater = useRef<Beater | null>(null)
  if (!beater.current) beater.current = new Beater(source)

  useEffect(() => {
    const b = beater.current!
    let lastMove = 0
    const mark = () => b.input(workRef.current())
    const move = () => { const tv = Date.now(); if (tv - lastMove > 1000) { lastMove = tv; mark() } }
    const opts = { passive: true, capture: true } as const
    const events = ['keydown', 'pointerdown', 'wheel', 'paste'] as const
    for (const e of events) window.addEventListener(e, mark, opts)
    window.addEventListener('pointermove', move, opts)
    const id = window.setInterval(() => b.beat(workRef.current()), BEAT_MS)
    return () => {
      window.clearInterval(id)
      for (const e of events) window.removeEventListener(e, mark, opts)
      window.removeEventListener('pointermove', move, opts)
    }
  }, [])

  useEffect(() => {
    if (key) beater.current!.beat(workRef.current())
  }, [key])
}
