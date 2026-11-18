/**
 * Round 3 lab 3, tk_810245f2: how health and time show in J's window, in
 * three variants from the quietest up. Calm in all three: no sound, nothing
 * moves at rest, nothing takes the focus from the terminal.
 *
 *   a · quiet — the title row and the window edge tint slightly yellow or
 *       red; one small time label in the title row. The suggestion shows
 *       only while the pointer is on the label.
 *   b · chip — a time chip in the tab strip takes the zone's colour; on a
 *       new zone a one-line notice under the terminal: the action and
 *       «Сделал» / «Позже» (Позже: again in 15 minutes).
 *   c · card — the chip, and a short break card over the terminal: one
 *       action for a minute and «Продолжить работу» (Esc does the same). It
 *       takes no focus and covers only its own place. In the red zone a thin
 *       red line stays on top of the terminal until a break.
 *
 * A click on the time opens the day's card (as the Timer page would show
 * it): today's work, on this project and in all, minutes in yellow and in
 * red, the breaks and the actions done. Its gear opens the settings.
 *
 * tk_caf2b06a adds reminders on a schedule and a fourth variant:
 *   d · popup — the suggestion in a small window over the terminal's lower
 *       right corner: «Сделал», «Перерыв», «Отложить» (Esc). Not modal: the
 *       terminal keeps the keyboard.
 * In every variant a break shows the same small window: the break's time,
 * "work and project time are paused", a one-line note and «Готово».
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { Bell, Pause, Plus, Settings2, X } from 'lucide-react'

import { t } from '../../../../../i18n/scope/aqua'
import { useCompare } from '../../round4/compareState'
import { SeeHint } from '../../round4/SeeHint'
import {
  ACTS, AGAIN_MIN, CLOCKS, HEALTH_DEFAULT, HEALTH_VARIANTS, LATER_MIN, addReminder, breakNow, clockOf, didIt, dueOf, endBreak, finishBreak,
  jumpTo, jumpToReminder, later, openUi, remOf, removeReminder, setHealthSettings, setReminder, startBreak, timeOfDay, useHealth, useHealthPick, zoneOf,
  type ActId, type Clock, type Due, type HealthLook, type HealthSettings, type HealthState, type Reminder, type Zone,
} from './health'

/* ------------------------------------------------------------ words */

export const actWord = (a: ActId): string => ({
  stretch: t('stretch'), water: t('water'), eat: t('eat'), far: t('look into the distance'), walk: t('take a walk'),
})[a]

/** One line for the break card: what the minute holds. */
const actHint = (a: ActId): string => ({
  stretch: t('Stand up, stretch the arms, turn the head left and right.'),
  water: t('A glass of water.'),
  eat: t('Something to eat.'),
  far: t('Twenty seconds on something far away.'),
  walk: t('A few minutes on foot.'),
})[a]

const zoneWord = (z: Zone): string => ({ green: t('Green zone'), yellow: t('Yellow zone'), red: t('Red zone') })[z]
export const ZONE_INK: Record<Zone, string> = { green: 'var(--aq-up)', yellow: 'var(--aq-wait)', red: 'var(--aq-down)' }

/** 94 → "1 ч 34 мин", 12 → "12 мин". */
export function durOf(min: number) {
  const m = Math.floor(min)
  if (m < 60) return t('{m} min', { m })
  return m % 60 ? t('{h} h {m} min', { h: Math.floor(m / 60), m: m % 60 }) : t('{h} h', { h: m / 60 })
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** Where a reminder is in its series: "every 45 min · 2 of 3, then a pause of 3 h". */
export const scheduleLine = (r: Reminder, n: number) =>
  t('every {e} · {n} of {all}, then a pause of {p}', { e: durOf(r.every), n, all: r.times, p: durOf(r.pause) })

type Shown = Exclude<Due, null>
/** The colour of a suggestion: its zone's, or jade for a reminder and the pomodoro. */
const inkOf = (due: Shown) => (due.kind === 'yellow' || due.kind === 'red' ? ZONE_INK[due.kind] : 'var(--brand)')

/** The suggestion in one line. */
function dueLine(due: Shown, h: HealthState) {
  if (due.kind === 'pomo') return t('Pomodoro: {n} min of work. A break of {r} min.', { n: h.s.pomo.work, r: h.s.pomo.rest })
  if (due.kind === 'remind') return `${capital(actWord(due.act))} · ${scheduleLine(due.r, due.n)}.`
  return `${zoneWord(due.kind)}: ${t('{t} without a break', { t: durOf(h.run) })}. ${t('Suggested:')} ${actWord(due.act)}.`
}

/* ------------------------------------------------------------ shared */

/** A frozen state and variant for K's compare view; null in the live mock. */
export const HealthFrozen = createContext<{ h: HealthState; look: HealthLook } | null>(null)

export function useHealthView() {
  const frozen = useContext(HealthFrozen)
  const live = useHealth()
  const pick = useHealthPick()
  const h = frozen?.h ?? live
  const look = frozen?.look ?? pick.look
  return { h, look, zone: zoneOf(h.run, h.s), due: dueOf(h), frozen: !!frozen }
}

/** «Сделал», «Перерыв» (a reminder, the card, the popup) and «Позже» / «Отложить» / «Продолжить работу». */
function DueButtons({ due, card, popup }: { due: Shown; card?: boolean; popup?: boolean }) {
  const brk = due.kind !== 'pomo' && (card || popup || due.kind === 'remind')
  return (
    <span className="inline-flex gap-4 shrink-0">
      <button type="button" data-nodrag className={`aq-btn ${card || popup ? 'solid' : 'line'} !h-[22px] text-11`} onClick={didIt}>
        {due.kind === 'pomo' ? t('Start the break') : t('Did it')}
      </button>
      {brk && <button type="button" data-nodrag className="aq-btn line !h-[22px] text-11" onClick={breakNow} title={t('Work and project time pause until «Done»')}>{t('Break')}</button>}
      <button type="button" data-nodrag className="aq-btn line !h-[22px] text-11" onClick={later} title={t('Everything moves {n} min on', { n: LATER_MIN })}>
        {popup ? t('Postpone') : card ? t('Continue working') : t('Later')}
      </button>
    </span>
  )
}

/** The time as one word: the counter, or the break under way. */
function TimeText({ h }: { h: HealthState }) {
  if (h.away !== null) return <>{t('break')} {clockOf(h.now - h.away)}</>
  return <>{clockOf(h.run)}</>
}

/* ------------------------------------------------------------ a: the title row */

/** The window edge in variant a: the zone's colour mixed into the border; null in the green zone and in other variants. */
export function useHealthEdge(): string | null {
  const { look, zone, h } = useHealthView()
  if (look !== 'a' || zone === 'green' || h.away !== null) return null
  return `color-mix(in srgb, ${ZONE_INK[zone]} 55%, var(--border-strong))`
}

/** Variant a: the title row's slight tint. */
export function HealthTint() {
  const { look, zone, h } = useHealthView()
  if (look !== 'a' || zone === 'green' || h.away !== null) return null
  return <span aria-hidden data-health-tint={zone} className="absolute inset-0 pointer-events-none" style={{ background: `color-mix(in srgb, ${ZONE_INK[zone]} ${zone === 'red' ? 12 : 9}%, transparent)` }} />
}

/** Variant a: the small time label in the title row; the suggestion on hover. */
export function HealthTitle({ folded }: { folded: boolean }) {
  const { look, zone, due, h, frozen } = useHealthView()
  const [hover, setHover] = useState(false)
  if (look !== 'a') return null
  const ink = due?.kind === 'pomo' ? 'var(--brand)' : zone === 'green' || h.away !== null ? 'var(--text-tertiary)' : ZONE_INK[zone]
  return (
    <span className="relative inline-flex items-center" data-nodrag onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button type="button" data-nodrag data-health-label={zone} className="font-mono tabular-nums rounded-[4px] hover:bg-[var(--aq-hover)]"
        style={{ fontSize: folded ? 9 : 11, lineHeight: folded ? '12px' : '22px', padding: folded ? '0 4px' : '0 6px', color: ink }}
        aria-label={`${t('Time without a break')}: ${clockOf(h.run)}`} onClick={() => openUi({ summary: true, settings: false })}>
        <TimeText h={h} />
      </button>
      {(hover || (frozen && !!due)) && (
        <span className="absolute right-0 z-[60] w-[300px] rounded-[8px] p-10 flex flex-col gap-6 text-12 cursor-default" role="status" data-health-hover
          style={{ top: folded ? 12 : 24, background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)' }}>
          <span className="flex items-center gap-6">
            <span className="w-[8px] h-[8px] rounded-full shrink-0" style={{ background: ZONE_INK[zone] }} />
            <span className="font-semibold">{h.away !== null ? `${t('On a break')}: ${durOf(h.now - h.away)}` : `${zoneWord(zone)} · ${t('{t} without a break', { t: durOf(h.run) })}`}</span>
          </span>
          {due && <span>{due.kind === 'yellow' || due.kind === 'red' ? `${t('Suggested:')} ${actWord(due.act)}.` : dueLine(due, h)}</span>}
          {due && <DueButtons due={due} />}
          {!due && <span className="aq-ink3 text-11">{t('Today {all}, on this project {p}.', { all: clockOf(h.day), p: clockOf(h.project) })}</span>}
        </span>
      )}
    </span>
  )
}

/* ------------------------------------------------------------ b, c: the chip */

/** Variants b and c: the time chip in the tab strip, in the zone's colour. */
export function HealthChip() {
  const { look, zone, due, h } = useHealthView()
  if (look === 'a') return null
  const ink = h.away !== null ? 'var(--brand)' : zone === 'green' ? 'var(--aq-ink2)' : ZONE_INK[zone]
  const tip = h.away !== null ? `${t('On a break')}: ${durOf(h.now - h.away)}`
    : `${zoneWord(zone)} · ${t('{t} without a break', { t: durOf(h.run) })} · ${t('Today {all}, on this project {p}.', { all: clockOf(h.day), p: clockOf(h.project) })}`
  return (
    <span className="self-center shrink-0 inline-flex items-center gap-2">
      <button type="button" data-nodrag data-health-chip={zone} className="h-[20px] px-6 inline-flex items-center gap-4 rounded-full text-11 font-mono tabular-nums"
        style={{ color: ink, background: zone === 'green' || h.away !== null ? 'var(--aq-hover)' : `color-mix(in srgb, ${ZONE_INK[zone]} 16%, transparent)` }}
        title={tip} aria-label={`${t('Time without a break')}: ${clockOf(h.run)}`} onClick={() => openUi({ summary: true, settings: false })}>
        <span className="w-[6px] h-[6px] rounded-full" style={{ background: due?.kind === 'pomo' ? 'var(--brand)' : h.away !== null ? 'var(--brand)' : ZONE_INK[zone] }} />
        <TimeText h={h} />
      </button>
    </span>
  )
}

/* ------------------------------------------------------------ the layer over the terminal */

/** The notice (b), the break card and the red line (c), the day's card and the settings. Sits in the terminal column. */
export function HealthLayer({ top, project }: { top: number; project: string }) {
  const { look, zone, due, h, frozen } = useHealthView()
  // Esc closes what is open; on the break card (c) it means «Продолжить работу»
  useEffect(() => {
    if (frozen) return
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (h.ui.settings || h.ui.summary) { openUi({ settings: false, summary: false }); return }
      if ((look === 'c' || look === 'd') && due) later()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [h.ui.settings, h.ui.summary, look, due, frozen])
  return (
    <>
      {look === 'c' && zone === 'red' && h.away === null && (
        <span aria-hidden data-health-redline className="absolute left-0 right-0 pointer-events-none z-[20]" style={{ top, height: 2, background: 'var(--aq-down)' }} />
      )}
      {look === 'b' && due && (
        <div role="status" data-health-toast={due.kind} className="absolute left-12 right-12 bottom-[62px] z-[30] h-[32px] px-10 rounded-[8px] flex items-center gap-8 text-12"
          style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', borderLeft: `3px solid ${inkOf(due)}`, boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)' }}>
          <span className="truncate flex-1 min-w-0">{dueLine(due, h)}</span>
          <DueButtons due={due} />
        </div>
      )}
      {look === 'c' && due && <BreakCard due={due} h={h} top={top} />}
      {look === 'd' && due && <Popup due={due} h={h} />}
      {h.away !== null && <BreakWindow h={h} />}
      {h.ui.summary && <DayCard h={h} zone={zone} project={project} top={top} />}
      {h.ui.settings && <SettingsCard s={h.s} top={top} />}
    </>
  )
}

function BreakCard({ due, h, top }: { due: Exclude<Due, null>; h: HealthState; top: number }) {
  const pomo = due.kind === 'pomo'
  return (
    <div role="dialog" aria-modal={false} aria-label={t('A short break')} data-health-card={due.kind}
      className="absolute left-1/2 -translate-x-1/2 z-[30] w-[360px] rounded-[10px] p-14 flex flex-col gap-8 text-12"
      style={{ top: top + 36, background: 'var(--bg-base)', border: '1px solid var(--border-default)', borderTop: `3px solid ${inkOf(due)}`, boxShadow: 'var(--shadow-lg)', color: 'var(--aq-ink)' }}>
      <div className="flex items-center">
        <span className="text-13 font-semibold">{pomo ? t('Pomodoro') : due.kind === 'remind' ? t('Reminder') : t('A short break')}</span>
        <span className="ml-auto font-mono text-11 aq-ink3">{clockOf(h.run)}</span>
      </div>
      {pomo
        ? <span>{t('Pomodoro: {n} min of work. A break of {r} min.', { n: h.s.pomo.work, r: h.s.pomo.rest })}</span>
        : (
          <>
            <span className="aq-ink2">{due.kind === 'remind' ? `${capital(scheduleLine(due.r, due.n))}.` : `${zoneWord(due.kind)}: ${t('{t} without a break', { t: durOf(h.run) })}.`}</span>
            <span className="flex flex-col"><b className="font-semibold">{capital(actWord(due.act))}</b><span className="aq-ink2">{actHint(due.act)}</span></span>
          </>
        )}
      <div className="flex items-center gap-6 pt-2">
        <DueButtons due={due} card />
        <span className="ml-auto text-10 aq-ink3 font-mono" title={t('Continue working')}>Esc</span>
      </div>
    </div>
  )
}

/** The small window of variants d and of a break: a title row and a body, over the terminal's lower right corner. Not modal. */
function MiniWindow({ label, icon, ink, onClose, closeLabel, children, data }: { label: string; icon: ReactNode; ink: string; onClose?: () => void; closeLabel?: string; children: ReactNode; data: Record<string, string> }) {
  return (
    <div role="dialog" aria-modal={false} aria-label={label} {...data} className="absolute right-16 bottom-[62px] z-[32] w-[300px] rounded-[8px] overflow-hidden text-12 flex flex-col"
      style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-lg)', color: 'var(--aq-ink)' }}>
      <div className="h-[26px] px-8 flex items-center gap-6 shrink-0" style={{ background: 'var(--r2-bar)', borderBottom: '1px solid var(--border-default)', boxShadow: `inset 0 2px 0 ${ink}` }}>
        <span style={{ color: ink }} className="inline-flex">{icon}</span>
        <span className="text-11 font-semibold">{label}</span>
        {onClose && <button type="button" data-nodrag className="aq-btn icon ml-auto !h-[20px] !w-[20px]" aria-label={closeLabel} title={closeLabel} onClick={onClose}><X size={11} /></button>}
      </div>
      <div className="p-10 flex flex-col gap-6">{children}</div>
    </div>
  )
}

/** Variant d: the suggestion as a small window. × and Esc postpone. */
function Popup({ due, h }: { due: Shown; h: HealthState }) {
  const pomo = due.kind === 'pomo'
  return (
    <MiniWindow label={pomo ? t('Pomodoro') : t('Reminder')} icon={<Bell size={12} />} ink={inkOf(due)} onClose={later} closeLabel={`${t('Postpone')} (Esc)`} data={{ 'data-health-popup': due.kind }}>
      {pomo
        ? <span>{dueLine(due, h)}</span>
        : (
          <>
            <span className="text-14 font-semibold">{capital(actWord(due.act))}</span>
            <span className="aq-ink2">{actHint(due.act)}</span>
            <span className="text-11 aq-ink3">{due.kind === 'remind' ? `${capital(scheduleLine(due.r, due.n))}.` : `${zoneWord(due.kind)}: ${t('{t} without a break', { t: durOf(h.run) })}.`}</span>
          </>
        )}
      <span className="pt-2"><DueButtons due={due} popup /></span>
    </MiniWindow>
  )
}

/** A break under way, in every variant: its time, the counters standing still, a note and «Готово». */
function BreakWindow({ h }: { h: HealthState }) {
  const [note, setNote] = useState('')
  const done = () => { finishBreak(note); setNote('') }
  return (
    <MiniWindow label={t('Break')} icon={<Pause size={12} />} ink="var(--brand)" data={{ 'data-health-break': '' }}>
      <div className="flex items-baseline gap-8">
        <span className="font-mono tabular-nums text-[22px] leading-[26px]">{clockOf(h.now - h.away!)}</span>
        <span className="text-11 aq-ink3">{t('since {t}', { t: timeOfDay(h.away!) })}</span>
      </div>
      <span className="text-11 aq-ink2">{t('Work time and project time are paused.')}</span>
      <input type="text" value={note} maxLength={120} placeholder={t('A note, if you like')} aria-label={t('Note')}
        className="h-[24px] rounded-[4px] px-6 text-12" style={{ background: 'var(--bg-surface)', color: 'var(--aq-ink)', border: '1px solid var(--border-default)' }}
        onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') done() }} />
      <span className="flex items-center gap-6">
        <button type="button" data-nodrag className="aq-btn solid !h-[22px] text-11" onClick={done}>{t('Done')}</button>
        <span className="text-10 aq-ink3">{t('Every counter starts again.')}</span>
      </span>
    </MiniWindow>
  )
}

/* ------------------------------------------------------------ the day's card */

function Row({ label, value, ink }: { label: string; value: ReactNode; ink?: string }) {
  return (
    <div className="flex items-baseline gap-8 h-[22px]">
      <span className="aq-ink3 text-11 flex-1 min-w-0 truncate">{label}</span>
      <span className="font-mono tabular-nums text-12" style={{ color: ink }}>{value}</span>
    </div>
  )
}

const CARD = { background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)' }

function DayCard({ h, zone, project, top }: { h: HealthState; zone: Zone; project: string; top: number }) {
  const green = Math.max(h.day - h.inYellow - h.inRed, 0)
  const bar = [['green', green], ['yellow', h.inYellow], ['red', h.inRed]] as const
  const breaks = h.breaks.length
  return (
    <div role="dialog" aria-label={t('Time today')} data-health-day className="absolute right-12 z-[40] w-[320px] rounded-[8px] p-12 flex flex-col gap-6 text-12" style={{ top: top + 6, ...CARD }}>
      <div className="flex items-center gap-6">
        <span className="font-semibold">{t('Time today')}</span>
        <span className="aq-ink3 text-11 font-mono">{timeOfDay(h.now)}</span>
        <button type="button" className="aq-btn icon ml-auto" aria-label={t('Settings')} title={t('Settings')} onClick={() => openUi({ settings: true, summary: false })}><Settings2 size={12} /></button>
        <button type="button" className="aq-btn icon" aria-label={t('Close')} onClick={() => openUi({ summary: false })}><X size={12} /></button>
      </div>
      <div className="flex items-baseline gap-12">
        <span className="flex flex-col">
          <span className="font-mono tabular-nums text-[22px] leading-[26px]">{clockOf(h.day)}</span>
          <span className="aq-ink3 text-10">{t('all projects')}</span>
        </span>
        <span className="flex flex-col">
          <span className="font-mono tabular-nums text-[22px] leading-[26px]">{clockOf(h.project)}</span>
          <span className="aq-ink3 text-10 truncate max-w-[150px]">{project}</span>
        </span>
      </div>
      <div className="flex h-[6px] rounded-full overflow-hidden" aria-label={t('Work today by zone')} role="img">
        {bar.map(([z, m]) => m > 0 && <span key={z} style={{ flex: m, background: ZONE_INK[z] }} />)}
      </div>
      <Row label={h.away !== null ? t('On a break') : t('Without a break now')} value={h.away !== null ? clockOf(h.now - h.away) : clockOf(h.run)} ink={h.away !== null ? 'var(--brand)' : zone === 'green' ? undefined : ZONE_INK[zone]} />
      <Row label={t('In the yellow zone')} value={durOf(h.inYellow)} ink={h.inYellow ? 'var(--aq-wait)' : undefined} />
      <Row label={t('In the red zone')} value={durOf(h.inRed)} ink={h.inRed ? 'var(--aq-down)' : undefined} />
      <Row label={t('Breaks taken')} value={breaks ? `${breaks} · ${h.breaks.map((b) => timeOfDay(b.at)).join(', ')}` : '0'} />
      {h.breaks.some((b) => b.note) && (
        <ul className="m-0 p-0 list-none flex flex-col gap-2" aria-label={t('Notes after breaks')} data-health-notes>
          {h.breaks.filter((b) => b.note).map((b) => (
            <li key={b.at} className="text-11 flex gap-6"><span className="font-mono aq-ink3 shrink-0">{timeOfDay(b.at)} · {durOf(b.len)}</span><span className="truncate">{b.note}</span></li>
          ))}
        </ul>
      )}
      <Row label={t('Actions done')} value={h.done.length ? h.done.map((d) => actWord(d.act)).join(', ') : '—'} />
      <div className="flex items-center gap-6 pt-4">
        {h.away === null
          ? <button type="button" className="aq-btn line !h-[22px] text-11" onClick={startBreak}>{t('Take a break')}</button>
          : <button type="button" className="aq-btn line !h-[22px] text-11" onClick={() => finishBreak()}>{t('Done')}</button>}
        <span className="text-10 aq-ink3 leading-[1.35]">{t('A break of {n} min sets the counter to zero.', { n: h.s.reset })}</span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ the settings */

/** The reminders in the settings: one row each — on, the action, every N min, × times, then a pause; × removes it. */
function Reminders({ s }: { s: HealthSettings }) {
  const h = useHealth()
  const field = (r: Reminder, k: 'every' | 'times' | 'pause', label: string, max: number) => (
    <input type="number" min={1} max={max} value={r[k]} aria-label={`${label} — ${actWord(r.act)}`}
      className="w-[44px] h-[22px] rounded-[4px] px-4 font-mono text-11 tabular-nums" style={{ background: 'var(--bg-surface)', color: 'var(--aq-ink)', border: '1px solid var(--border-default)' }}
      onChange={(e) => { const v = Math.round(Number(e.target.value)); if (v >= 1 && v <= max) setReminder(r.id, { [k]: v }) }} />
  )
  return (
    <div className="flex flex-col gap-4" role="group" aria-label={t('Reminders')}>
      <span className="aq-ink3 text-11">{t('Reminders')}</span>
      {s.reminders.map((r) => {
        const st = remOf(h, r)
        return (
          <div key={r.id} className="flex flex-col gap-2 rounded-[6px] p-6" style={{ border: '1px solid var(--border-default)', opacity: r.on ? 1 : 0.6 }} data-health-reminder={r.act}>
            <div className="flex items-center gap-4">
              <input type="checkbox" checked={r.on} aria-label={`${t('On')} — ${actWord(r.act)}`} onChange={(e) => setReminder(r.id, { on: e.target.checked })} />
              <select value={r.act} aria-label={t('Action')} className="h-[22px] rounded-[4px] text-11 px-2 flex-1 min-w-0" style={{ background: 'var(--bg-surface)', color: 'var(--aq-ink)', border: '1px solid var(--border-default)' }}
                onChange={(e) => setReminder(r.id, { act: e.target.value as ActId })}>
                {ACTS.map((a) => <option key={a} value={a}>{actWord(a)}</option>)}
              </select>
              <button type="button" className="aq-btn icon !h-[20px] !w-[20px]" aria-label={`${t('Remove')} ${actWord(r.act)}`} onClick={() => removeReminder(r.id)}><X size={11} /></button>
            </div>
            <div className="flex items-center gap-4 text-11 aq-ink3 flex-wrap">
              {t('every')} {field(r, 'every', t('every, min'), 600)} × {field(r, 'times', t('times'), 20)}, {t('pause')} {field(r, 'pause', t('pause, min'), 1440)} {t('min')}
            </div>
            <span className="text-10 aq-ink3 font-mono">{st.paused ? t('pause: next in {t}', { t: durOf(Math.max(st.next - h.wk, 0)) }) : t('{n} of {all} · next in {t}', { n: st.count + 1, all: r.times, t: durOf(Math.max(st.next - h.wk, 0)) })}</span>
          </div>
        )
      })}
      <button type="button" className="aq-btn line self-start !h-[22px] text-11" onClick={addReminder}><Plus size={11} />{t('Reminder')}</button>
      <span className="text-10 aq-ink3 leading-[1.35]">{t('Reminders count work minutes: a break pauses them. «Postpone» moves the whole schedule.')}</span>
    </div>
  )
}

function Num({ label, value, onChange, min = 1, max = 600 }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number }) {
  return (
    <label className="flex items-center gap-8">
      <span className="flex-1 min-w-0 aq-ink3 text-11">{label}</span>
      <input type="number" min={min} max={max} value={value} aria-label={label}
        className="w-[64px] h-[24px] rounded-[4px] px-6 font-mono text-12 tabular-nums"
        style={{ background: 'var(--bg-surface)', color: 'var(--aq-ink)', border: '1px solid var(--border-default)' }}
        onChange={(e) => { const v = Math.round(Number(e.target.value)); if (v >= min && v <= max) onChange(v) }} />
    </label>
  )
}

function Pills<T extends string | number>({ label, value, options, word, onPick }: { label: string; value: T; options: readonly T[]; word: (v: T) => string; onPick: (v: T) => void }) {
  return (
    <div className="flex items-center gap-8">
      <span className="flex-1 min-w-0 aq-ink3 text-11">{label}</span>
      <div className="flex gap-2" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button key={String(o)} type="button" role="radio" aria-checked={o === value} data-on={o === value} className="aq-btn line !h-[22px] text-11" onClick={() => onPick(o)}>{word(o)}</button>
        ))}
      </div>
    </div>
  )
}

function ActPick({ zone, s }: { zone: 'yellow' | 'red'; s: HealthSettings }) {
  const on = s.acts[zone]
  const label = zone === 'yellow' ? t('Actions in the yellow zone') : t('Actions in the red zone')
  return (
    <div className="flex flex-col gap-4">
      <span className="aq-ink3 text-11">{label}</span>
      <div className="flex gap-2 flex-wrap" role="group" aria-label={label}>
        {ACTS.map((a) => {
          const has = on.includes(a)
          return (
            <button key={a} type="button" aria-pressed={has} data-on={has} className="aq-btn line !h-[22px] text-11"
              onClick={() => setHealthSettings({ acts: { ...s.acts, [zone]: has ? on.filter((x) => x !== a) : ACTS.filter((x) => x === a || on.includes(x)) } })}>
              {actWord(a)}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export const clockWord = (c: Clock) => (c === 1 ? t('real time') : `×${c}`)
export const lookWord = (v: HealthLook): string => ({ a: t('quiet'), b: t('chip'), c: t('card'), d: t('popup') })[v]

function SettingsCard({ s, top }: { s: HealthSettings; top: number }) {
  const { look, clock, setLook, setClock } = useHealthPick()
  return (
    <div role="dialog" aria-label={t('Health and time')} data-health-settings className="absolute right-12 z-[40] w-[340px] rounded-[8px] p-12 flex flex-col gap-8 text-12 overflow-y-auto"
      style={{ top: top + 6, maxHeight: 540, ...CARD }}>
      <div className="flex items-center">
        <span className="font-semibold">{t('Health and time')}</span>
        <button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={() => openUi({ settings: false })}><X size={12} /></button>
      </div>
      <Num label={t('Yellow zone after, min')} value={s.yellow} onChange={(yellow) => setHealthSettings({ yellow })} />
      <Num label={t('Red zone after, min')} value={s.red} onChange={(red) => setHealthSettings({ red })} />
      <ActPick zone="yellow" s={s} />
      <ActPick zone="red" s={s} />
      <Reminders s={s} />
      <Num label={t('A break that sets the counter to zero, min')} value={s.reset} onChange={(reset) => setHealthSettings({ reset })} max={120} />
      <Pills label={t('Pomodoro')} value={s.pomo.on ? 'on' : 'off'} options={['off', 'on'] as const} word={(v) => (v === 'on' ? t('on') : t('off'))}
        onPick={(v) => setHealthSettings({ pomo: { ...s.pomo, on: v === 'on' } })} />
      {s.pomo.on && <Num label={t('Pomodoro: work, min')} value={s.pomo.work} onChange={(work) => setHealthSettings({ pomo: { ...s.pomo, work } })} max={120} />}
      {s.pomo.on && <Num label={t('Pomodoro: break, min')} value={s.pomo.rest} onChange={(rest) => setHealthSettings({ pomo: { ...s.pomo, rest } })} max={60} />}
      <Pills label={t('How it shows')} value={look} options={HEALTH_VARIANTS} word={(v) => `${v} · ${lookWord(v)}`} onPick={setLook} />
      <Pills label={t('Mock clock')} value={clock} options={CLOCKS} word={clockWord} onPick={setClock} />
      <p className="text-11 aq-ink3 leading-[1.4] m-0">{t('«Done» asks again in {a} min, «Later» in {l} min. Work goes on in every zone; the minutes in yellow and red are counted.', { a: AGAIN_MIN, l: LATER_MIN })}</p>
      <button type="button" className="aq-btn self-start text-11" onClick={() => setHealthSettings(HEALTH_DEFAULT)}>{t('Default settings')}</button>
    </div>
  )
}

/* ------------------------------------------------------------ the rows in the «Варианты» panel */

const lookIdea = (v: HealthLook): string => ({
  a: t('The title row and the window edge tint; the suggestion shows on hover'),
  b: t('A time chip in the tab strip; on a new zone a one-line notice with Done and Later'),
  c: t('A short break card over the terminal; Esc closes it; a red line in the red zone'),
  d: t('A small window over the lower right corner: Done, Break, Postpone; Esc postpones'),
})[v]

/** The health rows of the «Варианты» panel: the variant, the clock and the mock's own buttons. */
export function HealthSwitches() {
  const { look, clock, setLook, setClock } = useHealthPick()
  const h = useHealth()
  const zone = zoneOf(h.run, h.s)
  const [, compare] = useCompare()
  return (
    <div className="flex flex-col gap-4" data-health-switches>
      <span className="flex items-center gap-6">
        <span className="aq-label">{t('Health and time')}</span>
        <button type="button" className="ml-auto text-10 aq-ink3 hover:underline" onClick={() => compare('health')}>{t('compare')}</button>
      </span>
      <div className="flex gap-2 flex-wrap" role="radiogroup" aria-label={t('Health and time')}>
        {HEALTH_VARIANTS.map((v) => (
          <button key={v} type="button" role="radio" aria-checked={look === v} data-on={look === v} className="aq-btn line !h-[22px] text-11" title={lookIdea(v)} onClick={() => setLook(v)}>
            <span className="font-mono">{v.toUpperCase()}</span> {lookWord(v)}
          </button>
        ))}
      </div>
      <span className="text-11 aq-ink3 leading-[1.35]">{lookIdea(look)}</span>
      <SeeHint text={t('Speed up the clock, or jump to a zone below')} />
      <div className="flex gap-2 flex-wrap items-center" role="radiogroup" aria-label={t('Mock clock')}>
        <span className="text-11 aq-ink3 mr-4">{t('Mock clock')}</span>
        {CLOCKS.map((c) => (
          <button key={c} type="button" role="radio" aria-checked={clock === c} data-on={clock === c} className="aq-btn line !h-[22px] text-11" onClick={() => setClock(c)}>{clockWord(c)}</button>
        ))}
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        {(['green', 'yellow', 'red'] as const).map((z) => (
          <button key={z} type="button" className="aq-btn line !h-[22px] text-11" onClick={() => jumpTo(z)} title={t('Put the counter just before this zone')}>
            <span className="w-[6px] h-[6px] rounded-full" style={{ background: ZONE_INK[z] }} />{zoneWord(z)}
          </button>
        ))}
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        {h.away === null
          ? <button type="button" className="aq-btn line !h-[22px] text-11" onClick={startBreak}>{t('Step away')}</button>
          : <button type="button" className="aq-btn line !h-[22px] text-11" onClick={endBreak}>{t('Back to work')}</button>}
        <button type="button" className="aq-btn line !h-[22px] text-11" onClick={jumpToReminder} title={t('The clock runs on to the next reminder')}>{t('Next reminder')}</button>
        <button type="button" className="aq-btn line !h-[22px] text-11" onClick={() => openUi({ settings: true, summary: false })}>{t('Settings')}</button>
        <span className="ml-auto font-mono text-10 aq-ink3" data-health-state={zone}>{clockOf(h.run)} · {timeOfDay(h.now)}</span>
      </div>
    </div>
  )
}
