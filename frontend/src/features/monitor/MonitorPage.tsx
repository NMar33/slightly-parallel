/**
 * The Monitor page: a tile per measure with its last minutes, the charts
 * over a chosen span (the unusual moments shaded), and beside them what is
 * going on, what was unusual lately, and the heaviest programs. The
 * settings open in a drawer. Under all that, the server itself: its state,
 * capture, backups, the slow requests and the log (ServerSection).
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Activity, Settings2 } from 'lucide-react'

import { PageHeader } from '../../components/PageHeader'
import { Segmented } from '../../components/Segmented'
import { StatTile } from '../../components/StatTile'
import { useModalA11y } from '../project/useModalA11y'
import { MONITOR_GUIDE } from '../visions/guides'
import { PageGuide } from '../visions/parts'
import {
  HUE, RANGES, SEVERITY_COLOR, bytes, duration, health, ms, pct, rate,
  useMonitorEvents, useMonitorNow, useMonitorSeries, useMonitorSettings, useSeenAll, type MonitorNow, type Range, type Severity,
} from '../../lib/monitor'
import { Spark, TimeAxis } from './charts'
import {
  EventDetail, EventRow, MonitorSettings, PowerSwitch, Processes, StripFor, measuresFor,
} from './parts'
import { ServerSection } from './ServerSection'
import { t, tn } from '../../i18n/scope/system'

const RANGE_WORDS: Record<Range, string> = {
  '15m': t('15 min'), '1h': t('1 hour'), '6h': t('6 hours'), '24h': t('24 hours'), '7d': t('7 days'), '30d': t('30 days'), '90d': t('90 days'), '1y': t('1 year'),
}

function upFor(boot: number): string {
  return boot ? t('up {time}', { time: duration(Date.now() / 1000 - boot) }) : ''
}

function HealthPill({ now }: { now: MonitorNow | undefined }) {
  const h = health(now)
  const color = h.tone === 'ok' ? 'var(--status-green)' : h.tone === 'off' ? 'var(--text-tertiary)' : SEVERITY_COLOR[h.tone as Severity]
  return (
    <span className="inline-flex items-center gap-6 h-24 px-10 rounded-pill border text-12" style={{ borderColor: color, color }}>
      <span className={`w-8 h-8 rounded-pill ${h.tone === 'warning' || h.tone === 'critical' ? 'animate-pulse' : ''}`} style={{ background: color }} />
      {h.word}
    </span>
  )
}

function Header({ now, right, sub }: { now: MonitorNow | undefined; right?: ReactNode; sub?: ReactNode }) {
  useEffect(() => { document.title = 'Monitor — Slightly Parallel' }, [])
  const host = now?.host
  return (
    <>
      <PageHeader
        variant="lens" icon={Activity} title={t('Monitor')}
        actions={<>{right}<PowerSwitch /></>}
        below={host ? (
          <p className="text-11 font-mono text-tertiary">
            {host.name} · {host.os} · {tn(host.threads, '{n} thread', '{n} threads')} · {t('{size} memory', { size: bytes(host.memory) })} · {upFor(host.boot)}
            {sub}
          </p>
        ) : undefined}
      >
        <HealthPill now={now} />
      </PageHeader>
      <PageGuide id="monitor" guide={MONITOR_GUIDE} examples={0} />
    </>
  )
}

function Off() {
  return (
    <div className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-8 max-w-[560px]">
      <h2 className="text-16 font-semibold text-primary">{t('The monitor is off.')}</h2>
      <p className="text-13 text-secondary">{t('When on, it reads CPU, memory, disk and network every few seconds and records anything unusual here.')}</p>
      <div><PowerSwitch /></div>
    </div>
  )
}

function Cost({ now }: { now: MonitorNow | undefined }) {
  if (!now?.cost) return null
  const self = now.sample
  return (
    <p className="text-11 font-mono text-tertiary">
      {t('The monitor itself: {ms} ms a reading, {cpu}% of one core · Slightly Parallel uses {mem} memory, {selfCpu} CPU.', { ms: now.cost.ms_per_sample, cpu: now.cost.cpu_pct, mem: bytes(self?.self_rss), selfCpu: pct(self?.self_cpu) })}
    </p>
  )
}

function useCursor() {
  return useState<number | null>(null)
}

/* =============================================================== A · Console */

function Tile({ label, value, sub, spark, color, max, hot }: {
  label: string; value: string; sub?: string; spark: Array<number | null | undefined>; color: string; max?: number; hot?: boolean
}) {
  return (
    <StatTile label={label} value={value} sub={sub} hot={hot}>
      <span className="my-4 block"><Spark values={spark} color={color} width={160} height={24} max={max} /></span>
    </StatTile>
  )
}

function Tiles({ now }: { now: MonitorNow }) {
  // The alerts the operator set, as the top bar reads them.
  const { values } = useMonitorSettings()
  const cpuAlert = Number(values?.['monitor.cpu_alert_pct'] ?? 90)
  const memAlert = Number(values?.['monitor.memory_alert_pct'] ?? 90)
  const s = now.sample ?? { ts: 0 }
  const sp = now.spark
  const disk = (s.disks ?? []).slice().sort((a, b) => b.used / b.total - a.used / a.total)[0]
  return (
    <div className="grid gap-10 grid-cols-[repeat(auto-fit,minmax(160px,1fr))]">
      <Tile label={t('CPU')} value={pct(s.cpu)} sub={s.load1 != null ? t('load {n}', { n: s.load1.toFixed(2) }) : undefined} spark={sp.map((x) => x.cpu)} color={HUE.cpu} max={100} hot={(s.cpu ?? 0) >= cpuAlert} />
      <Tile label={t('Memory')} value={pct(s.mem_pct)} sub={`${t('{a} of {b}', { a: bytes(s.mem_used), b: bytes(s.mem_total) })}${s.swap_used ? ` · ${t('swap {size}', { size: bytes(s.swap_used) })}` : ''}`} spark={sp.map((x) => x.mem_pct)} color={HUE.mem} max={100} hot={(s.mem_pct ?? 0) >= memAlert} />
      <Tile label={t('Disk')} value={disk ? t('{size} free', { size: bytes(disk.total - disk.used, 0) }) : '—'} sub={disk ? `${disk.mount} · ${t('{pct} used', { pct: pct((100 * disk.used) / disk.total) })}` : undefined} spark={sp.map((x) => (x.disk_read ?? 0) + (x.disk_write ?? 0))} color={HUE.disk} />
      <Tile label={t('Download')} value={rate(s.net_rx)} sub={t('up {rate}', { rate: rate(s.net_tx) })} spark={sp.map((x) => x.net_rx)} color={HUE.rx} />
      <Tile label={t('Connection')} value={now.ping ? (now.ping.ok ? ms(now.ping.ms) : t('no answer')) : '—'} sub={now.ping?.host} spark={sp.map((x) => x.ping_ms)} color={HUE.ping} hot={now.ping ? !now.ping.ok : false} />
      {/* macOS and Windows give no temperature to a program: the battery stands in, or nothing. */}
      {s.temp_c != null ? (
        <Tile label={t('Temperature')} value={`${Math.round(s.temp_c)} °C`} sub={s.battery != null ? (s.plugged ? t('battery {pct}, plugged in', { pct: pct(s.battery) }) : t('battery {pct}', { pct: pct(s.battery) })) : undefined} spark={sp.map((x) => x.temp_c)} color={HUE.temp} />
      ) : s.battery != null ? (
        <Tile label={t('Battery')} value={pct(s.battery)} sub={s.plugged ? t('plugged in') : t('on battery')} spark={[]} color={HUE.temp} max={100} />
      ) : null}
    </div>
  )
}

function RangePicker({ range, onRange }: { range: Range; onRange: (r: Range) => void }) {
  return <Segmented label={t('Span')} shape="pill" height={20} value={range} onChange={onRange} options={RANGES.map((r) => [r, r, RANGE_WORDS[r]] as const)} />
}

function Drawer({ open, onClose, children, title }: { open: boolean; onClose: () => void; children: ReactNode; title: string }) {
  if (!open) return null
  return <OpenDrawer onClose={onClose} title={title}>{children}</OpenDrawer>
}

/** The drawer once it is open — a component of its own so the modal
 *  behavior (Escape, focus trap, focus restore) mounts with it. */
function OpenDrawer({ onClose, children, title }: { onClose: () => void; children: ReactNode; title: string }) {
  const dialogRef = useRef<HTMLDivElement>(null)
  useModalA11y(dialogRef, onClose)
  return (
    <div ref={dialogRef} className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label={t('Close')} className="absolute inset-0 bg-scrim" onClick={onClose} />
      <aside className="relative w-[440px] max-w-full h-full overflow-y-auto bg-base border-l border-border-subtle p-16 flex flex-col gap-12">
        <div className="flex items-center">
          <h2 className="text-16 font-semibold text-primary">{title}</h2>
          <button type="button" onClick={onClose} className="ml-auto text-tertiary hover:text-primary text-20 leading-none" aria-label={t('Close')}>×</button>
        </div>
        {children}
      </aside>
    </div>
  )
}

function Console() {
  const now = useMonitorNow().data
  const [range, setRange] = useState<Range>('1h')
  const series = useMonitorSeries(range).data
  const [cursor, setCursor] = useCursor()
  const [open, setOpen] = useState<number | null>(null)
  const [settings, setSettings] = useState(false)
  const recent = useMonitorEvents({ days: 7, limit: 40 }).data
  const seen = useSeenAll()
  const measures = measuresFor(series)
  const going = now?.open ?? []
  const past = (recent?.events ?? []).filter((e) => e.ended != null)

  return (
    <div className="flex flex-col gap-16 min-w-0">
      <Header now={now} right={
        <button type="button" onClick={() => setSettings(true)} className="inline-flex items-center gap-6 text-12 text-secondary hover:text-primary">
          <Settings2 size={14} aria-hidden /> {t('Settings')}
        </button>} />
      {now && !now.enabled ? <Off /> : now && (
        <>
          <Tiles now={now} />
          <div className="grid gap-16 lg:grid-cols-[minmax(0,1fr)_320px] items-start">
            <section className="flex flex-col gap-10 min-w-0 rounded-card border border-border-subtle p-12">
              <div className="flex items-center gap-8 flex-wrap">
                <span className="text-13 font-medium text-primary">{t('Over the last')}</span>
                <RangePicker range={range} onRange={setRange} />
                {series && <span className="ml-auto text-10 font-mono text-tertiary">{series.tier === 0 ? t('every reading') : series.tier === 1 ? t('minute averages') : t('15-minute averages')} · {t('shaded: unusual')}</span>}
              </div>
              {series && measures.map((m) => (
                <StripFor key={m.id} m={m} series={series} cursor={cursor} onCursor={setCursor} onEvent={(e) => setOpen(e.id)} height={56} />
              ))}
              {series && <TimeAxis from={series.from} to={series.to} />}
            </section>
            <aside className="flex flex-col gap-16 min-w-0">
              {open != null ? (
                <div className="rounded-card border border-border-subtle bg-surface"><EventDetail id={open} onClose={() => setOpen(null)} /></div>
              ) : (
                <section className="flex flex-col gap-4">
                  <div className="flex items-center gap-8">
                    <h2 className="text-13 font-medium text-primary">{t('In progress')}</h2>
                    <span className="text-11 font-mono text-tertiary">{going.length || t('nothing')}</span>
                  </div>
                  {going.map((e) => <EventRow key={e.id} e={e} onOpen={(x) => setOpen(x.id)} />)}
                  <div className="flex items-center gap-8 mt-8">
                    <h2 className="text-13 font-medium text-primary">{t('Last 7 days')}</h2>
                    {(now.unseen ?? 0) > 0 && (
                      <button type="button" className="ml-auto text-11 text-brand hover:underline" onClick={() => seen.mutate(undefined)}>{t('mark {n} seen', { n: now.unseen ?? 0 })}</button>
                    )}
                  </div>
                  {past.length === 0 && <p className="text-12 text-tertiary">{t('Nothing unusual in the last 7 days.')}</p>}
                  {past.slice(0, 12).map((e) => <EventRow key={e.id} e={e} onOpen={(x) => setOpen(x.id)} />)}
                </section>
              )}
              <Processes compact />
            </aside>
          </div>
          <Cost now={now} />
        </>
      )}
      <ServerSection />
      <Drawer open={settings} onClose={() => setSettings(false)} title={t('Monitor settings')}><MonitorSettings /></Drawer>
    </div>
  )
}

/** The Monitor page: the console, chosen from three looks. */
export function MonitorPage() {
  return <Console />
}


