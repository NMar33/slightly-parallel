import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'

import { PageHeader } from '../components/PageHeader'
import { AGENTS_GUIDE } from '../features/visions/guides'
import { PageGuide } from '../features/visions/parts'
import { LoadingSkeleton } from '../components/states'
import { AgentCard } from '../features/agents/AgentCard'
import { FleetStrip, projectRange, useDrawer } from '../features/agents/parts'
import { fetchProfiles, fmtMinutes, profileHeadline, profileLabel, type AgentProfile } from '../features/agents/profile'
import { api, qk } from '../lib/api'
import { projectColor } from '../utils/projectColor'
import { useHashState } from '../hooks/useHashState'
import { GROUP_COLOR } from '../lib/groups'
import { useMarks } from '../lib/marks'
import { t, tn } from '../i18n/scope/pages'

/**
 * /agent — every agent in the fleet, on one page.
 *
 * Each project's roster (the same cards as its Agents tab), stacked
 * project by project, most recently active first, with the fleet totals
 * on top and one search box over names, ids and headlines. A click on a
 * card opens the agent's own page.
 */
/** Each roster's profiles; recombined only when one of the reads changes. */
const rosterData = (results: Array<{ data?: AgentProfile[]; isLoading: boolean }>) => ({
  data: results.map((r) => r.data ?? []),
  loading: results.some((r) => r.isLoading && !r.data),
})

export default function AgentsIndexPage() {
  useEffect(() => { document.title = `${t('Agents')} — Slightly Parallel` }, [])
  const navigate = useNavigate()
  const { open: openDrawer, drawer } = useDrawer()
  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal) })
  const codes = useMemo(() => (snapshot.data?.projects ?? []).map((p) => p.code), [snapshot.data])
  const { data: rosters, loading: rostersLoading } = useQueries({
    queries: codes.map((code) => ({
      queryKey: ['agents', 'profiles', code],
      queryFn: ({ signal }: { signal: AbortSignal }) => fetchProfiles(code, signal),
      staleTime: 15_000,
    })),
    combine: rosterData,
  })
  // The find belongs in the URL like every other list search on the product.
  const [hash, setHash] = useHashState()
  const q = hash.q ?? ''
  const setQ = (v: string) => setHash({ q: v })
  const needle = q.trim().toLowerCase()
  const star = useMarks()
  // A group picked stands for its members; it lives in the URL too.
  const group = hash.group ?? ''
  const starred = star.has

  const sections = useMemo(() => {
    const match = (p: AgentProfile) =>
      (!group || p.agent.agent_group === group) &&
      (!needle || `${profileLabel(p)} ${p.agent.agent_id} ${profileHeadline(p)} ${p.agent.agent_group ?? ''}`.toLowerCase().includes(needle))
    return codes.map((code, i) => {
      const all = rosters[i] ?? []
      // Important agents first, then the most recently active.
      const members = all.filter(match).sort((a, b) =>
        Number(starred('agent', b.agent.agent_id)) - Number(starred('agent', a.agent.agent_id))
        || (b.agent.last_active || '').localeCompare(a.agent.last_active || ''))
      return { code, all, members, range: projectRange(all), peak: Math.max(1, ...all.flatMap((p) => p.by_day.map((d) => d.turns))) }
    }).sort((a, b) => (b.members[0]?.agent.last_active || '').localeCompare(a.members[0]?.agent.last_active || ''))
  }, [codes, rosters, needle, group, starred])
  const everyone = useMemo(() => sections.flatMap((s) => s.all), [sections])
  const groups = useMemo(() => {
    const n = new Map<string, number>()
    for (const p of everyone) if (p.agent.agent_group) n.set(p.agent.agent_group, (n.get(p.agent.agent_group) ?? 0) + 1)
    return [...n.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [everyone])
  const loading = (snapshot.isLoading && !snapshot.data) || rostersLoading

  return (
    <div className="flex flex-col gap-16 min-w-0">
      <PageHeader
        variant="tool"
        title={t('Agents')}
        sub={everyone.length ? `${tn(everyone.length, '{n} agent', '{n} agents')} · ${tn(codes.length, '{n} project', '{n} projects')} · ${fmtMinutes(everyone.reduce((n, p) => n + p.totals.minutes, 0))}` : undefined}
        actions={
          <input
            value={q}
            onChange={(e) => setQ(e.currentTarget.value)}
            placeholder={t('Find an agent')}
            aria-label={t('Find an agent')}
            className="w-[220px] rounded-input border border-border-subtle bg-surface px-8 py-4 text-12 text-primary placeholder:text-tertiary focus:outline-none focus:border-brand"
          />
        }
      />
      <PageGuide id="agents" guide={AGENTS_GUIDE} examples={0} />
      {loading && <LoadingSkeleton variant="card" count={3} label={t('Loading agents')} />}
      {!loading && everyone.length > 0 && <FleetStrip profiles={everyone} />}
      {!loading && groups.length > 0 && (
        <div className="flex items-center gap-6 flex-wrap" role="group" aria-label={t('Groups')}>
          <span className="text-10 uppercase tracking-wide font-mono text-tertiary">{t('groups')}</span>
          {groups.map(([name, n]) => {
            const on = group === name
            return (
              <button key={name} type="button" aria-pressed={on} onClick={() => setHash({ group: on ? '' : name })}
                className="h-20 px-8 rounded-pill border text-11 font-mono inline-flex items-center gap-4"
                style={{ borderColor: GROUP_COLOR, color: on ? 'var(--bg-surface)' : GROUP_COLOR, backgroundColor: on ? GROUP_COLOR : 'transparent' }}
                title={on ? t('Show every agent') : t('Show the agents in {name}: {n}', { name, n })}>
                {name} <span className="opacity-70">{n}</span>
              </button>
            )
          })}
        </div>
      )}
      {!loading && everyone.length === 0 && (
        <div className="text-12 text-tertiary italic">{t('No agents yet. Start an agent in a connected project.')}</div>
      )}
      {sections.filter((s) => s.members.length > 0).map((s) => (
        <section key={s.code} className="flex flex-col gap-8 min-w-0">
          <h2 className="text-12 font-mono text-secondary flex items-center gap-8">
            <span aria-hidden className="inline-block w-8 h-8 rounded-pill" style={{ backgroundColor: projectColor(s.code) }} />
            <span className="text-primary">{s.code}</span>
            <span className="text-tertiary">{s.members.length !== s.all.length ? t('{n} of {all} agents', { n: s.members.length, all: s.all.length }) : tn(s.members.length, '{n} agent', '{n} agents')}</span>
            <span className="flex-1 border-t border-border-subtle" />
          </h2>
          <div className="grid gap-12" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))' }}>
            {s.members.map((p) => (
              <AgentCard
                key={p.agent.agent_id}
                p={p}
                code={s.code}
                range={s.range}
                peak={s.peak}
                onOpenLens={openDrawer}
                onOpenTask={(tid) => navigate(`/project/${encodeURIComponent(s.code)}#tasks&task=${encodeURIComponent(tid)}`)}
                onToggle={() => navigate(`/agent/${encodeURIComponent(p.agent.agent_id)}`)}
              />
            ))}
          </div>
        </section>
      ))}
      {!loading && needle && sections.every((s) => s.members.length === 0) && everyone.length > 0 && (
        <div className="text-12 text-tertiary italic">{t('no agent matches “{q}”', { q })}</div>
      )}
      {drawer}
    </div>
  )
}
