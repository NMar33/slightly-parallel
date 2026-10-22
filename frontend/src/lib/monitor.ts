/**
 * The system monitor, read (backend sysmon.py, /api/monitor/*).
 *
 * `useMonitorNow` is the one live poll: the top bar and the page share it,
 * at the sampler's own interval (never faster than 2 s), and it stops while
 * the tab is hidden. Everything else is read on demand.
 */

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { getJson, postJson } from './getJson'
import { SETTINGS_QUERY_KEY, saveSettings, useSettingsValues } from './settings'
import { dayMonth } from './months'

interface Disk { mount: string; used: number; total: number }

export interface Sample {
  ts: number
  cpu?: number | null
  load1?: number | null
  mem_used?: number | null
  mem_total?: number | null
  mem_pct?: number | null
  swap_used?: number | null
  swap_total?: number | null
  disk_pct?: number | null
  disk_free?: number | null
  disk_read?: number | null
  disk_write?: number | null
  net_rx?: number | null
  net_tx?: number | null
  ping_ms?: number | null
  temp_c?: number | null
  battery?: number | null
  plugged?: boolean
  self_rss?: number | null
  self_cpu?: number | null
  disks?: Disk[]
}

export type Severity = 'info' | 'warning' | 'critical'

export interface MonitorEvent {
  id: number
  key: string
  kind: string
  severity: Severity
  title: string
  detail?: string
  metric?: string
  unit?: string
  started: number
  ended: number | null
  peak?: number | null
  seen?: number
  context?: {
    reading?: Record<string, number | null>
    top_cpu?: Array<{ pid: number; name: string; rss: number; cpu: number }>
    top_memory?: Array<{ pid: number; name: string; rss: number; cpu: number }>
  }
}

export interface MonitorNow {
  enabled: boolean
  running: boolean
  interval: number
  topbar: 'off' | 'numbers' | 'sparks' | 'dot'
  host: { name: string; os: string; cpus: number; threads: number; memory: number; boot: number }
  ts: number | null
  sample: Sample | null
  spark: Sample[]
  ping: { ok: boolean; ms: number | null; at: number; host: string } | null
  cost: { ms_per_sample: number; cpu_pct: number } | null
  open: MonitorEvent[]
  today: Partial<Record<Severity, number>>
  unseen: number
}

export interface Series {
  from: number
  to: number
  tier: number
  bucket: number
  points: number
  series: Record<string, Array<number | null>>
  gaps: Array<[number, number]>
  events: MonitorEvent[]
}

export const RANGES = ['15m', '1h', '6h', '24h', '7d', '30d', '90d', '1y'] as const
export type Range = (typeof RANGES)[number]

/** One hue per measure (tokens.css --m-*). */
export const HUE = {
  cpu: 'var(--m-cpu)', mem: 'var(--m-mem)', disk: 'var(--m-disk)', rx: 'var(--m-rx)',
  tx: 'var(--m-tx)', ping: 'var(--m-ping)', temp: 'var(--m-temp)',
  // Slightly Parallel's own memory: the product's colour among the machine's.
  self: 'var(--brand)',
} as const

export const SEVERITY_COLOR: Record<Severity, string> = {
  info: 'var(--text-tertiary)', warning: 'var(--status-amber)', critical: 'var(--status-red)',
}

function useVisible(): boolean {
  const [v, setV] = useState(() => typeof document === 'undefined' || document.visibilityState !== 'hidden')
  useEffect(() => {
    const on = () => setV(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', on)
    return () => document.removeEventListener('visibilitychange', on)
  }, [])
  return v
}

export function useMonitorNow() {
  const visible = useVisible()
  const q = useQuery({
    queryKey: ['monitor', 'now'],
    queryFn: ({ signal }) => getJson<MonitorNow>('/api/monitor/now', signal),
    refetchInterval: (query) => {
      const d = query.state.data
      if (!visible) return false
      if (d && !d.enabled) return 30_000
      return Math.max(2, d?.interval ?? 5) * 1000
    },
    staleTime: 1000,
  })
  return q
}

export function useMonitorSeries(range: Range | { from: number; to: number }, live = true) {
  const visible = useVisible()
  const key = typeof range === 'string' ? range : `${Math.round(range.from)}-${Math.round(range.to)}`
  const url = typeof range === 'string' ? `/api/monitor/series?range=${range}` : `/api/monitor/series?from=${range.from}&to=${range.to}`
  const every = typeof range === 'string'
    ? ({ '15m': 5_000, '1h': 10_000, '6h': 30_000, '24h': 60_000 } as Record<string, number>)[range] ?? 300_000
    : 0
  return useQuery({
    queryKey: ['monitor', 'series', key],
    queryFn: ({ signal }) => getJson<Series>(url, signal),
    refetchInterval: live && visible && every ? every : false,
    placeholderData: (prev) => prev,
  })
}

export function useMonitorEvents(params: { days?: number; severity?: string; q?: string; limit?: number } = {}) {
  const qs = new URLSearchParams()
  if (params.days) qs.set('days', String(params.days))
  if (params.severity) qs.set('severity', params.severity)
  if (params.q) qs.set('q', params.q)
  qs.set('limit', String(params.limit ?? 300))
  return useQuery({
    queryKey: ['monitor', 'events', qs.toString()],
    queryFn: ({ signal }) => getJson<{ events: MonitorEvent[]; total: number; days?: Record<string, { n: number; worst: Severity }>; watched?: string[] }>(
      `/api/monitor/events?${qs}`, signal),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  })
}

export function useMonitorEvent(id: number | null) {
  return useQuery({
    queryKey: ['monitor', 'event', id],
    queryFn: ({ signal }) => getJson<{ event: MonitorEvent; processes: Array<{ ts: number; pid: number; name: string; label: string; rss: number; cpu: number }> }>(
      `/api/monitor/events/${id}`, signal),
    enabled: id != null,
  })
}

export function useMonitorProcesses(sort: 'rss' | 'cpu') {
  const visible = useVisible()
  return useQuery({
    queryKey: ['monitor', 'processes', sort],
    queryFn: ({ signal }) => getJson<{ at: number | null; count: number; processes: Array<{ pid: number; name: string; rss: number; cpu: number }>; programs: Array<{ name: string; rss: number; cpu: number; n: number }> }>(
      `/api/monitor/processes?sort=${sort}&limit=12`, signal),
    refetchInterval: visible ? 15_000 : false,
    placeholderData: (prev) => prev,
  })
}

export function useMonitorStorage() {
  return useQuery({
    queryKey: ['monitor', 'storage'],
    queryFn: ({ signal }) => getJson<{ file: string; bytes: number; tiers: Record<string, { rows: number; oldest: number }>; events: { rows: number; oldest: number | null } }>(
      '/api/monitor/storage', signal),
    refetchInterval: 60_000,
  })
}

/** The monitor.* settings, and a save that refreshes what depends on them. */
export function useMonitorSettings() {
  const values = useSettingsValues()
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: (v: Record<string, number | boolean | string>) => saveSettings(v),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY })
      void qc.invalidateQueries({ queryKey: ['monitor'] })
    },
  })
  return { values, save: save.mutate, saving: save.isPending, error: save.error as Error | null }
}

export function useSeenAll() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id?: number) => postJson(id == null ? '/api/monitor/events/seen' : `/api/monitor/events/${id}/seen`, { actor: 'operator' }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['monitor'] }),
  })
}

/* ------------------------------------------------------------------ words */

export { bytes, duration } from '../utils/format'
import { bytes } from '../utils/format'
import { t, locale } from '../i18n/scope/shell'


export const rate = (b: number | null | undefined) => (b == null ? '—' : `${bytes(b)}/s`)
export const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v)}%`)
export const ms = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v)} ms`)


export function clock(ts: number, withDay = false): string {
  const d = new Date(ts * 1000)
  // 24-hour in both languages: en-GB, not en-US.
  const loc = locale()
  const hm = d.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' })
  if (!withDay) return hm
  const today = new Date()
  const same = d.toDateString() === today.toDateString()
  return same ? t('today {time}', { time: hm }) : `${dayMonth(d)} ${hm}`
}

/** The worst thing going on now, as the health word the page leads with. */
export function health(now: MonitorNow | undefined): { word: string; tone: Severity | 'ok' | 'off' } {
  if (!now) return { word: t('Reading…'), tone: 'info' }
  if (!now.enabled) return { word: t('Monitor off'), tone: 'off' }
  const worst = now.open.find((e) => e.severity === 'critical') ?? now.open.find((e) => e.severity === 'warning')
  if (worst) return { word: worst.title, tone: worst.severity }
  return { word: t('All normal'), tone: 'ok' }
}
