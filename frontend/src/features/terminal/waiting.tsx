/**
 * When an agent turns to you, you hear about it — even with Slightly Parallel in a
 * background tab. The terminal list already knows each terminal's state
 * (working → waiting is the agent handing you the turn); this watches it
 * once, for the whole app:
 *
 * - the tab title carries the count, "(2) Kanban — Slightly Parallel";
 * - a screen reader hears "b-and-p is waiting for you" (a polite live region);
 * - with the switch on (terminal settings; the browser asks once), a
 *   desktop notification — only while Slightly Parallel is not in front — and a
 *   click on it brings the tab forward with that terminal open. With the
 *   switch on the list keeps being read in a hidden tab: that is the tab
 *   the notification is for.
 *
 * Only a change is news: a terminal already waiting when the page loads
 * counts in the title but raises nothing.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'

import { persistPref, readPref } from '../../lib/uiPrefs'
import { showTerminal, useTerminalsWatch, type TermSession, type TermState } from '../../lib/terminal'
import { t } from '../../i18n/scope/system'

/** The terminals that have just turned to "waiting" since the last look. */
export function newlyWaiting(before: ReadonlyMap<string, TermState> | null, sessions: TermSession[]): TermSession[] {
  if (!before) return []
  return sessions.filter((s) => s.state === 'waiting' && before.has(s.id) && before.get(s.id) !== 'waiting')
}

const COUNT = /^\(\d+\) /

/** The title with the waiting count in front (or without it at zero). */
export function titleWith(title: string, waiting: number): string {
  const bare = title.replace(COUNT, '')
  return waiting > 0 ? `(${waiting}) ${bare}` : bare
}

/* ------------------------------------------------ the notification switch */

const PREF = 'sp-waiting-notify'
const listeners = new Set<() => void>()
const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
const supported = () => typeof window !== 'undefined' && 'Notification' in window

function notifyOn(): boolean {
  return supported() && readPref(PREF) === '1' && Notification.permission === 'granted'
}

/**
 * The switch in the terminal settings. Turning it on asks the browser —
 * which only allows asking from a click, so this is where it happens.
 * Returns the state and, when the browser has said no, why nothing shows.
 */
export function useWaitingNotify(): { on: boolean; supported: boolean; blocked: boolean; set: (on: boolean) => Promise<void> } {
  const on = useSyncExternalStore(subscribe, notifyOn)
  const blocked = supported() && Notification.permission === 'denied'
  const set = async (want: boolean) => {
    if (!supported()) return
    if (want && Notification.permission === 'default') await Notification.requestPermission()
    persistPref(PREF, want && Notification.permission === 'granted' ? '1' : '0')
    listeners.forEach((l) => l())
  }
  return { on, supported: supported(), blocked, set }
}

/* ------------------------------------------------------------ the watcher */

export function WaitingNotice() {
  // The app's one poll of the list; it runs on in a hidden tab only when a
  // notification could come of it.
  const notify = useSyncExternalStore(subscribe, notifyOn)
  const sessions = useTerminalsWatch(notify).data?.sessions
  const before = useRef<Map<string, TermState> | null>(null)
  const waitingRef = useRef(0)
  const [said, setSaid] = useState('')

  useEffect(() => {
    if (!sessions) return
    const turned = newlyWaiting(before.current, sessions)
    before.current = new Map(sessions.map((s) => [s.id, s.state]))
    waitingRef.current = sessions.filter((s) => s.state === 'waiting').length
    document.title = titleWith(document.title, waitingRef.current)
    if (!turned.length) return
    setSaid(turned.map((s) => t('{name} is waiting for you', { name: s.label })).join('. '))
    const away = document.visibilityState === 'hidden' || !document.hasFocus()
    if (!away || !notifyOn()) return
    for (const s of turned) {
      // Some browsers refuse a page's own Notification (only a service
      // worker may make one): the title and the live region still say it.
      let n: Notification
      try {
        n = new Notification(t('{name} is waiting for you', { name: s.label }), {
          body: [s.project, s.program].filter(Boolean).join(' · '),
          tag: `sp-waiting-${s.id}`,
        })
      } catch { return }
      n.onclick = () => { window.focus(); showTerminal(s.id); n.close() }
    }
  }, [sessions])

  // Every page writes its own title on arrival; put the count back on it.
  useEffect(() => {
    const el = document.querySelector('title')
    if (!el) return
    const mo = new MutationObserver(() => {
      const want = titleWith(document.title, waitingRef.current)
      if (document.title !== want) document.title = want
    })
    mo.observe(el, { childList: true, characterData: true, subtree: true })
    return () => mo.disconnect()
  }, [])

  return <div aria-live="polite" className="sr-only">{said}</div>
}
