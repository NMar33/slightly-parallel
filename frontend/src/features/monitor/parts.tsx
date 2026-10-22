/**
 * What every monitor page shares: the measures and how each is worded and
 * drawn, the events list and one event opened, the heaviest processes, the
 * on/off switch, and the settings.
 */

import { Switch } from '../../components/Switch'
import { LABEL } from '../../components/ui'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { Segmented } from '../../components/Segmented'
import { Confirm } from '../../components/Confirm'
import { postJson } from '../../lib/getJson'
import {
  HUE, SEVERITY_COLOR, bytes, clock, duration, ms, pct, rate,
  useMonitorEvent, useMonitorProcesses, useMonitorSettings, useMonitorStorage,
  type MonitorEvent, type Series,
} from '../../lib/monitor'
import { Strip, type Line } from './charts'
import { locale, t, tn } from '../../i18n/scope/system'

/* ---------------------------------------------------------------- measures */

interface Measure {
  id: string
  title: string
  format: (v: number | null | undefined) => string
  max?: number
  lines: (s: Series['series']) => Line[]
  /** The event kinds drawn on this strip; the rest are drawn on none. */
  kinds: string[]
  setting?: string
}

const col = (s: Series['series'], k: string) => (s[k] ?? []) as Array<number | null>

const MEASURES: Measure[] = [
  { id: 'cpu', title: t('CPU'), format: pct, max: 100, kinds: ['cpu', 'unusual', 'leak'],
    lines: (s) => [{ name: 'CPU', color: HUE.cpu, values: col(s, 'cpu'), peaks: col(s, 'cpu_max') }] },
  { id: 'mem', title: t('Memory'), format: pct, max: 100, kinds: ['memory', 'swap', 'leak'],
    lines: (s) => [{ name: t('Memory'), color: HUE.mem, values: col(s, 'mem_pct'), peaks: col(s, 'mem_pct_max') }] },
  // The server's own memory, with the bucket's peak: a spike of a few
  // seconds (2.5 GB on a start, once) stays visible in hour and day views.
  { id: 'self', title: t('Slightly Parallel memory'), format: bytes, kinds: ['leak'],
    lines: (s) => [{ name: t('Server'), color: HUE.self, values: col(s, 'self_rss'), peaks: col(s, 'self_rss_max') }] },
  { id: 'net', title: t('Network'), format: rate, kinds: ['network', 'unusual'], setting: 'monitor.track_network',
    lines: (s) => [
      { name: '↓', color: HUE.rx, values: col(s, 'net_rx'), peaks: col(s, 'net_rx_max') },
      { name: '↑', color: HUE.tx, values: col(s, 'net_tx') }] },
  { id: 'ping', title: t('Connection'), format: ms, kinds: ['network'],
    lines: (s) => [{ name: 'Ping', color: HUE.ping, values: col(s, 'ping_ms'), peaks: col(s, 'ping_ms_max') }] },
  { id: 'io', title: t('Disk traffic'), format: rate, kinds: ['unusual'], setting: 'monitor.track_disk',
    lines: (s) => [
      { name: t('read'), color: HUE.disk, values: col(s, 'disk_read'), peaks: col(s, 'disk_read_max') },
      { name: t('write'), color: HUE.tx, values: col(s, 'disk_write') }] },
  { id: 'space', title: t('Disk space used'), format: pct, max: 100, kinds: ['disk'], setting: 'monitor.track_disk',
    lines: (s) => [{ name: t('Used'), color: HUE.disk, values: col(s, 'disk_pct') }] },
  { id: 'temp', title: t('Temperature'), format: (v) => (v == null ? '—' : `${Math.round(v)} °C`), kinds: ['temperature'], setting: 'monitor.track_temperature',
    lines: (s) => [{ name: t('Hottest'), color: HUE.temp, values: col(s, 'temp_c'), peaks: col(s, 'temp_c_max') }] },
]

/** The strips worth drawing: tracked, and with something in them. */
export function measuresFor(series: Series | undefined): Measure[] {
  if (!series) return MEASURES.slice(0, 4)
  return MEASURES.filter((m) => m.lines(series.series).some((l) => l.values.some((v) => v != null)))
}

export function StripFor({ m, series, cursor, onCursor, onEvent, height, dense, now, bare }: {
  m: Measure
  series: Series
  cursor: number | null
  onCursor: (t: number | null) => void
  onEvent?: (e: MonitorEvent) => void
  height?: number
  dense?: boolean
  now?: ReactNode
  /** No title row: the host names the strip itself. */
  bare?: boolean
}) {
  // The same lines for the same series: a new array every render undid the
  // strip's own memo, and every cursor move redrew every path.
  const lines = useMemo(() => m.lines(series.series), [m, series])
  const events = useMemo(() => series.events.filter((e) => m.kinds.includes(e.kind)), [m, series])
  return (
    <Strip bare={bare} t={series.series.t as number[]} lines={lines} from={series.from} to={series.to}
      format={m.format} max={m.max} title={m.title} gaps={series.gaps} now={now}
      events={events}
      cursor={cursor} onCursor={onCursor} onEvent={onEvent} height={height} dense={dense} />
  )
}

/* ------------------------------------------------------------------ events */

function SeverityDot({ s, size = 8 }: { s: MonitorEvent['severity']; size?: number }) {
  return <span role="img" className="inline-block rounded-pill shrink-0" style={{ width: size, height: size, background: SEVERITY_COLOR[s] }} aria-label={s} />
}

export function EventRow({ e, onOpen, active }: { e: MonitorEvent; onOpen: (e: MonitorEvent) => void; active?: boolean }) {
  const going = e.ended == null
  return (
    <button type="button" onClick={() => onOpen(e)}
      className={`w-full text-left flex items-start gap-8 px-8 py-6 rounded-input hover:bg-hover ${active ? 'bg-hover' : ''}`}>
      <span className="pt-4"><SeverityDot s={e.severity} /></span>
      <span className="min-w-0 flex-1 flex flex-col">
        <span className={`text-13 truncate ${e.kind === 'gap' ? 'text-tertiary' : 'text-primary'} ${e.seen ? '' : e.severity !== 'info' ? 'font-medium' : ''}`}>{e.title}</span>
        <span className="text-11 font-mono text-tertiary tabular-nums truncate">
          {clock(e.started, true)} · {going ? <span style={{ color: SEVERITY_COLOR[e.severity] }}>{t('in progress, {time}', { time: duration(Date.now() / 1000 - e.started) })}</span> : duration((e.ended ?? e.started) - e.started)}
        </span>
      </span>
    </button>
  )
}

/** One event: what, when, how long, the readings and the heaviest processes of its moment. */
export function EventDetail({ id, onClose }: { id: number; onClose?: () => void }) {
  const q = useMonitorEvent(id)
  const e = q.data?.event
  if (!e) return <div className="text-12 text-tertiary p-12">{t('Reading…')}</div>
  const r = e.context?.reading ?? {}
  const facts: Array<[string, string]> = [
    [t('CPU'), pct(r.cpu)], [t('Memory'), pct(r.mem_pct)], [t('Download'), rate(r.net_rx)], [t('Upload'), rate(r.net_tx)],
    [t('Ping'), ms(r.ping_ms)], [t('Disk used'), pct(r.disk_pct)], [t('Temperature'), r.temp_c == null ? '—' : `${Math.round(r.temp_c)} °C`],
  ]
  return (
    <div className="flex flex-col gap-12 p-12 min-w-0">
      <div className="flex items-start gap-8">
        <span className="pt-6"><SeverityDot s={e.severity} size={10} /></span>
        <div className="min-w-0 flex-1">
          <h3 className="text-16 font-semibold text-primary leading-snug">{e.title}</h3>
          <p className="text-13 text-secondary leading-relaxed">{e.detail}</p>
        </div>
        {onClose && <button type="button" onClick={onClose} className="text-tertiary hover:text-primary text-16 leading-none" aria-label={t('Close')}>×</button>}
      </div>
      <div className="text-11 font-mono text-tertiary tabular-nums">
        {clock(e.started, true)} → {e.ended ? clock(e.ended, true) : t('now')} · {duration((e.ended ?? Date.now() / 1000) - e.started)} · {t(e.severity)}
      </div>
      {e.kind !== 'gap' && e.kind !== 'system' && (
        <>
          <dl className="grid grid-cols-2 gap-x-12 gap-y-2 text-12">
            {facts.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-8"><dt className="text-tertiary">{k}</dt><dd className="font-mono tabular-nums text-primary">{v}</dd></div>
            ))}
          </dl>
          <ProcList title={t('Busiest then')} rows={e.context?.top_cpu ?? []} by="cpu" />
          <ProcList title={t('Largest then')} rows={e.context?.top_memory ?? []} by="rss" />
        </>
      )}
    </div>
  )
}

function ProcList({ title, rows, by }: { title: string; rows: Array<{ pid: number; name: string; rss: number; cpu: number }>; by: 'cpu' | 'rss' }) {
  if (!rows.length) return null
  return (
    <div className="flex flex-col gap-2">
      <span className={LABEL}>{title}</span>
      {rows.map((p) => (
        <div key={p.pid} className="flex items-baseline gap-8 text-12">
          <span className="truncate text-primary flex-1">{p.name}</span>
          <span className="font-mono tabular-nums text-tertiary">{by === 'cpu' ? pct(p.cpu) : bytes(p.rss)}</span>
        </div>
      ))}
    </div>
  )
}

/* --------------------------------------------------------------- processes */

export function Processes({ compact = false }: { compact?: boolean }) {
  const [sort, setSort] = useState<'rss' | 'cpu'>('rss')
  const [grouped, setGrouped] = useState(true)
  const q = useMonitorProcesses(sort)
  const rows = grouped && q.data?.programs.length ? q.data.programs : q.data?.processes ?? []
  const top = Math.max(1, ...rows.map((p) => (sort === 'rss' ? p.rss : p.cpu)))
  return (
    <div className="flex flex-col gap-6 min-w-0">
      <div className="flex items-center gap-8 flex-wrap">
        <span className={LABEL}>{t('Heaviest')}</span>
        <Segmented label={t('Sort')} shape="pill" height={20} value={sort} onChange={setSort}
          options={[['rss', t('memory')], ['cpu', t('CPU')]] as const} />
        <Segmented label={t('Group')} shape="pill" height={20} value={grouped ? 'g' : 'p'} onChange={(v) => setGrouped(v === 'g')}
          options={[['g', t('programs'), t('Processes of one program added up')], ['p', t('processes')]] as const} />
        {q.data?.at && <span className="ml-auto text-10 font-mono text-tertiary">{tn(q.data.count, '{n} process', '{n} processes')} · {clock(q.data.at)}</span>}
      </div>
      {rows.length === 0 && <span className="text-12 text-tertiary">{t('Processes are read every 30 seconds. Waiting for the first reading.')}</span>}
      <ul className="flex flex-col">
        {rows.slice(0, compact ? 6 : 12).map((p) => {
          const v = sort === 'rss' ? p.rss : p.cpu
          return (
            <li key={'pid' in p ? p.pid : p.name} className="relative flex items-baseline gap-8 px-6 py-2 text-12">
              <span className="absolute inset-y-0 left-0 rounded-input" style={{ width: `${(v / top) * 100}%`, background: sort === 'rss' ? HUE.mem : HUE.cpu, opacity: 0.1 }} aria-hidden />
              <span className="relative truncate flex-1 text-primary">{p.name}{'n' in p && p.n > 1 ? <span className="text-tertiary"> ×{p.n}</span> : null}</span>
              <span className="relative font-mono tabular-nums text-tertiary w-[56px] text-right">{pct(p.cpu)}</span>
              <span className="relative font-mono tabular-nums text-secondary w-[72px] text-right">{bytes(p.rss)}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/* ---------------------------------------------------------------- settings */

export function PowerSwitch() {
  const { values, save, saving } = useMonitorSettings()
  const on = values?.['monitor.enabled'] !== false
  return (
    <Switch on={on} disabled={saving || !values} label={t('Monitor')} text={on ? t('On') : t('Off')}
      onChange={(next) => save({ 'monitor.enabled': next })}
      title={on ? t('The monitor is reading this computer. Click to stop.') : t('The monitor is off. Click to start it.')} />
  )
}

type V = number | boolean | string

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-12 py-4 min-w-0">
      <div className="flex-1 min-w-0">
        <div className="text-13 text-primary">{label}</div>
        {hint && <div className="text-11 text-tertiary leading-snug">{hint}</div>}
      </div>
      <div className="shrink-0 flex items-center gap-6">{children}</div>
    </div>
  )
}

function NumberBox({ value, onSave, unit, min, max }: { value: number; onSave: (v: number) => void; unit: string; min: number; max: number }) {
  const [draft, setDraft] = useState(String(value))
  useEffect(() => setDraft(String(value)), [value])
  const commit = () => {
    const n = Math.trunc(Number(draft))
    if (Number.isFinite(n) && n >= min && n <= max && n !== value) onSave(n)
    else setDraft(String(value))
  }
  return (
    <>
      <input type="number" value={draft} min={min} max={max} onChange={(e) => setDraft(e.target.value)}
        onBlur={commit} onKeyDown={(e) => e.key === 'Enter' && commit()}
        className="w-[72px] h-24 px-6 rounded-input border border-border-default bg-surface text-12 font-mono text-right text-primary" />
      <span className="text-11 text-tertiary w-[64px]">{unit}</span>
    </>
  )
}

/** Everything the monitor can be told, in five groups, saved as it is changed. */
export function MonitorSettings() {
  const { values, save, error } = useMonitorSettings()
  const storage = useMonitorStorage()
  const [clear, setClear] = useState<'samples' | 'events' | null>(null)
  const qc = useQueryClient()
  if (!values) return <div className="text-12 text-tertiary">{t('Reading the settings…')}</div>
  const v = (k: string) => values[`monitor.${k}`]
  const set = (k: string, x: V) => save({ [`monitor.${k}`]: x })
  const choice = (k: string, opts: string[], words?: Record<string, string>) => (
    <Segmented label={k} shape="pill" height={20} value={String(v(k))} onChange={(x) => set(k, x)}
      options={opts.map((o) => [o, words?.[o] ?? t(o)] as const)} />
  )
  const flag = (k: string) => (
    <input type="checkbox" checked={v(k) !== false} onChange={(e) => set(k, e.target.checked)} className="accent-[var(--brand)]" aria-label={k} />
  )
  const num = (k: string, unit: string, min: number, max: number) => (
    <NumberBox value={Number(v(k))} unit={unit} min={min} max={max} onSave={(x) => set(k, x)} />
  )
  const secs = (o: string) => (o === '0' ? t('off') : t('{n} s', { n: o }))
  const tiers = storage.data?.tiers ?? {}
  return (
    <div className="flex flex-col gap-16 min-w-0">
      {error && <p className="text-12 text-error">{error.message}</p>}
      <section className="flex flex-col">
        <h3 className={`${LABEL} mb-4`}>{t('Read')}</h3>
        <Field label={t('The monitor')} hint={t('Off: no readings, and the top bar is empty.')}><PowerSwitch /></Field>
        <Field label={t('Every')} hint={t('CPU, memory, disk and network.')}>{choice('interval_seconds', ['1', '2', '5', '10', '30', '60'], Object.fromEntries(['1', '2', '5', '10', '30', '60'].map((o) => [o, t('{n} s', { n: o })])))}</Field>
        <Field label={t('Processes every')} hint={t('Which processes use CPU and memory, to find leaks. About 50 ms each.')}>{choice('processes_seconds', ['0', '10', '30', '60', '300'], Object.fromEntries(['0', '10', '30', '60', '300'].map((o) => [o, secs(o)])))}</Field>
        <Field label={t('Connection every')} hint={t('Opens a connection to the host below and times it.')}>{choice('ping_seconds', ['0', '5', '10', '30', '60'], Object.fromEntries(['0', '5', '10', '30', '60'].map((o) => [o, secs(o)])))}</Field>
        <Field label={t('Connection host')}>
          <input defaultValue={String(v('ping_host'))} key={String(v('ping_host'))}
            onBlur={(e) => e.target.value.trim() && e.target.value !== v('ping_host') && set('ping_host', e.target.value.trim())}
            className="w-[160px] h-24 px-6 rounded-input border border-border-default bg-surface text-12 font-mono text-primary" />
        </Field>
        <Field label={t('Disk')} hint={t('Space, reads and writes.')}>{flag('track_disk')}</Field>
        <Field label={t('Network')} hint={t('Download and upload.')}>{flag('track_network')}</Field>
        <Field label={t('Temperature and battery')} hint={t('Temperature on Linux only.')}>{flag('track_temperature')}</Field>
      </section>
      <section className="flex flex-col">
        <h3 className={`${LABEL} mb-4`}>{t('Unusual')}</h3>
        <Field label={t('Sensitivity')} hint={t('How far from usual a reading must be to be recorded.')}>{choice('sensitivity', ['low', 'normal', 'high'])}</Field>
        <Field label={t('CPU')} hint={t('Recorded after 2 minutes at or above.')}>{num('cpu_alert_pct', '%', 50, 100)}</Field>
        <Field label={t('Memory')} hint={t('Recorded after 1 minute at or above.')}>{num('memory_alert_pct', '%', 50, 100)}</Field>
        <Field label={t('Disk space')} hint={t('Recorded below this much free.')}>{num('disk_alert_pct', t('% free'), 1, 50)}</Field>
        <Field label={t('Temperature')}>{num('temp_alert_c', '°C', 50, 120)}</Field>
        <Field label={t('Memory leak')} hint={t('A process growing steadily faster than this…')}>{num('leak_mb_per_hour', t('MB/hour'), 5, 5000)}</Field>
        <Field label={t('…for')} hint={t('for the whole of this window.')}>{num('leak_window_minutes', t('minutes'), 10, 720)}</Field>
      </section>
      <section className="flex flex-col">
        <h3 className={`${LABEL} mb-4`}>{t('Keep')}</h3>
        <Field label={t('Every sample')} hint={tiers['0'] ? t('{n} now', { n: tiers['0'].rows.toLocaleString(locale()) }) : undefined}>{num('keep_raw_hours', t('hours'), 1, 72)}</Field>
        <Field label={t('Minute averages')} hint={tiers['1'] ? t('{n} now', { n: tiers['1'].rows.toLocaleString(locale()) }) : undefined}>{num('keep_minutes_days', t('days'), 1, 60)}</Field>
        <Field label={t('15-minute averages')} hint={tiers['2'] ? t('{n} now', { n: tiers['2'].rows.toLocaleString(locale()) }) : undefined}>{num('keep_quarters_days', t('days'), 7, 1095)}</Field>
        <Field label={t('Unusual events')} hint={storage.data ? t('{n} now', { n: storage.data.events.rows.toLocaleString(locale()) }) : undefined}>{num('keep_events_days', t('days'), 30, 3650)}</Field>
        <div className="flex items-center gap-8 pt-6 text-11 font-mono text-tertiary flex-wrap">
          <span>{storage.data ? t('{size} on disk', { size: bytes(storage.data.bytes) }) : ''}</span>
          <button type="button" className="ml-auto text-secondary hover:text-primary underline-offset-2 hover:underline" onClick={() => setClear('samples')}>{t('Delete readings')}</button>
          <button type="button" className="text-secondary hover:text-primary underline-offset-2 hover:underline" onClick={() => setClear('events')}>{t('Delete events')}</button>
        </div>
      </section>
      <section className="flex flex-col">
        <h3 className={`${LABEL} mb-4`}>{t('Top bar')}</h3>
        <Field label={t('Shows')}>{choice('topbar', ['off', 'numbers', 'sparks', 'dot'], { off: t('nothing'), numbers: t('numbers'), sparks: t('small charts'), dot: t('one dot') })}</Field>
      </section>
      {clear && (
        <Confirm
          text={clear === 'samples' ? t('Delete all readings. The charts start empty. Events and settings are kept.') : t('Delete all finished events. Events in progress, readings and settings are kept.')}
          action={t('Delete')}
          onYes={async () => {
            try {
              await postJson('/api/monitor/clear', { what: clear, actor: 'operator' })
              setClear(null)
              // Everything that showed the deleted record reads it again.
              void qc.invalidateQueries({ queryKey: ['monitor'] })
            } catch (e) {
              toast.error(t('Nothing was deleted: {error}', { error: (e as Error).message }))
            }
          }}
          onNo={() => setClear(null)}
        />
      )}
    </div>
  )
}
