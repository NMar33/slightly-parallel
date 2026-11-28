import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Moon, X } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { toast } from 'sonner'

import '../design/aqua.css'
import { t } from '../../../i18n/scope/aqua'
import { ApiError, getJson, postJson } from '../../../lib/getJson'
import { saveSettings, SETTINGS_QUERY_KEY } from '../../../lib/settings'
import { terminalLimitPending, useTerminalLimit, type PendingTerminal, type TerminalLimitSnapshot } from '../../../lib/terminalLimit'
import { useModalA11y } from '../../project/useModalA11y'
import { limitAgents } from './limitLabels'
import { LimitMemory } from './LimitMemory'
import { LimitTerminalList } from './LimitTerminalList'
import { needsCloseConfirmation } from './limitModel'
import { useWindowScheme } from './scheme'

const closedStyle = 'aq-btn line disabled:opacity-40'

export function TerminalLimitPanel({ pending, className = '' }: { pending: PendingTerminal; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const qc = useQueryClient()
  const [value, setValue] = useState(pending.limit)
  const [selection, setSelection] = useState<ReadonlySet<string>>(() => new Set())
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const snapshot = useQuery({
    queryKey: ['terminal', 'limit'],
    queryFn: ({ signal }) => getJson<TerminalLimitSnapshot>('/api/terminal/limit', signal),
    refetchInterval: busy ? false : 4000,
    gcTime: 0,
    retry: false,
  })
  const data = snapshot.data ?? pending
  const selected = data.sessions.filter(({ id }) => selection.has(id))
  const project = pending.requested.project
  const name = pending.requested.label && pending.requested.label !== project
    ? pending.requested.label : limitAgents[pending.requested.agent_kind ?? 'shell']
  const described = project ? t('Waiting to open {name} in {project}.', { name, project }) : t('Waiting to open {name}.', { name })
  const close = () => { if (!busy) pending.cancel() }
  useModalA11y(ref, close)

  async function retry() {
    await pending.retry()
    void qc.invalidateQueries({ queryKey: ['terminal'] })
  }

  async function apply() {
    setBusy(true)
    setErrors([])
    setConfirm(false)
    try {
      await saveSettings({ 'terminal.max_sessions': value })
      void qc.invalidateQueries({ queryKey: SETTINGS_QUERY_KEY })
      await retry()
    } catch {
      setErrors([t('Could not save the terminal limit.')])
    } finally {
      setBusy(false)
    }
  }

  async function act(action: 'sleep' | 'close') {
    if (action === 'close' && !confirm && selected.some(needsCloseConfirmation)) {
      setConfirm(true)
      return
    }
    setBusy(true)
    setErrors([])
    const failures: string[] = []
    const failedIds = new Set<string>()
    let needsConfirm = false
    try {
      for (const row of selected) {
        try {
          await postJson(`/api/terminal/sessions/${encodeURIComponent(row.id)}/${action}`, action === 'sleep'
            ? { actor: 'operator' }
            : { actor: 'operator', from_limit: true, confirmed: confirm })
        } catch (error) {
          failedIds.add(row.id)
          if (action === 'close' && error instanceof ApiError && error.status === 409) needsConfirm = true
          failures.push(t('{name}: {error}', { name: row.label, error: error instanceof Error ? error.message : String(error) }))
        }
      }
      setSelection(failedIds)
      setConfirm(needsConfirm)
      setErrors(failures)
      if (failedIds.size < selected.length) {
        await retry()
        if (!terminalLimitPending()) {
          for (const failure of failures) toast.error(failure)
        }
      } else {
        void snapshot.refetch()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div ref={ref} role="dialog" aria-modal="true" aria-label={t('Terminal limit')} data-nodrag
      className={`flex min-h-0 flex-col bg-base text-12 ${className}`}
      onKeyDown={(e) => e.stopPropagation()} onKeyUp={(e) => e.stopPropagation()}>
      <header className="flex shrink-0 items-center justify-between gap-4 border-y border-border-subtle bg-surface px-10 py-4">
        <h1 className="text-13 font-medium">
          {data.limit ? t('{count} of {limit} open', { count: data.count, limit: data.limit }) : t('{count} open · unlimited', { count: data.count })}
        </h1>
        <button type="button" autoFocus className="aq-btn icon disabled:opacity-40" aria-label={t('Dismiss')} disabled={busy} onClick={close}><X size={14} /></button>
      </header>
      <div className="aq-scroll flex min-h-0 flex-1 flex-col gap-8 overflow-auto p-10">
        <p className="m-0 shrink-0 aq-ink2">{described} {t('It opens automatically when a slot is available.')}</p>
        <LimitMemory value={value} limit={data.limit} maximum={data.maximum} setValue={setValue}
          memory={snapshot.data?.memory} busy={busy} apply={() => void apply()} />
        {confirm && <p role="status" className="m-0 shrink-0 text-[var(--status-amber)]">
          {t('Selected terminals have an attached view or running program. Closing them will stop their programs.')}
        </p>}
        {errors.length > 0 && <ul role="alert" className="m-0 shrink-0 list-none p-0 text-status-red">
          {errors.map((error, n) => <li key={n}>{error}</li>)}
        </ul>}
        <LimitTerminalList rows={data.sessions} selected={selection} busy={busy}
          setSelected={(ids) => { setSelection(ids); setConfirm(false) }}
          actions={<>
            <span className="font-mono text-11 aq-ink3">{t('{n} selected', { n: selected.length })}</span>
            <button type="button" className="aq-btn solid disabled:opacity-40" disabled={busy || !selected.length} onClick={() => void act('sleep')}>
              <Moon size={12} />{t('Sleep')}
            </button>
            <button type="button" className={closedStyle} disabled={busy || !selected.length} onClick={() => void act('close')}>
              {confirm ? t('Confirm close') : t('Close')}
            </button>
          </>} />
        <p className="m-0 shrink-0 text-11 aq-ink3">{t('Last opened is the last connection. Last action is the last input or output.')}</p>
      </div>
    </div>
  )
}

/** Dashboard entry points use the same Aqua panel when there is no Aqua window. */
export function TerminalLimitOverlay() {
  const pending = useTerminalLimit()
  const scheme = useWindowScheme()
  const location = useLocation()
  if (!pending || location.pathname === '/term') return null
  return (
    <div className="aq fixed inset-0 z-modal grid place-items-center p-10" data-v="j"
      data-scheme={scheme.id} data-scheme-scope={scheme.scope}
      style={{ ...scheme.style, background: 'color-mix(in srgb, var(--aq-panel) 72%, transparent)' }}>
      <TerminalLimitPanel pending={pending} className="h-[90vh] w-full max-w-[1100px] overflow-hidden rounded-[12px] border border-border-subtle shadow-xl" />
    </div>
  )
}
