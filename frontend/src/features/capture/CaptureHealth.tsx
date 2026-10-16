/**
 * Is capture working? (backend capturewatch.py, /api/capture/health)
 *
 * The top bar shows `CaptureAlert` only when something is wrong — a chat
 * that Claude Code has and Slightly Parallel does not, or a hook that failed in the
 * last day — and it opens the Health page, where `CaptureSection` says what
 * and what to do.
 */

import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { toast } from 'sonner'

import { getJson } from '../../lib/getJson'
import { postIgnore, SETUP_INFO_KEY, TOOL_NAMES, type ToolKey } from '../setup/data'
import { t, tn, locale } from '../../i18n/scope/system'

interface CaptureHealth {
  ok: boolean
  missed: Array<{ project: string; session: string; agent_id: string; prompt_at: number; captured_at: number | null; why: string }>
  errors: Array<{ at: string; project: string; agent_id: string; tool: string; error: string }>
  errors_n: number
  watched: number
  /** Sessions of the last week that were never recorded, per project and tool. */
  lost?: Array<{ project: string; tool: ToolKey; sessions: number; last_at: number; ignored: boolean }>
}

const lostNow = (d: CaptureHealth) => (d.lost ?? []).filter((g) => !g.ignored)

function useCaptureHealth() {
  return useQuery({
    queryKey: ['capture', 'health'],
    queryFn: ({ signal }) => getJson<CaptureHealth>('/api/capture/health', signal),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

const time = (ts: number) => new Date(ts * 1000).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })

export function CaptureAlert() {
  const d = useCaptureHealth().data
  if (!d || d.ok) return null
  const chats = d.missed.length + lostNow(d).reduce((a, g) => a + g.sessions, 0)
  const word = chats
    ? tn(chats, '{n} chat not recorded', '{n} chats not recorded')
    : tn(d.errors_n, '{n} capture error', '{n} capture errors')
  return (
    <Link to="/monitor#capture" title={t('Some messages were not recorded. Open Monitor.')}
      className="inline-flex items-center gap-6 h-24 px-8 rounded-pill border border-status-amber text-11 font-mono text-status-amber hover:bg-hover whitespace-nowrap">
      <span className="w-6 h-6 rounded-pill bg-status-amber animate-pulse" aria-hidden />
      {word}
    </Link>
  )
}

const day = (ts: number) => new Date(ts * 1000).toLocaleString(locale(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export function CaptureSection() {
  const q = useCaptureHealth()
  const d = q.data
  const queryClient = useQueryClient()
  const ignore = (project: string, tool: ToolKey) => postIgnore(project, tool).then(() => {
    void queryClient.invalidateQueries({ queryKey: ['capture', 'health'] })
    void queryClient.invalidateQueries({ queryKey: SETUP_INFO_KEY })
  }).catch(() => toast.error(t('Could not save that')))
  const gone = d ? lostNow(d) : []
  return (
    <section id="capture" className="flex flex-col gap-8 min-w-0 scroll-mt-16">
      <div className="flex items-baseline gap-8">
        <h2 className="text-14 font-semibold text-primary">{t('Capture')}</h2>
        {d && <span className="text-11 font-mono text-tertiary">{tn(d.watched, '{n} active Claude Code session checked', '{n} active Claude Code sessions checked')}</span>}
      </div>
      {!d && <p className="text-12 text-tertiary">{t('Checking…')}</p>}
      {d?.ok && (
        <p className="text-12 text-secondary">{t('Every message in the active sessions was recorded, and no hook failed in the last day.')}</p>
      )}
      {d && d.missed.length > 0 && (
        <div className="rounded-card border border-status-amber/50 bg-surface p-12 flex flex-col gap-6">
          <p className="text-13 text-primary">{t('Some Claude Code messages were not recorded.')}</p>
          {d.missed.map((m) => (
            <div key={m.session} className="text-12 font-mono text-secondary">
              {m.project} · {m.agent_id} · {m.captured_at ? t('last message {time}, last recorded {recorded}', { time: time(m.prompt_at), recorded: time(m.captured_at) }) : t('last message {time}', { time: time(m.prompt_at) })} — {m.why}
            </div>
          ))}
          <p className="text-12 text-tertiary">
            {t('Usually the hook is not installed in the folder that session runs in, or Python is missing there.')}{' '}
            {t('Open')} <Link to="/setup" className="text-brand hover:underline">{t('Setup')}</Link> {t('and install the hooks for that project again, then restart the session.')}
          </p>
        </div>
      )}
      {gone.length > 0 && (
        <div className="rounded-card border border-status-amber/50 bg-surface p-12 flex flex-col gap-6">
          <p className="text-13 text-primary">{t('Sessions of the last week that were never recorded.')}</p>
          {gone.map((g) => (
            <div key={`${g.project}:${g.tool}`} className="flex items-center gap-8 flex-wrap text-12">
              <span className="font-mono text-secondary">
                {g.project} · {TOOL_NAMES[g.tool]} · {tn(g.sessions, '{n} session', '{n} sessions')} · {t('the last {time}', { time: day(g.last_at) })}
              </span>
              <Link to="/setup" className="text-brand hover:underline">{t('Connect it in Setup')}</Link>
              <button type="button" onClick={() => void ignore(g.project, g.tool)}
                className="text-tertiary hover:text-primary">{t('Not needed')}</button>
            </div>
          ))}
          <p className="text-12 text-tertiary">
            {t('The tool worked in that project folder and nothing reached Slightly Parallel: the tool is not connected there, or its hooks did not run. Codex runs the hooks of a project only once you trust them.')}
          </p>
        </div>
      )}
      {d && d.errors_n > 0 && (
        <div className="rounded-card border border-status-red/40 bg-surface p-12 flex flex-col gap-4">
          <p className="text-13 text-primary">{d.errors_n} hook failure{d.errors_n === 1 ? '' : 's'} in the last day. Those turns were not recorded.</p>
          {d.errors.slice(-8).reverse().map((e, i) => (
            <div key={i} className="text-12 font-mono text-secondary break-all">{e.at.slice(11, 16)} · {e.project} · {e.agent_id} · {e.error}</div>
          ))}
        </div>
      )}
    </section>
  )
}
