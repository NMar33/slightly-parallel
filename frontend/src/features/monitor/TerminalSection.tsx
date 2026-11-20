import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download } from 'lucide-react'

import { StatTile } from '../../components/StatTile'
import { ErrorBanner } from '../../components/states'
import { getJson, postJson } from '../../lib/getJson'
import { bytes, clock } from '../../lib/monitor'
import { termLog, type LogMode } from '../terminal/telemetry'
import { t } from '../../i18n/scope/pages'

/**
 * The terminal's part of the Monitor page (tk_f89e84c4): the terminal log
 * of today (backend/termlog.py). The day in one line, the hours, what the
 * rules found, the server's tmux calls, and two buttons: a report for a bug,
 * and the full log for an hour.
 */

interface Finding { t: number; kind: string; sid: string; p: string; doing: string; n: number; what: string }
interface Hour { h: number; frames: number; slow: number; stalls: number; errors: number; reconnects: number; findings: number; p95: number }
export interface TermLogSummary {
  day: string
  mode: LogMode
  setting: LogMode
  full_until: number | null
  totals: {
    frames: number; slow: number; stalls: number; errors: number; reconnects: number; findings: number
    in: number; out: number; pastes: number; keys: number; wheels: number; longtasks: number; fetch_errors: number
    p50: number; p95: number; max: number; page_minutes: number; self_ms: number
  }
  hours: Hour[]
  findings: Finding[]
  by_kind: Record<string, number>
  scroll: Record<string, number>
  paste: Record<string, number>
  mem: { heap?: number; app_kb?: number; t?: number }
  server: {
    tmux: Record<string, { n: number; avg: number; max: number; timeouts: number; slow: number }>
    writes: { n: number; max: number; slow: number }
    sends: { n: number; max: number; slow: number }
  }
  files: { folder: string; light_bytes: number; full_bytes: number; full_files: number }
}

const KIND: Record<string, string> = {
  'paste-twice': t('Paste sent twice'),
  'scroll-stall': t('Scrolling stalled'),
  reconnect: t('Connection dropped'),
  fetch: t('Request failed'),
  'click-typed': t('Click counted as typing'),
  'slow-frames': t('Slow frames for a minute'),
  error: t('Page error'),
  'tmux-timeout': t('tmux did not answer'),
  'write-stall': t('Writing to the terminal stalled'),
  'keys-lost': t('Keys pressed, nothing sent'),
}
const DOING: Record<string, string> = {
  scroll: t('scrolling'), output: t('output'), paste: t('paste'), typing: t('typing'), idle: '—', server: t('server'),
}
const MODE_WORD: Record<LogMode, string> = { off: t('off'), light: t('light'), full: t('full') }

/** What the number of a finding means, with its unit. */
function amount(f: Finding): string {
  if (f.kind === 'paste-twice') return t('{n} characters', { n: f.n })
  if (f.kind === 'slow-frames') return t('p95 {n} ms', { n: f.n })
  if (f.kind === 'tmux-timeout') return t('{n} times', { n: f.n })
  if (f.kind === 'error') return ''
  if (f.kind === 'keys-lost') return t('{n} ms after the window got focus', { n: f.n })
  return `${f.n} ${t('ms')}`
}

function Bars({ hours, pick, color, label }: { hours: Hour[]; pick: (h: Hour) => number; color: string; label: string }) {
  const vals = hours.map(pick)
  const top = Math.max(1, ...vals)
  const total = vals.reduce((a, b) => a + b, 0)
  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="flex items-baseline gap-6">
        <span className="text-11 text-secondary">{label}</span>
        <span className="ml-auto text-11 font-mono tabular text-tertiary">{total}</span>
      </div>
      <svg viewBox="0 0 240 28" preserveAspectRatio="none" className="w-full h-28" role="img" aria-label={`${label}: ${total}`}>
        <line x1="0" x2="240" y1="27.5" y2="27.5" stroke="var(--border-subtle)" strokeWidth="1" />
        {vals.map((v, i) => v > 0 && (
          <rect key={i} x={i * 10 + 1} width="8" y={28 - Math.max(2, (26 * v) / top)} height={Math.max(2, (26 * v) / top)} rx="1" fill={color}>
            <title>{`${String(i).padStart(2, '0')}:00 · ${v}`}</title>
          </rect>
        ))}
      </svg>
    </div>
  )
}

function HourAxis() {
  return (
    <div className="flex justify-between text-10 font-mono text-tertiary">
      {[0, 6, 12, 18, 24].map((h) => <span key={h}>{String(h).padStart(2, '0')}</span>)}
    </div>
  )
}

export function TerminalSection() {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['terminal-log', 'summary'],
    queryFn: ({ signal }) => getJson<TermLogSummary>('/api/terminal/log/summary', signal),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })
  const s = q.data
  const switchTo = async (mode: LogMode, hours?: number) => {
    const got = await postJson<{ mode: LogMode }>('/api/terminal/log/mode', hours ? { mode, hours } : { mode })
    termLog.setMode(got.mode)
    await qc.invalidateQueries({ queryKey: ['terminal-log'] })
  }
  const tot = s?.totals
  const healthy = tot ? tot.findings === 0 && tot.errors === 0 : true
  const tmux = s ? Object.entries(s.server.tmux).sort((a, b) => b[1].n - a[1].n) : []

  return (
    <section aria-label={t('Terminal')} className="flex flex-col gap-16 min-w-0">
      <div className="flex items-center gap-8 flex-wrap">
        <h2 className="text-16 font-semibold text-primary">{t('Terminal')}</h2>
        <span className="text-12 text-tertiary">{t('How the terminal works today: slow frames, stalls, errors and lost connections. What you type and what it prints is not kept.')}</span>
        <div className="ml-auto flex items-center gap-8">
          {s && (
            <span className="text-11 font-mono text-tertiary" data-testid="term-log-mode">
              {t('Log: {mode}', { mode: MODE_WORD[s.mode] })}
              {s.mode === 'full' && s.full_until ? ` · ${t('until {time}', { time: clock(s.full_until) })}` : ''}
            </span>
          )}
          {s && s.mode !== 'full' ? (
            <button type="button" onClick={() => void switchTo('full', 1)}
              className="inline-flex items-center gap-4 whitespace-nowrap h-24 px-8 rounded-input border border-border-subtle text-11 font-mono text-secondary hover:text-primary hover:border-brand">
              {t('Turn on the full log for 1 hour')}
            </button>
          ) : s && (
            <button type="button" onClick={() => void switchTo('light')}
              className="inline-flex items-center gap-4 whitespace-nowrap h-24 px-8 rounded-input border border-brand text-11 font-mono text-primary bg-brand-glow">
              {t('Back to the light log')}
            </button>
          )}
          <a href="/api/terminal/log/report" download
            title={t('One file: today\'s counts, the last hour of the full log if it was on, versions, the system and the terminal settings. No typed or printed text. Attach it to a bug report.')}
            className="inline-flex items-center gap-4 whitespace-nowrap h-24 px-8 rounded-input border border-border-subtle text-11 font-mono text-secondary hover:text-primary hover:border-brand no-underline">
            <Download size={12} aria-hidden /> {t('Download report')}
          </a>
        </div>
      </div>

      {q.isError && <ErrorBanner title={t('Could not read the terminal log')} onRetry={() => void q.refetch()} hideDismiss />}

      {s && s.mode === 'off' && tot && tot.page_minutes === 0 && (
        <p className="text-12 text-tertiary">{t('The terminal log is off. Turn it on in Settings › Terminal.')}</p>
      )}

      {s && tot && (
        <>
          <p className={`text-13 ${healthy ? 'text-primary' : 'text-status-amber'}`} data-testid="term-log-health">
            {t('Today: {frames} frames, p95 {p95} ms, {slow} slow · {stalls} stalls · {errors} errors · {reconnects} reconnects · {findings} found', {
              frames: tot.frames.toLocaleString(), p95: tot.p95, slow: tot.slow, stalls: tot.stalls, errors: tot.errors, reconnects: tot.reconnects, findings: tot.findings,
            })}
          </p>

          <div className="grid gap-10 grid-cols-[repeat(auto-fit,minmax(160px,1fr))]">
            <StatTile label={t('Frames')} value={`p95 ${tot.p95} ms`} sub={t('p50 {p50} ms · worst {max} ms', { p50: tot.p50, max: Math.round(tot.max) })} hot={tot.p95 > 50} />
            <StatTile label={t('Found')} value={String(tot.findings)} hot={tot.findings > 0}
              sub={Object.entries(s.by_kind).map(([k, n]) => `${KIND[k] ?? k} ${n}`).join(' · ') || t('nothing')} />
            <StatTile label={t('Traffic')} value={bytes(tot.in)} sub={t('in · {out} out · {keys} keys · {pastes} pastes', { out: bytes(tot.out), keys: tot.keys, pastes: tot.pastes })} />
            <StatTile label={t('Memory')} value={s.mem.app_kb ? bytes(s.mem.app_kb * 1024) : s.mem.heap ? bytes(s.mem.heap) : '—'}
              sub={s.mem.app_kb ? t('the window · page {heap}', { heap: bytes(s.mem.heap ?? 0) }) : t('the page')} />
          </div>

          <div className="grid gap-12 md:grid-cols-2 xl:grid-cols-4 rounded-card border border-border-subtle p-12">
            <div className="flex flex-col gap-4"><Bars hours={s.hours} pick={(h) => h.slow} color="var(--m-cpu)" label={t('Slow frames (over 50 ms)')} /><HourAxis /></div>
            <div className="flex flex-col gap-4"><Bars hours={s.hours} pick={(h) => h.stalls} color="var(--status-amber)" label={t('Scroll stalls')} /><HourAxis /></div>
            <div className="flex flex-col gap-4"><Bars hours={s.hours} pick={(h) => h.errors} color="var(--status-red)" label={t('Errors')} /><HourAxis /></div>
            <div className="flex flex-col gap-4"><Bars hours={s.hours} pick={(h) => h.reconnects} color="var(--m-ping)" label={t('Reconnects')} /><HourAxis /></div>
          </div>

          <div className="grid gap-16 lg:grid-cols-[minmax(0,1fr)_320px] items-start">
            <section className="flex flex-col gap-6 min-w-0">
              <h3 className="text-14 font-semibold text-primary">{t('Found today')}</h3>
              <ol className="rounded-card border border-border-subtle bg-surface max-h-[40vh] overflow-y-auto text-12" aria-label={t('Found today')} data-testid="term-log-findings">
                {s.findings.map((f, i) => (
                  <li key={`${f.t}-${i}`} className="px-10 py-4 border-b border-border-subtle last:border-b-0 flex gap-8 items-baseline">
                    <span className="font-mono text-tertiary shrink-0">{clock(f.t / 1000)}</span>
                    <span className={`shrink-0 ${f.kind === 'error' || f.kind === 'fetch' ? 'text-status-red' : 'text-status-amber'}`} data-kind={f.kind}>{KIND[f.kind] ?? f.kind}</span>
                    <span className="text-secondary truncate min-w-0">
                      {[DOING[f.doing] ?? f.doing, f.p, f.sid, amount(f), f.kind === 'fetch' || f.kind === 'error' || f.kind === 'tmux-timeout' || f.kind === 'keys-lost' ? f.what : ''].filter(Boolean).join(' · ')}
                    </span>
                  </li>
                ))}
                {s.findings.length === 0 && <li className="px-10 py-8 text-tertiary italic">{t('Nothing found today.')}</li>}
              </ol>
            </section>
            <aside className="flex flex-col gap-8 min-w-0">
              <h3 className="text-14 font-semibold text-primary">{t('Server')}</h3>
              <table className="w-full text-11 font-mono tabular">
                <thead>
                  <tr className="text-10 uppercase tracking-wide text-tertiary">
                    <th className="text-left font-medium">tmux</th><th className="text-right font-medium">{t('calls')}</th>
                    <th className="text-right font-medium">{t('avg ms')}</th><th className="text-right font-medium">{t('max ms')}</th>
                    <th className="text-right font-medium">{t('no answer')}</th>
                  </tr>
                </thead>
                <tbody>
                  {tmux.slice(0, 8).map(([cmd, v]) => (
                    <tr key={cmd} className="text-secondary">
                      <td className="truncate max-w-[110px]">{cmd}</td><td className="text-right">{v.n}</td><td className="text-right">{v.avg}</td>
                      <td className={`text-right ${v.max >= 500 ? 'text-status-amber' : ''}`}>{Math.round(v.max)}</td>
                      <td className={`text-right ${v.timeouts ? 'text-status-red' : 'text-tertiary'}`}>{v.timeouts}</td>
                    </tr>
                  ))}
                  {tmux.length === 0 && <tr><td colSpan={5} className="text-tertiary italic">{t('No tmux calls today.')}</td></tr>}
                </tbody>
              </table>
              <p className="text-11 font-mono text-tertiary">
                {t('Writes to terminals: {n}, slowest {max} ms · sends to the window: {sends}, {slow} slow', {
                  n: s.server.writes.n, max: Math.round(s.server.writes.max), sends: s.server.sends.n, slow: s.server.sends.slow,
                })}
              </p>
              <p className="text-11 font-mono text-tertiary">
                {t('Wheel: {paths}', { paths: Object.entries(s.scroll).map(([k, n]) => `${k} ${n}`).join(', ') || '—' })}
                {' · '}
                {t('Paste: {paths}', { paths: Object.entries(s.paste).map(([k, n]) => `${k} ${n}`).join(', ') || '—' })}
              </p>
              <p className="text-11 font-mono text-tertiary break-all">
                {t('Log files: light {light} (14 days), full {full} · {folder}', { light: bytes(s.files.light_bytes), full: bytes(s.files.full_bytes), folder: s.files.folder })}
                {' · '}
                {t('the log itself: {ms} ms today', { ms: Math.round(tot.self_ms) })}
              </p>
            </aside>
          </div>
        </>
      )}
    </section>
  )
}
