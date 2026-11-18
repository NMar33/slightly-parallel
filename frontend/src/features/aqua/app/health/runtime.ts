/**
 * The health counter's clock in the terminal window: the window's own
 * input, the computer's input (the server's idle reading), and a step
 * every few seconds. Called once in the window; does nothing while health
 * is off.
 */

import { useEffect } from 'react'

import { getJson } from '../../../../lib/getJson'
import { useTimeAuto } from '../../../../lib/timer'
import { SETTINGS_KEY, adoptServerBreak, flushDay, nowMs, reloadSettings, setProject, tick, useHealth } from './health'

/** A step this often with no input: the label moves by whole minutes, so nothing redraws in between. */
export const STEP_MS = 15_000

type BreakStatus = { on: boolean; since?: string }

export function useHealthRuntime(project: string) {
  const on = useHealth().s.on
  const auto = useTimeAuto()

  useEffect(() => { setProject(project) }, [project])

  // The window's own input: keys, clicks, the wheel, pastes, the pointer moving (once a second at most).
  useEffect(() => {
    if (!on) return
    let last = 0
    const mark = () => { const now = nowMs(); if (now - last >= 1000) { last = now; tick(now) } }
    const opts = { passive: true, capture: true } as const
    const events = ['keydown', 'pointerdown', 'wheel', 'paste', 'pointermove'] as const
    for (const e of events) window.addEventListener(e, mark, opts)
    const id = window.setInterval(() => tick(0), STEP_MS)
    tick(0)
    return () => {
      window.clearInterval(id)
      for (const e of events) window.removeEventListener(e, mark, opts)
    }
  }, [on])

  // The computer's input anywhere, as the server reads it (null: no idle source here).
  const idle = auto.data?.idle_sec
  const at = auto.dataUpdatedAt
  useEffect(() => {
    if (!on || idle === null || idle === undefined || !at) return
    tick(at - idle * 1000)
  }, [on, idle, at])

  // A break the server holds (taken in another window, or before a reload) is under way here too.
  useEffect(() => {
    if (!on) return
    const ctl = new AbortController()
    getJson<BreakStatus>('/api/time/auto/break', ctl.signal)
      .then((b) => adoptServerBreak(b.on, b.since ? Date.parse(b.since) : null), () => undefined)
    return () => ctl.abort()
  }, [on])

  // Settings changed on the Settings page: through the server's prefs on focus, or at once in this page.
  useEffect(() => {
    const pref = (e: Event) => { if ((e as CustomEvent<{ key?: string }>).detail?.key === SETTINGS_KEY) reloadSettings() }
    const focus = () => {
      void getJson<{ prefs?: Record<string, string> }>('/api/prefs').then((p) => {
        const v = p.prefs?.[SETTINGS_KEY]
        if (typeof v === 'string') { try { localStorage.setItem(SETTINGS_KEY, v) } catch { /* private mode */ } reloadSettings() }
      }, () => undefined)
    }
    window.addEventListener('sp:pref', pref)
    window.addEventListener('focus', focus)
    window.addEventListener('beforeunload', flushDay)
    return () => {
      window.removeEventListener('sp:pref', pref)
      window.removeEventListener('focus', focus)
      window.removeEventListener('beforeunload', flushDay)
    }
  }, [])
}
