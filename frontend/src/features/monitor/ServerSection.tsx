import { useMemo, useState } from 'react'
import { StatTile } from '../../components/StatTile'
import { BackupProof } from '../capture/BackupProof'
import { CaptureSection } from '../capture/CaptureHealth'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'

import { CopyButton } from '../../components/CopyButton'
import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { useHashState } from '../../hooks/useHashState'
import { getJson, getText } from '../../lib/getJson'
import { t } from '../../i18n/scope/pages'

/**
 * The server's half of the Monitor page — is the server well, and its log.
 *
 * Four numbers at the top, capture and backups, the slow paths under them,
 * the log tail under that, and one button that copies the whole section as
 * plain text. The text is what an operator pastes to an AI when something
 * is slow or wrong: it holds what a person who wrote the server would ask
 * for first. It was the Health page until the two pages became one.
 */

interface PathStat { path: string; n: number; p50_ms: number; max_ms: number; total_ms: number; errors: number }
interface LogRecord {
  ts: number; level: string; logger: string; msg: string
  method?: string; path?: string; status?: number; ms?: number; why?: string; exc?: string
}
interface LogsAnswer {
  summary: {
    started_at: number; uptime_s: number; data_root: string; log_file: string; log_file_bytes: number
    view_age_ms: number; load_errors: Array<{ file: string; stage: string; error: string }>
    rss_mb: number; threads: number; records_n: number; since: number
    requests: { n: number; slow_n: number; by_path: PathStat[] }
    rebuilds: { n: number; p50_ms: number; max_ms: number; last_ms: number }
    errors_n: number; warnings_n: number; slow_request_ms: number
  }
  records: LogRecord[]
}

const LEVELS: Array<[string, string]> = [['INFO', t('all')], ['WARNING', t('warnings')], ['ERROR', t('errors')]]

function uptime(s: number): string {
  if (s < 3600) return t('{m} min', { m: Math.floor(s / 60) })
  if (s < 86400) return t('{h} h {m} min', { h: Math.floor(s / 3600), m: Math.floor((s % 3600) / 60) })
  return t('{d} d {h} h', { d: Math.floor(s / 86400), h: Math.floor((s % 86400) / 3600) })
}

function when(ts: number): string {
  const d = new Date(ts * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function lineOf(r: LogRecord): string {
  if (r.msg === 'req' && r.path) return `${r.method ?? ''} ${r.path} → ${r.status ?? ''} in ${r.ms ?? 0} ms`
  return `${r.msg}${r.ms != null ? ` (${r.ms} ms)` : ''}${r.why ? ` — ${r.why}` : ''}${r.exc ? ` | ${r.exc}` : ''}`
}

export function ServerSection() {
  const [hash, setHash] = useHashState()
  const level = LEVELS.some(([k]) => k === hash.level) ? hash.level! : 'INFO'
  const [find, setFind] = useState('')

  const q = useQuery({
    queryKey: ['logs', level],
    queryFn: ({ signal }) => getJson<LogsAnswer>(`/api/logs?level=${level}&limit=400`, signal),
    staleTime: 5_000,
  })
  const text = useQuery({
    queryKey: ['logs', 'text', level],
    queryFn: ({ signal }) => getText(`/api/logs/text?level=${level}&limit=400`, signal),
    staleTime: 5_000,
  })

  const s = q.data?.summary
  const needle = find.trim().toLowerCase()
  const rows = useMemo(() => {
    const all = q.data?.records ?? []
    const shown = needle ? all.filter((r) => `${r.logger} ${lineOf(r)}`.toLowerCase().includes(needle)) : all
    return shown.slice().reverse()
  }, [q.data, needle])

  const well = s ? s.errors_n === 0 && s.load_errors.length === 0 : null
  const tone = (n: number, warn: number) => (n === 0 ? 'text-primary' : n < warn ? 'text-status-amber' : 'text-status-red')

  return (
    <section aria-label={t('Server')} className="flex flex-col gap-24 min-w-0">
      <div className="flex items-center gap-8 flex-wrap">
        <h2 className="text-16 font-semibold text-primary">{t('Server')}</h2>
        <span className="text-12 text-tertiary">{t('Server status, slow requests and the log. When something is wrong, copy the page as text for an AI assistant.')}</span>
        <div className="ml-auto flex items-center gap-8">
          <button
            type="button"
            onClick={() => { void q.refetch(); void text.refetch() }}
            className="inline-flex items-center gap-4 h-24 px-8 rounded-input border border-border-subtle text-11 font-mono text-secondary hover:text-primary hover:border-brand"
            title={t('Read the log again')}
          >
            <RefreshCw size={11} aria-hidden /> {t('refresh')}
          </button>
          <CopyButton
            text={() => text.data ?? ''}
            title={t('Copy the whole page as plain text')}
            label={t('copy for AI')}
            className="inline-flex items-center gap-4 whitespace-nowrap h-24 px-8 rounded-input border border-brand text-11 font-mono text-primary bg-brand-glow"
          />
        </div>
      </div>

      {q.isLoading && !q.data && <LoadingSkeleton variant="card" count={2} />}
      {q.isError && <ErrorBanner title={t('Could not read the log')} onRetry={() => void q.refetch()} hideDismiss />}

      {s && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-10">
            <Stat label={t('Server')} value={well ? t('well') : t('needs a look')} valueClass={well ? 'text-primary' : 'text-status-red'}
              sub={t('up {uptime} · {mb} MB · {threads} threads', { uptime: uptime(s.uptime_s), mb: s.rss_mb, threads: s.threads })} />
            <Stat label={t('Data')} value={s.load_errors.length === 0 ? t('every file read') : t('{n} unreadable', { n: s.load_errors.length })}
              valueClass={s.load_errors.length === 0 ? 'text-primary' : 'text-status-red'}
              sub={t('views {age} old · rebuilt {n} times, last {last} ms, max {max} ms', { age: s.view_age_ms < 60_000 ? t('{s} s', { s: Math.round(s.view_age_ms / 1000) }) : t('{m} min', { m: Math.round(s.view_age_ms / 60_000) }), n: s.rebuilds.n, last: s.rebuilds.last_ms, max: s.rebuilds.max_ms })} />
            <Stat label={t('Requests')} value={String(s.requests.n)} valueClass="text-primary"
              sub={t('{slow} slow (over {ms} ms) in the last {lines} lines', { slow: s.requests.slow_n, ms: s.slow_request_ms, lines: s.records_n })} />
            <Stat label={t('Errors')} value={String(s.errors_n)} valueClass={tone(s.errors_n, 3)}
              sub={t('{n} warnings · log {kb} KB, rotates at 5 MB', { n: s.warnings_n, kb: Math.round(s.log_file_bytes / 1024) })} />
          </div>

          <CaptureSection />
          <section className="flex flex-col gap-8 min-w-0">
            <h2 className="text-14 font-semibold text-primary">{t('Backups')}</h2>
            <BackupProof />
          </section>

          {s.load_errors.length > 0 && (
            <div className="rounded-card border border-status-red/40 bg-surface p-12 flex flex-col gap-4">
              <div className="text-10 uppercase tracking-wide font-mono text-status-red">{t('Files that could not be read')}</div>
              {s.load_errors.map((e) => (
                <div key={e.file + e.stage} className="text-12 font-mono text-secondary break-all">{e.file} · {e.stage} · {e.error}</div>
              ))}
              <Link to="/internals#doctor" className="text-11 text-brand hover:underline">{t('Run the data check')}</Link>
            </div>
          )}

          <section className="flex flex-col gap-8 min-w-0">
            <div className="flex items-baseline gap-8">
              <h2 className="text-14 font-semibold text-primary">{t('Time per request path')}</h2>
              <span className="text-11 font-mono text-tertiary">{t('by path, the costliest first, since {time}', { time: when(s.since) })}</span>
            </div>
            <div className="overflow-x-auto rounded-card border border-border-subtle bg-surface">
              <table className="w-full text-12 tabular">
                <thead>
                  <tr className="text-10 uppercase tracking-wide font-mono text-tertiary border-b border-border-subtle">
                    <th className="text-left px-10 py-6 font-medium">{t('path')}</th>
                    <th className="text-right px-10 py-6 font-medium">{t('calls')}</th>
                    <th className="text-right px-10 py-6 font-medium">{t('p50 ms')}</th>
                    <th className="text-right px-10 py-6 font-medium">{t('max ms')}</th>
                    <th className="text-right px-10 py-6 font-medium">{t('total ms')}</th>
                    <th className="text-right px-10 py-6 font-medium">{t('errors')}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.requests.by_path.map((p) => (
                    <tr key={p.path} className="border-b border-border-subtle last:border-b-0">
                      <td className="px-10 py-4 font-mono text-secondary">{p.path}</td>
                      <td className="px-10 py-4 text-right text-secondary">{p.n}</td>
                      <td className={`px-10 py-4 text-right ${p.p50_ms >= s.slow_request_ms ? 'text-status-amber' : 'text-secondary'}`}>{p.p50_ms}</td>
                      <td className={`px-10 py-4 text-right ${p.max_ms >= s.slow_request_ms ? 'text-status-amber' : 'text-secondary'}`}>{p.max_ms}</td>
                      <td className="px-10 py-4 text-right text-secondary">{p.total_ms}</td>
                      <td className={`px-10 py-4 text-right ${p.errors ? 'text-status-red' : 'text-tertiary'}`}>{p.errors}</td>
                    </tr>
                  ))}
                  {s.requests.by_path.length === 0 && (
                    <tr><td colSpan={6} className="px-10 py-8 text-tertiary italic">{t('No request yet since the server started.')}</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="flex flex-col gap-8 min-w-0">
            <div className="flex items-center gap-8 flex-wrap">
              <h2 className="text-14 font-semibold text-primary">{t('Log')}</h2>
              <span className="inline-flex items-center rounded-input border border-border-subtle overflow-hidden" role="tablist" aria-label={t('Log level')}>
                {LEVELS.map(([k, label], i) => (
                  <button key={k} type="button" role="tab" aria-selected={level === k}
                    onClick={() => setHash({ level: k === 'INFO' ? '' : k })}
                    className={`px-8 h-20 text-10 font-mono ${i > 0 ? 'border-l border-border-subtle' : ''} ${level === k ? 'bg-brand-glow text-primary' : 'text-tertiary hover:text-primary'}`}>
                    {label}
                  </button>
                ))}
              </span>
              <input
                value={find}
                onChange={(e) => setFind(e.currentTarget.value)}
                placeholder={t('Find in the log')}
                aria-label={t('Find in the log')}
                className="w-[200px] rounded-input border border-border-subtle bg-surface px-8 py-3 text-12 text-primary placeholder:text-tertiary focus:outline-none focus:border-brand"
              />
              <span className="ml-auto text-11 font-mono text-tertiary">{t('{n} lines, newest first', { n: rows.length })}{s.log_file ? ` · ${t('file {path}', { path: s.log_file })}` : ''}</span>
            </div>
            <ol className="rounded-card border border-border-subtle bg-surface max-h-[60vh] overflow-y-auto font-mono text-11 leading-relaxed" aria-label={t('Log lines')}>
              {rows.map((r, i) => (
                <li key={`${r.ts}-${i}`} className={`px-10 py-2 border-b border-border-subtle last:border-b-0 flex gap-8 ${
                  r.level === 'ERROR' || r.level === 'CRITICAL' ? 'text-status-red' : r.level === 'WARNING' ? 'text-status-amber' : 'text-secondary'}`}>
                  <span className="text-tertiary shrink-0">{when(r.ts)}</span>
                  <span className="w-[56px] shrink-0">{r.level.toLowerCase()}</span>
                  <span className="text-tertiary shrink-0 w-[96px] truncate" title={r.logger}>{r.logger.replace(/^sp\./, '')}</span>
                  <span className="min-w-0 break-all">{lineOf(r)}</span>
                </li>
              ))}
              {rows.length === 0 && <li className="px-10 py-8 text-tertiary italic">{t('Nothing at this level.')}</li>}
            </ol>
          </section>
        </>
      )}
    </section>
  )
}

function Stat({ label, value, valueClass, sub }: { label: string; value: string; valueClass: string; sub: string }) {
  return <StatTile label={label} value={value} valueClassName={valueClass} sub={sub} wrapSub />
}
