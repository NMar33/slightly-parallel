/**
 * The monitor in the top bar: CPU, memory, network, the connection and the
 * time, small. Three looks (setting monitor.topbar):
 *
 * - numbers — one mono line of figures;
 * - sparks  — each figure with the last few minutes as a tiny chart;
 * - dot     — one dot, green or not, and the time; the figures on hover.
 *
 * A figure past its alert turns amber; something going on puts its title
 * first. Every look opens the Monitor page.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  HUE, SEVERITY_COLOR, health, ms, pct, useMonitorNow, useMonitorSettings,
  type MonitorNow, type Sample,
} from '../../lib/monitor'
import { Spark } from './charts'
import { t, locale } from '../../i18n/scope/system'

type Look = 'numbers' | 'sparks' | 'dot'

function useClock(): string {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 10_000)
    return () => clearInterval(t)
  }, [])
  return now.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })
}

/** 1.2M, 340K: a rate in four characters. */
function short(b: number | null | undefined): string {
  if (b == null) return '—'
  if (b < 1024) return `${Math.round(b)}B`
  if (b < 1024 ** 2) return `${Math.round(b / 1024)}K`
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(b < 10 * 1024 ** 2 ? 1 : 0)}M`
  return `${(b / 1024 ** 3).toFixed(1)}G`
}

interface Figure {
  id: string
  label: string
  value: string
  hot: boolean
  color: string
  spark: Array<number | null | undefined>
  max?: number
}

function figures(now: MonitorNow, cfg: Record<string, unknown> | undefined): Figure[] {
  const s = now.sample ?? ({} as Sample)
  const sp = now.spark
  const cpuAlert = Number(cfg?.['monitor.cpu_alert_pct'] ?? 90)
  const memAlert = Number(cfg?.['monitor.memory_alert_pct'] ?? 90)
  const out: Figure[] = [
    { id: 'cpu', label: t('CPU'), value: pct(s.cpu), hot: (s.cpu ?? 0) >= cpuAlert, color: HUE.cpu, spark: sp.map((x) => x.cpu), max: 100 },
    { id: 'mem', label: t('MEM'), value: pct(s.mem_pct), hot: (s.mem_pct ?? 0) >= memAlert, color: HUE.mem, spark: sp.map((x) => x.mem_pct), max: 100 },
  ]
  if (s.net_rx != null || s.net_tx != null) {
    out.push({ id: 'net', label: t('NET'), value: `↓${short(s.net_rx)} ↑${short(s.net_tx)}`, hot: false, color: HUE.rx,
      spark: sp.map((x) => (x.net_rx ?? 0) + (x.net_tx ?? 0)) })
  }
  if (now.ping) {
    out.push({ id: 'ping', label: t('PING'), value: now.ping.ok ? ms(now.ping.ms) : t('down'), hot: !now.ping.ok || (now.ping.ms ?? 0) > 300,
      color: HUE.ping, spark: sp.map((x) => x.ping_ms) })
  }
  return out
}

export function TopbarMonitor({ look: forced }: { look?: Look }) {
  const q = useMonitorNow()
  const { values } = useMonitorSettings()
  const time = useClock()
  const now = q.data
  const look = forced ?? (now?.topbar as Look | 'off' | undefined) ?? 'sparks'
  if (!now || (look as string) === 'off') return <span className="text-11 font-mono text-tertiary tabular-nums">{time}</span>
  if (!now.enabled) {
    return (
      <Link to="/monitor" className="text-11 font-mono text-tertiary tabular-nums hover:text-primary" title={t('The system monitor is off')}>
        {time}
      </Link>
    )
  }
  const figs = figures(now, values)
  const h = health(now)
  const alert = h.tone === 'warning' || h.tone === 'critical'
  const title = t('{state} — open the monitor', { state: h.word })

  if (look === 'dot') {
    return (
      <span className="relative group inline-flex">
        <Link to="/monitor" aria-label={title} className="inline-flex items-center gap-6 h-24 px-8 rounded-pill hover:bg-hover text-11 font-mono tabular-nums text-secondary">
          <span className={`w-8 h-8 rounded-pill ${alert ? 'animate-pulse' : ''}`}
            style={{ background: alert ? SEVERITY_COLOR[h.tone as 'warning'] : 'var(--status-green)' }} />
          {alert && <span className="max-w-[160px] truncate" style={{ color: SEVERITY_COLOR[h.tone as 'warning'] }}>{h.word}</span>}
          {time}
        </Link>
        <span className="absolute right-0 top-full pt-4 z-50 hidden group-hover:block group-focus-within:block">
        <span className="flex flex-col gap-6 w-[260px] p-10 rounded-card border border-border-subtle bg-base shadow-lg">
          <span className="text-12 font-medium text-primary">{h.word}</span>
          {figs.map((f) => (
            <span key={f.id} className="flex items-center gap-8 text-11 font-mono tabular-nums">
              <span className="w-[36px] text-tertiary">{f.label}</span>
              <Spark values={f.spark} color={f.color} width={96} height={14} max={f.max} />
              <span className={`ml-auto whitespace-nowrap ${f.hot ? 'text-status-amber' : 'text-primary'}`}>{f.value}</span>
            </span>
          ))}
        </span>
        </span>
      </span>
    )
  }

  return (
    <Link to="/monitor" title={title}
      className="inline-flex items-center gap-10 h-24 px-8 rounded-pill hover:bg-hover text-11 font-mono tabular-nums text-secondary whitespace-nowrap">
      {alert && (
        <span className="inline-flex items-center gap-4 max-w-[180px]" style={{ color: SEVERITY_COLOR[h.tone as 'warning'] }}>
          <span className="w-6 h-6 rounded-pill animate-pulse" style={{ background: 'currentColor' }} />
          <span className="truncate">{h.word}</span>
        </span>
      )}
      {figs.map((f) => (
        <span key={f.id} className="inline-flex items-center gap-4">
          <span className="text-tertiary text-10">{f.label}</span>
          {look === 'sparks' && <Spark values={f.spark.slice(-40)} color={f.color} width={28} height={12} max={f.max} />}
          <span className={f.hot ? 'text-status-amber' : 'text-primary'}>{f.value}</span>
        </span>
      ))}
      <span className="text-tertiary">·</span>
      <span className="text-primary">{time}</span>
    </Link>
  )
}
