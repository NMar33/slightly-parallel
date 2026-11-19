/**
 * Health and time in the terminal window, variant a «quiet» (tk_810245f2,
 * tk_caf2b06a), as chosen in the mockup (design/round3/lab3/Health.tsx):
 *
 * - the title row and the window edge tint slightly yellow, then red, by
 *   continuous work time; one small time label in the title row, also
 *   when the row is folded;
 * - the suggestion and «Сделал» / «Перерыв» / «Позже» show only while the
 *   pointer is on the label;
 * - a click on the label opens the day's card: today on this project and
 *   in all (the server's /api/time/summary), minutes in yellow and red,
 *   breaks, actions done; its gear opens the settings;
 * - a break shows a small window: its time, a note and «Готово».
 *
 * Calm: no sound, nothing moves at rest, and the label and its buttons
 * never take the keyboard from the terminal (mousedown is not let through).
 */

import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pause, Plus, Settings2, X } from 'lucide-react'

import { Segmented } from '../../../../components/Segmented'
import { getJson } from '../../../../lib/getJson'
import { t } from '../../../../i18n/scope/aqua'
import {
  ACTS, AGAIN_MIN, HEALTH_DEFAULT, LATER_MIN, addReminder, breakNow, clockOf, didIt, dueOf, finishBreak, later, openUi, remOf,
  removeReminder, setHealthSettings, setReminder, startBreak, timeOfDay, useHealth, zoneOf,
  type ActId, type Due, type HealthSettings as Settings, type HealthState, type Reminder, type Zone,
} from './healthModel'

/* ------------------------------------------------------------ words */

export const actWord = (a: ActId): string => ({
  stretch: t('stretch'), water: t('water'), eat: t('eat'), far: t('look into the distance'), walk: t('take a walk'),
})[a]

const zoneWord = (z: Zone): string => ({ green: t('Green zone'), yellow: t('Yellow zone'), red: t('Red zone') })[z]
export const ZONE_INK: Record<Zone, string> = { green: 'var(--aq-up, var(--status-green))', yellow: 'var(--aq-wait, var(--status-amber))', red: 'var(--aq-down, var(--status-red))' }

/** 94 → "1 ч 34 мин", 12 → "12 мин". */
export function durOf(min: number) {
  const m = Math.max(0, Math.floor(min))
  if (m < 60) return t('{m} min', { m })
  return m % 60 ? t('{h} h {m} min', { h: Math.floor(m / 60), m: m % 60 }) : t('{h} h', { h: m / 60 })
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

const scheduleLine = (r: Reminder, n: number) =>
  t('every {e} · {n} of {all}, then a pause of {p}', { e: durOf(r.every), n, all: r.times, p: durOf(r.pause) })

type Shown = Exclude<Due, null>

function dueLine(due: Shown, h: HealthState) {
  if (due.kind === 'pomo') return t('Pomodoro: {n} min of work. A break of {r} min.', { n: h.s.pomo.work, r: h.s.pomo.rest })
  if (due.kind === 'remind') return `${capital(actWord(due.act))} · ${scheduleLine(due.r, due.n)}.`
  return `${t('Suggested:')} ${actWord(due.act)}.`
}

/** Clicks that leave the keyboard with the terminal. */
const keepFocus = (e: MouseEvent) => e.preventDefault()

/* ------------------------------------------------------------ the view */

function useView() {
  const h = useHealth()
  const zone = zoneOf(h.d.run, h.s)
  const away = h.d.away
  return { h, zone, away, due: dueOf(h.d, h.s, h.now), breakMin: away === null ? 0 : Math.max(0, h.now - away) / 60_000 }
}

type Summary = { today_min: number }

/** Today's minutes from the server, as the timer chip reads them (the same queries, shared). */
function useToday(project: string) {
  const mine = useQuery({
    queryKey: ['time-summary', project],
    queryFn: ({ signal }) => getJson<Summary>(`/api/time/summary?project=${encodeURIComponent(project)}`, signal),
    refetchInterval: 60_000, retry: false, enabled: !!project,
  })
  const all = useQuery({
    queryKey: ['time-summary-all'],
    queryFn: ({ signal }) => getJson<Summary>('/api/time/summary', signal),
    refetchInterval: 60_000, retry: false,
  })
  return { project: mine.data?.today_min ?? 0, all: all.data?.today_min ?? 0 }
}

/* ------------------------------------------------------------ the title row */

/** The window edge: the zone's colour mixed into the border; null in green, on a break and when off. */
export function useHealthEdge(): string | null {
  const { h, zone, away } = useView()
  if (!h.s.on || zone === 'green' || away !== null) return null
  return `color-mix(in srgb, ${ZONE_INK[zone]} 55%, var(--border-strong))`
}

/** The title row's slight tint. Absolutely placed: the title row must be `relative`. */
export function HealthTint() {
  const { h, zone, away } = useView()
  if (!h.s.on || zone === 'green' || away !== null) return null
  return <span aria-hidden data-health-tint={zone} className="absolute inset-0 pointer-events-none" style={{ background: `color-mix(in srgb, ${ZONE_INK[zone]} ${zone === 'red' ? 12 : 9}%, transparent)` }} />
}

const BTN = 'aq-btn line !h-[22px] text-11'
/** The hover card's width. */
const HOVER_W = 300

function DueButtons({ due }: { due: Shown }) {
  return (
    <span className="inline-flex gap-4 shrink-0">
      <button type="button" data-nodrag data-health-did className={BTN} onMouseDown={keepFocus} onClick={didIt}>
        {due.kind === 'pomo' ? t('Start the break') : t('Did it')}
      </button>
      {due.kind !== 'pomo' && (
        <button type="button" data-nodrag data-health-breaknow className={BTN} onMouseDown={keepFocus} onClick={breakNow} title={t('Work and project time pause until «Done»')}>{t('Break')}</button>
      )}
      <button type="button" data-nodrag data-health-later className={BTN} onMouseDown={keepFocus} onClick={later} title={t('Everything moves {n} min on', { n: LATER_MIN })}>{t('Later')}</button>
    </span>
  )
}

/** The small time label in the title row; the suggestion while the pointer is on it. */
export function HealthTitle({ folded }: { folded: boolean }) {
  const { h, zone, due, away, breakMin } = useView()
  const today = useToday(h.project)
  // The card hangs left from the label's right edge; in a narrow window it moves right so it stays inside (8 px from the edge).
  const [hover, setHover] = useState<number | null>(null)
  if (!h.s.on) return null
  const ink = away !== null ? 'var(--brand)' : due?.kind === 'pomo' ? 'var(--brand)' : zone === 'green' ? 'var(--aq-ink3, var(--text-tertiary))' : ZONE_INK[zone]
  return (
    // pointerdown stays here: the title row drags the window and, folded, unfolds on a click
    <span className="relative inline-flex items-center" data-nodrag data-health-title onPointerDown={(e) => e.stopPropagation()}
      onMouseEnter={(e) => setHover(Math.max(0, HOVER_W + 8 - e.currentTarget.getBoundingClientRect().right))} onMouseLeave={() => setHover(null)}>
      <button type="button" data-nodrag data-health-label={away !== null ? 'break' : zone} className="font-mono tabular-nums rounded-[4px] hover:bg-[var(--aq-hover)]"
        style={{ fontSize: folded ? 9 : 11, lineHeight: folded ? '12px' : '22px', padding: folded ? '0 4px' : '0 6px', color: ink }}
        aria-label={`${t('Time without a break')}: ${clockOf(h.d.run)}`} onMouseDown={keepFocus} onClick={() => {
          setHover(null)
          openUi({ summary: !h.ui.summary, settings: false })
        }}>
        {away !== null ? <>{t('break')} {clockOf(breakMin)}</> : clockOf(h.d.run)}
      </button>
      {hover !== null && !h.ui.summary && !h.ui.settings && (
        <span className="absolute z-[60] rounded-[8px] p-10 flex flex-col gap-6 text-12 cursor-default" role="status" data-health-hover
          onWheel={(e) => {
            if (!e.deltaY || e.ctrlKey || e.shiftKey) return
            const terminal = document.elementsFromPoint(e.clientX, e.clientY)
              .find((element) => element.closest('.aqua-screen .xterm'))
            if (!terminal) return
            // The hover card covers the terminal here. Dismiss it and pass
            // the first wheel step through the same path as the next ones.
            e.stopPropagation()
            setHover(null)
            terminal.dispatchEvent(new WheelEvent('wheel', e.nativeEvent))
          }}
          style={{ top: '100%', right: -hover, width: HOVER_W, background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)' }}>
          <span className="flex items-center gap-6">
            <span className="w-[8px] h-[8px] rounded-full shrink-0" style={{ background: away !== null ? 'var(--brand)' : ZONE_INK[zone] }} />
            <span className="font-semibold">{away !== null ? `${t('On a break')}: ${durOf(breakMin)}` : `${zoneWord(zone)} · ${t('{t} without a break', { t: durOf(h.d.run) })}`}</span>
          </span>
          {due && <span data-health-suggestion={due.kind}>{dueLine(due, h)}</span>}
          {due && <DueButtons due={due} />}
          {!due && <span className="aq-ink3 text-11">{t('Today {all}, on this project {p}.', { all: clockOf(today.all), p: clockOf(today.project) })}</span>}
          {!due && away === null && (
            <span><button type="button" data-nodrag data-health-start className={BTN} onMouseDown={keepFocus} onClick={startBreak} title={t('Work and project time pause until «Done»')}>{t('Take a break')}</button></span>
          )}
        </span>
      )}
    </span>
  )
}

/* ------------------------------------------------------------ the layer over the terminal */

/** The break window, the day's card and the settings. Absolutely placed inside the terminal column; `top` is the terminal's top. */
export function HealthLayer({ top, project }: { top: number; project: string }) {
  const { h, zone, away, breakMin } = useView()
  const open = h.ui.settings || h.ui.summary
  // Esc closes the card that is open, and only then.
  useEffect(() => {
    if (!open) return
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') openUi({ settings: false, summary: false }) }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [open])
  if (!h.s.on) return null
  return (
    <>
      {away !== null && <BreakWindow away={away} breakMin={breakMin} />}
      {h.ui.summary && <DayCard h={h} zone={zone} project={project} top={top} breakMin={breakMin} />}
      {h.ui.settings && (
        <div role="dialog" aria-label={t('Health and time')} data-health-settings className="aq-health-settings absolute right-12 z-[40] w-[360px] rounded-[8px] overflow-y-auto"
          style={{ top: top + 6, maxHeight: `calc(100% - ${top + 18}px)`, ...CARD }}>
          <div className="flex items-center px-12 pt-10">
            <span className="font-semibold text-12">{t('Health and time')}</span>
            <button type="button" className="aq-btn icon ml-auto" aria-label={t('Close')} onClick={() => openUi({ settings: false })}><X size={12} /></button>
          </div>
          <HealthSettings />
        </div>
      )}
    </>
  )
}

/** A break under way: its time, the counters standing still, a note and «Готово». Not modal. */
function BreakWindow({ away, breakMin }: { away: number; breakMin: number }) {
  const [note, setNote] = useState('')
  const done = () => { finishBreak(note); setNote('') }
  return (
    <div role="dialog" aria-modal={false} aria-label={t('Break')} data-health-break className="absolute right-16 bottom-[62px] z-[32] w-[300px] rounded-[8px] overflow-hidden text-12 flex flex-col"
      style={{ background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-lg)', color: 'var(--aq-ink)' }}>
      <div className="h-[26px] px-8 flex items-center gap-6 shrink-0" style={{ background: 'var(--r2-bar)', borderBottom: '1px solid var(--border-default)', boxShadow: 'inset 0 2px 0 var(--brand)' }}>
        <span style={{ color: 'var(--brand)' }} className="inline-flex"><Pause size={12} /></span>
        <span className="text-11 font-semibold">{t('Break')}</span>
      </div>
      <div className="p-10 flex flex-col gap-6">
        <div className="flex items-baseline gap-8">
          <span className="font-mono tabular-nums text-[22px] leading-[26px]" data-health-break-time>{clockOf(breakMin)}</span>
          <span className="text-11 aq-ink3">{t('since {t}', { t: timeOfDay(away) })}</span>
        </div>
        <span className="text-11 aq-ink2">{t('Work time and project time are paused.')}</span>
        <input type="text" value={note} maxLength={120} placeholder={t('A note, if you like')} aria-label={t('Note')} data-health-note
          className="h-[24px] rounded-[4px] px-6 text-12" style={{ background: 'var(--bg-surface)', color: 'var(--aq-ink)', border: '1px solid var(--border-default)' }}
          onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') done() }} />
        <span className="flex items-center gap-6">
          <button type="button" data-nodrag data-health-done className="aq-btn solid !h-[22px] text-11" onClick={done}>{t('Done')}</button>
          <span className="text-10 aq-ink3">{t('Every counter starts again.')}</span>
        </span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ the day's card */

function Line({ label, value, ink }: { label: string; value: ReactNode; ink?: string }) {
  return (
    <div className="flex items-baseline gap-8 min-h-[22px]">
      <span className="aq-ink3 text-11 flex-1 min-w-0 truncate">{label}</span>
      <span className="font-mono tabular-nums text-12 text-right" style={{ color: ink }}>{value}</span>
    </div>
  )
}

const CARD = { background: 'var(--bg-base)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-md)', color: 'var(--aq-ink)' }

function DayCard({ h, zone, project, top, breakMin }: { h: HealthState; zone: Zone; project: string; top: number; breakMin: number }) {
  const today = useToday(project)
  const d = h.d
  const away = d.away !== null
  const green = Math.max(today.all - d.inYellow - d.inRed, 0)
  const bar = [['green', green], ['yellow', d.inYellow], ['red', d.inRed]] as const
  return (
    <div role="dialog" aria-label={t('Time today')} data-health-day className="absolute right-12 z-[40] w-[320px] rounded-[8px] p-12 flex flex-col gap-6 text-12" style={{ top: top + 6, ...CARD }}>
      <div className="flex items-center gap-6">
        <span className="font-semibold">{t('Time today')}</span>
        <span className="aq-ink3 text-11 font-mono">{timeOfDay(h.now)}</span>
        <button type="button" className="aq-btn icon ml-auto" aria-label={t('Settings')} title={t('Settings')} data-health-gear onClick={() => openUi({ settings: true, summary: false })}><Settings2 size={12} /></button>
        <button type="button" className="aq-btn icon" aria-label={t('Close')} onClick={() => openUi({ summary: false })}><X size={12} /></button>
      </div>
      <div className="flex items-baseline gap-12">
        <span className="flex flex-col">
          <span className="font-mono tabular-nums text-[22px] leading-[26px]" data-health-day-all>{clockOf(today.all)}</span>
          <span className="aq-ink3 text-10">{t('all projects')}</span>
        </span>
        <span className="flex flex-col">
          <span className="font-mono tabular-nums text-[22px] leading-[26px]" data-health-day-project>{clockOf(today.project)}</span>
          <span className="aq-ink3 text-10 truncate max-w-[150px]">{project}</span>
        </span>
      </div>
      <div className="flex h-[6px] rounded-full overflow-hidden" aria-label={t('Work today by zone')} role="img" style={{ background: 'var(--aq-hover)' }}>
        {bar.map(([z, m]) => m > 0 && <span key={z} style={{ flex: m, background: ZONE_INK[z] }} />)}
      </div>
      <Line label={away ? t('On a break') : t('Without a break now')} value={clockOf(away ? breakMin : d.run)} ink={away ? 'var(--brand)' : zone === 'green' ? undefined : ZONE_INK[zone]} />
      <Line label={t('In the yellow zone')} value={durOf(d.inYellow)} ink={d.inYellow >= 1 ? ZONE_INK.yellow : undefined} />
      <Line label={t('In the red zone')} value={durOf(d.inRed)} ink={d.inRed >= 1 ? ZONE_INK.red : undefined} />
      <Line label={t('Breaks taken')} value={d.breaks.length ? `${d.breaks.length} · ${d.breaks.map((b) => timeOfDay(b.at)).join(', ')}` : '0'} />
      {d.breaks.some((b) => b.note) && (
        <ul className="m-0 p-0 list-none flex flex-col gap-2" aria-label={t('Notes after breaks')} data-health-notes>
          {d.breaks.filter((b) => b.note).map((b) => (
            <li key={b.at} className="text-11 flex gap-6"><span className="font-mono aq-ink3 shrink-0">{timeOfDay(b.at)} · {durOf(b.len)}</span><span className="truncate">{b.note}</span></li>
          ))}
        </ul>
      )}
      <Line label={t('Actions done')} value={d.done.length ? d.done.map((x) => actWord(x.act)).join(', ') : '—'} />
      <div className="flex items-center gap-6 pt-4">
        {!away
          ? <button type="button" className={BTN} data-health-start onClick={startBreak}>{t('Take a break')}</button>
          : <button type="button" className={BTN} onClick={() => finishBreak()}>{t('Done')}</button>}
        <span className="text-10 aq-ink3 leading-[1.35]">{t('A break of {n} min sets the counter to zero.', { n: h.s.reset })}</span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ the settings */

/** One row as Settings › Terminal draws them: the label and its hint on the left, the control on the right. */
function Row({ label, hint, children }: { label: string; hint?: string; children?: ReactNode }) {
  return (
    <div className="flex items-center gap-12 py-4">
      <div className="flex-1 min-w-0">
        <div className="text-12 text-primary">{label}</div>
        {hint && <div className="text-10 text-tertiary leading-snug">{hint}</div>}
      </div>
      {children}
    </div>
  )
}

const FIELD = 'h-20 px-4 rounded-input border border-border-default bg-surface text-11 font-mono text-primary tabular-nums'

function Num({ label, value, onChange, min = 1, max = 600, width = 'w-[52px]' }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; width?: string }) {
  return (
    <input type="number" min={min} max={max} value={value} aria-label={label} className={`${FIELD} ${width}`}
      onChange={(e) => { const v = Math.round(Number(e.target.value)); if (v >= min && v <= max) onChange(v) }} />
  )
}

function ActPick({ zone, s }: { zone: 'yellow' | 'red'; s: Settings }) {
  const on = s.acts[zone]
  const label = zone === 'yellow' ? t('Actions in the yellow zone') : t('Actions in the red zone')
  return (
    <div className="flex flex-col gap-4 py-4">
      <span className="text-12 text-primary">{label}</span>
      <div className="flex gap-4 flex-wrap" role="group" aria-label={label}>
        {ACTS.map((a) => {
          const has = on.includes(a)
          return (
            <button key={a} type="button" aria-pressed={has} data-health-act={`${zone}-${a}`}
              className={`h-20 px-8 rounded-pill text-10 border ${has ? 'bg-brand text-on-brand border-transparent' : 'border-border-subtle text-tertiary hover:text-primary'}`}
              onClick={() => setHealthSettings({ acts: { ...s.acts, [zone]: has ? on.filter((x) => x !== a) : ACTS.filter((x) => x === a || on.includes(x)) } })}>
              {actWord(a)}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function Reminders({ s }: { s: Settings }) {
  const h = useHealth()
  return (
    <div className="flex flex-col gap-4 py-4" role="group" aria-label={t('Reminders')}>
      <span className="text-12 text-primary">{t('Reminders')}</span>
      {s.reminders.map((r) => {
        const st = remOf(h.d, r)
        const left = durOf(Math.max(st.next - h.d.wk, 0))
        return (
          <div key={r.id} className="flex flex-col gap-2 rounded-input border border-border-default p-6" style={{ opacity: r.on ? 1 : 0.6 }} data-health-reminder={r.act}>
            <div className="flex items-center gap-4">
              <input type="checkbox" checked={r.on} aria-label={`${t('On')} — ${actWord(r.act)}`} onChange={(e) => setReminder(r.id, { on: e.target.checked })} />
              <select value={r.act} aria-label={t('Action')} className={`${FIELD} flex-1 min-w-0 font-sans`} onChange={(e) => setReminder(r.id, { act: e.target.value as ActId })}>
                {ACTS.map((a) => <option key={a} value={a}>{actWord(a)}</option>)}
              </select>
              <button type="button" className="h-20 w-20 inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover" aria-label={`${t('Remove')} ${actWord(r.act)}`} onClick={() => removeReminder(r.id)}><X size={11} /></button>
            </div>
            <div className="flex items-center gap-4 text-11 text-tertiary flex-wrap">
              {t('every')} <Num label={`${t('every, min')} — ${actWord(r.act)}`} value={r.every} max={600} width="w-[44px]" onChange={(every) => setReminder(r.id, { every })} />
              × <Num label={`${t('times')} — ${actWord(r.act)}`} value={r.times} max={20} width="w-[40px]" onChange={(times) => setReminder(r.id, { times })} />,
              {t('pause')} <Num label={`${t('pause, min')} — ${actWord(r.act)}`} value={r.pause} max={1440} width="w-[48px]" onChange={(pause) => setReminder(r.id, { pause })} /> {t('min')}
            </div>
            {h.s.on && <span className="text-10 text-tertiary font-mono">{st.paused ? t('pause: next in {t}', { t: left }) : t('{n} of {all} · next in {t}', { n: st.count + 1, all: r.times, t: left })}</span>}
          </div>
        )
      })}
      <button type="button" className="self-start h-20 px-8 inline-flex items-center gap-4 rounded-input border border-border-default text-11 text-secondary hover:bg-hover" onClick={addReminder}><Plus size={11} />{t('Reminder')}</button>
      <span className="text-10 text-tertiary leading-snug">{t('Reminders count work minutes: a break pauses them. «Postpone» moves the whole schedule.')}</span>
    </div>
  )
}

/**
 * The health settings as rows, for Settings › Terminal (about 360 px wide)
 * and for the card the day's gear opens in the window: the off switch,
 * the zones, the actions, the reminders, the break that resets, the pomodoro.
 */
export function HealthSettings() {
  const s = useHealth().s
  const onOff = (v: boolean) => (v ? 'on' : 'off')
  return (
    <div className="flex flex-col p-12 gap-2" data-health-settings-rows>
      <Row label={t('Health and time')} hint={t('Time without a break in the terminal window\'s title row; it turns yellow, then red. Off: nothing is shown or counted.')}>
        <Segmented label={t('Health and time')} shape="pill" height={20} value={onOff(s.on)} onChange={(v) => setHealthSettings({ on: v === 'on' })}
          options={[['on', t('on')], ['off', t('off')]] as const} />
      </Row>
      {s.on && (
        <>
          <Row label={t('Yellow zone after, min')}><Num label={t('Yellow zone after, min')} value={s.yellow} max={1440} onChange={(yellow) => setHealthSettings({ yellow })} /></Row>
          <Row label={t('Red zone after, min')}><Num label={t('Red zone after, min')} value={s.red} max={1440} onChange={(red) => setHealthSettings({ red })} /></Row>
          <Row label={t('A break that sets the counter to zero, min')} hint={t('No input for this long counts as a break too.')}>
            <Num label={t('A break that sets the counter to zero, min')} value={s.reset} max={120} onChange={(reset) => setHealthSettings({ reset })} />
          </Row>
          <ActPick zone="yellow" s={s} />
          <ActPick zone="red" s={s} />
          <Reminders s={s} />
          <Row label={t('Pomodoro')}>
            <Segmented label={t('Pomodoro')} shape="pill" height={20} value={onOff(s.pomo.on)} onChange={(v) => setHealthSettings({ pomo: { ...s.pomo, on: v === 'on' } })}
              options={[['off', t('off')], ['on', t('on')]] as const} />
          </Row>
          {s.pomo.on && <Row label={t('Pomodoro: work, min')}><Num label={t('Pomodoro: work, min')} value={s.pomo.work} max={120} onChange={(work) => setHealthSettings({ pomo: { ...s.pomo, work } })} /></Row>}
          {s.pomo.on && <Row label={t('Pomodoro: break, min')}><Num label={t('Pomodoro: break, min')} value={s.pomo.rest} max={60} onChange={(rest) => setHealthSettings({ pomo: { ...s.pomo, rest } })} /></Row>}
          <span className="text-10 text-tertiary leading-snug py-4">{t('«Done» asks again in {a} min, «Later» in {l} min. Work goes on in every zone; the minutes in yellow and red are counted.', { a: AGAIN_MIN, l: LATER_MIN })}</span>
          <button type="button" className="self-start h-20 px-8 rounded-input border border-border-default text-11 text-secondary hover:bg-hover"
            onClick={() => setHealthSettings({ ...HEALTH_DEFAULT, on: true })}>{t('Default settings')}</button>
        </>
      )}
    </div>
  )
}
