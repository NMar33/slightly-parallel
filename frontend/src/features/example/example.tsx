/*
 * The example project (backend/example.py): shopfront, a month of work
 * played at install with the dates ending yesterday. The sidebar marks it
 * and offers to hide it; its entries say which chat message they were
 * written after, so a new user sees what to type to get the same.
 * Settings › Example project switches it back on.
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { getJson, postJson } from '../../lib/getJson'
import { t } from '../../i18n/scope/shell'

export interface ExampleState {
  project: string
  enabled: boolean
  present: boolean
  building: boolean
  error: string
}

export interface ExampleSourceRow {
  agent_id: string
  project: string
  session_id: string
  turn: number
  command: string
  excerpt: string
}

export const EXAMPLE_KEY = ['example'] as const

/**
 * The quick tour's first step (tour/script.ts PRESETS[0], whose first beat is
 * the Overview at /). Spelled out here so the sidebar does not load the tour.
 */
export const QUICK_TOUR = '/?tour=quick&step=0'

export function useExample(enabled = true) {
  return useQuery({
    queryKey: EXAMPLE_KEY,
    enabled,
    queryFn: ({ signal }) => getJson<ExampleState>('/api/example', signal),
    // While the month is played the sidebar says so, and shows the project
    // the moment it is there.
    // Switched from Settings, it starts building without the sidebar asking.
    refetchInterval: (q) => (q.state.data?.building ? 3000 : 15_000),
  })
}

/** True when `project` is the example project and it is there. */
export function useIsExample(project: string | undefined): boolean {
  const { data } = useExample()
  return !!project && !!data?.present && data.project === project
}

export function useSetExample() {
  const qc = useQueryClient()
  return async (enabled: boolean) => {
    await postJson('/api/settings', { values: { 'example.enabled': enabled } })
    await qc.invalidateQueries()
  }
}

/** The small mark beside the project's name. */
export function ExampleBadge() {
  return (
    <span className="shrink-0 rounded-pill border border-border-subtle px-6 text-10 font-mono uppercase tracking-wide text-tertiary">
      {t('example')}
    </span>
  )
}

/**
 * Above the example project in the sidebar: what it is, and Hide. Hiding
 * removes the project and everything that names it; Settings brings it back.
 */
export function SidebarExampleBar() {
  const setExample = useSetExample()
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)

  const hide = async () => {
    setBusy(true)
    try {
      await setExample(false)
      toast.success(t('Example project hidden. Settings › Example project brings it back.'))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setAsking(false)
    }
  }

  return (
    <div className="flex flex-col gap-2 px-8">
      <div className="flex items-center gap-6 text-10 font-mono uppercase tracking-wide text-tertiary">
        <span>{t('Example project')}</span>
        <span className="ml-auto" />
        {asking ? (
          <>
            <button type="button" disabled={busy} onClick={() => void hide()}
              className="normal-case tracking-normal text-11 text-status-red hover:underline disabled:opacity-50">
              {busy ? t('Hiding…') : t('Hide it')}
            </button>
            <button type="button" disabled={busy} onClick={() => setAsking(false)}
              className="normal-case tracking-normal text-11 hover:text-primary">
              {t('Keep')}
            </button>
          </>
        ) : (
          <button type="button" onClick={() => setAsking(true)}
            title={t('Remove the example project and everything that names it. Settings › Example project brings it back.')}
            className="normal-case tracking-normal text-11 hover:text-primary">
            {t('Hide')}
          </button>
        )}
      </div>
      {/* The quick tour walks this project; its first step is the Overview. */}
      <Link to={QUICK_TOUR} className="self-start text-11 text-brand hover:underline">
        {t('Take the tour')} →
      </Link>
    </div>
  )
}

/** While the month is played, or when it could not be. */
export function SidebarExampleNote({ state }: { state: ExampleState }) {
  if (state.building) {
    return (
      <div className="px-8 py-8 text-12 text-tertiary" role="status">
        {t('Preparing the example project: a month of work on a small online store. About a minute.')}
      </div>
    )
  }
  if (state.enabled && !state.present && state.error) {
    return (
      <div className="px-8 py-8 text-12 text-status-amber">
        {t('The example project could not be made.')}{' '}
        <Link to="/settings" className="underline">{t('Settings')}</Link>
      </div>
    )
  }
  return null
}

/**
 * On an entry of the example project: the chat message it was written
 * after, and the command in it. Nothing on the user's own projects.
 */
export function ExampleSource({ kind, project, agentId, date, time }: {
  kind: 'scan' | 'decision' | 'standup' | 'task'; project: string; agentId: string; date: string; time?: string
}) {
  const isExample = useIsExample(project)
  const { data } = useQuery({
    queryKey: ['example-source', kind, agentId, date, time ?? ''],
    queryFn: ({ signal }) => getJson<{ source: ExampleSourceRow | null }>(
      `/api/example/source?agent_id=${encodeURIComponent(agentId)}&date=${encodeURIComponent(date)}&time=${encodeURIComponent(time ?? '')}&kind=${kind}`, signal),
    enabled: isExample && !!agentId && !!date,
    staleTime: Infinity,
  })
  const s = data?.source
  if (!isExample || !s) return null
  const to = `/chats#project=${encodeURIComponent(s.project || project)}&agent=${encodeURIComponent(s.agent_id)}`
    + `${s.session_id ? `&sel=${encodeURIComponent(s.session_id)}` : ''}&turn=${s.turn}`
  return (
    <Link to={to} data-tour="example-source" className="self-start inline-flex items-baseline gap-6 rounded-input border border-dashed border-border-subtle px-8 py-4 text-12 text-secondary no-underline hover:text-primary hover:border-border">
      <span className="text-10 font-mono uppercase tracking-wide text-tertiary">{t('example')}</span>
      {s.command
        ? <span>{t('Made by {command} in this chat', { command: s.command })}</span>
        : <span>{t('Written in this chat, after “{excerpt}”', { excerpt: s.excerpt.length > 70 ? `${s.excerpt.slice(0, 70)}…` : s.excerpt })}</span>}
      <span aria-hidden>→</span>
    </Link>
  )
}

/**
 * On a page that needs the example project (the tours) while it is off or
 * being played: what it is, and the switch.
 */
export function ExampleOffCard({ why }: { why: string }) {
  const { data } = useExample()
  const setExample = useSetExample()
  const [asked, setAsked] = useState(false)
  if (!data || data.present) return null
  const busy = data.building || asked
  return (
    <section aria-label={t('Example project')} className="flex items-center gap-12 flex-wrap rounded-card border border-border-subtle bg-elevated p-16">
      <p className="text-12 text-secondary max-w-reading">
        {busy
          ? t('Preparing the example project: a month of work on a small online store. About a minute.')
          : `${why} ${t('{project}, a month of work on a small online store, is off in this data folder.', { project: data.project })}`}
      </p>
      {!busy && (
        <button type="button"
          onClick={() => { setAsked(true); setExample(true).catch((e: unknown) => { setAsked(false); toast.error(e instanceof Error ? e.message : String(e)) }) }}
          className="rounded-input border border-brand bg-base px-10 py-3 text-11 text-primary hover:bg-hover">
          {t('Turn on the example project')}
        </button>
      )}
    </section>
  )
}
