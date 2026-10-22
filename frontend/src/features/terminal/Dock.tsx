/**
 * The terminal's two fixtures in the app shell: the top bar's button and
 * the drawer at the bottom of every page.
 *
 * They are on every page, so they are small. The drawer's body — the deck
 * of tabs and screens (Deck.tsx, Screen.tsx) — is loaded the first time
 * the drawer opens; a session that never opens the terminal never loads it.
 */

import { Suspense, lazy } from 'react'
import { SquareTerminal } from 'lucide-react'

import { showTerminal, toggleDock, useDock, useTerminalStatus, useTerminals } from '../../lib/terminal'
import { StateDot } from './parts'
import { t, tn } from '../../i18n/scope/system'

const DrawerBody = lazy(() => import('./Deck').then((m) => ({ default: m.Drawer })))

/** The drawer, when it is open. Closed, nothing of it is mounted (or loaded). */
export function Drawer() {
  const dock = useDock()
  if (!dock.open) return null
  return <Suspense fallback={null}><DrawerBody /></Suspense>
}

/** The top bar's way in: how many terminals, and whether one waits for you. */
export function TerminalButton() {
  const dock = useDock()
  const st = useTerminalStatus().data
  const list = useTerminals().data
  const counts = list?.counts
  const waiting = counts?.waiting ?? 0
  const working = counts?.working ?? 0
  const live = (list?.sessions ?? []).filter((s) => s.state !== 'ended').length
  const word = !st?.enabled ? t('Terminal (off)') : waiting ? t('{n} waiting for you', { n: waiting }) : working ? t('{n} working', { n: working }) : tn(live, '{n} terminal', '{n} terminals')
  return (
    <button type="button" onClick={() => {
      if (waiting && !dock.open) {
        const w = list?.sessions.find((s) => s.state === 'waiting')
        if (w) { showTerminal(w.id); return }
      }
      toggleDock()
    }} aria-pressed={dock.open} title={`${word} — ${t('` shows and hides the terminal')}`}
      className={`relative h-[28px] px-8 inline-flex items-center gap-6 rounded-input text-12 font-mono ${dock.open ? 'bg-hover text-primary' : 'text-secondary hover:bg-hover hover:text-primary'}`}>
      <SquareTerminal size={14} aria-hidden />
      {st?.enabled && live > 0 && <span className="tabular-nums">{live}</span>}
      {waiting > 0 ? <StateDot state="waiting" size={7} /> : working > 0 ? <StateDot state="working" size={7} /> : null}
    </button>
  )
}
