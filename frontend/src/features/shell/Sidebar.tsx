import { getJson } from '../../lib/getJson'
import { Live } from '../../lib/clock'
import { Link, NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { BrandMark, BrandWordmark } from '../../components/Brand'
import { AgentTree } from '../../components/AgentTree'
import {
  formatClock,
  liveElapsed,
  type TimeEntry,
} from '../project/timeEntry'
import { api, qk } from '../../lib/api'
import { useStrSetting } from '../../lib/settings'
import { SIDEBAR_KEY } from '../../hooks/useSidebarCollapsed'
import { SidebarNav } from '../sidebar/SidebarNav'
import { ExampleBadge, SidebarExampleBar, SidebarExampleNote, useExample } from '../example/example'
import { t, tn } from '../../i18n/scope/shell'
import { ProjectDot } from '../../components/ProjectDot'

/* ---------------------------------------------------------------------------
 * Sidebar
 * ------------------------------------------------------------------------- */

/* The pages themselves live in features/sidebar/catalog.ts; which of them
   show, grouped how, is the operator's layout (features/sidebar/layout.ts). */

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { data: snapshot } = useQuery({
    queryKey: qk.snapshot(),
    queryFn: ({ signal }) => api.snapshot(signal),
    // Sidebar is always mounted; the shared polling default keeps it live.
  })
  const { data: example } = useExample()

  return (
    <aside
      className={`${collapsed ? 'w-sidebar-collapsed' : 'w-sidebar'} shrink-0 border-r border-border-subtle bg-surface flex flex-col overflow-hidden transition-[width] duration-fast ease-out`}
      aria-label={t('Primary navigation')}
      data-collapsed={collapsed || undefined}
    >
      {/* Brand. Collapsed, the mark is the way back: hovering it shows the
          open-panel icon, so the rail explains itself without a label. */}
      {collapsed ? (
        <div className="h-topbar min-h-topbar flex items-center justify-center border-b border-border-subtle">
          <button
            type="button"
            onClick={onToggle}
            title={t('Expand sidebar ({key})', { key: SIDEBAR_KEY })}
            aria-label={t('Expand sidebar')}
            aria-expanded={false}
            className="group relative inline-flex items-center justify-center w-32 h-32 rounded-input hover:bg-hover text-secondary hover:text-primary"
          >
            <span className="group-hover:opacity-0 transition-opacity duration-fast"><BrandMark size={22} /></span>
            <PanelLeftOpen size={16} aria-hidden className="absolute opacity-0 group-hover:opacity-100 transition-opacity duration-fast" />
          </button>
        </div>
      ) : (
        <div className="h-topbar min-h-topbar flex items-center gap-8 pl-12 pr-8 border-b border-border-subtle">
          <Link to="/about" className="flex items-center gap-8 rounded-input" title={t('About Slightly Parallel')}>
            <BrandMark size={28} />
            <BrandWordmark height={19} />
          </Link>
          <span className="ml-auto" />
          <button
            type="button"
            onClick={onToggle}
            title={t('Collapse sidebar ({key})', { key: SIDEBAR_KEY })}
            aria-label={t('Collapse sidebar')}
            aria-expanded
            className="inline-flex items-center justify-center w-24 h-24 rounded-input text-tertiary hover:text-primary hover:bg-hover"
          >
            <PanelLeftClose size={16} aria-hidden />
          </button>
        </div>
      )}

      {/* One scroller for the whole sidebar. The views and the projects used
          to own a scrollbar each, which put two of them side by side in a
          column 220px wide and made "scroll down to the projects" mean
          scrolling the wrong one first. */}
      <div className="flex-1 min-h-0 overflow-y-auto">
      {/* Views */}
      <SidebarNav collapsed={collapsed} />

      {/* Projects, as their dots: the colour is the identity the whole
          dashboard already uses, so a dot is enough to find one. */}
      {collapsed && (
        <div className="p-8 flex flex-col gap-4 border-t border-border-subtle items-center" aria-label={t('Projects')}>
          {(snapshot?.projects ?? []).map((p) => {
            return (
              <NavLink
                key={p.code}
                to={`/project/${encodeURIComponent(p.code)}`}
                title={p.open_tasks > 0 ? `${p.code} · ${tn(p.open_tasks, '{n} open', '{n} open')}` : p.code}
                aria-label={p.code}
                className={({ isActive }) =>
                  `inline-flex items-center justify-center w-32 h-32 rounded-input transition-colors duration-fast ease-out ${isActive ? 'bg-hover' : 'hover:bg-hover'}`
                }
              >
                <ProjectDot code={p.code} size={10} glow />
              </NavLink>
            )
          })}
        </div>
      )}

      {/* Projects + agents tree */}
      {!collapsed && <div className="p-8 flex flex-col gap-4 border-t border-border-subtle">
        <SectionLabel>
          <span>{t('Projects')}</span>
          {snapshot?.projects?.length ? (
            <span className="text-11 tabular text-tertiary font-mono normal-case tracking-normal">
              {snapshot.projects.length}
            </span>
          ) : null}
        </SectionLabel>
        {snapshot?.projects?.length ? (
          <div className="flex flex-col gap-8">
            {snapshot.projects.map((p) => {
              const isExample = !!example?.present && example.project === p.code
              return (
                <div key={p.code} className="flex flex-col gap-4">
                  {isExample && <SidebarExampleBar />}
                  <NavLink
                    to={`/project/${encodeURIComponent(p.code)}`}
                    className={({ isActive }) =>
                      `block px-8 py-8 rounded-input transition-colors duration-fast ease-out
                       ${isActive ? 'bg-hover' : 'hover:bg-hover'}`
                    }
                  >
                    <div className="flex items-center gap-8 min-w-0">
                      <ProjectDot code={p.code} glow />
                      <span className="truncate text-13 text-primary font-mono">
                        {p.code}
                      </span>
                      {isExample && <ExampleBadge />}
                      {p.open_tasks > 0 && (
                        <span
                          className="ml-auto text-11 tabular text-tertiary font-mono"
                          aria-label={tn(p.open_tasks, '{n} open task', '{n} open tasks')}
                        >
                          {p.open_tasks}
                        </span>
                      )}
                    </div>
                    {p.l1_headline && (
                      <div
                        className="text-11 text-tertiary mt-4 pl-16 leading-snug"
                        style={{
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                        title={p.l1_headline}
                      >
                        {p.l1_headline}
                      </div>
                    )}
                  </NavLink>
                  {snapshot.agents?.some((a) => a.project === p.code) && (
                    <div className="pl-12">
                      <AgentTree
                        agents={snapshot.agents}
                        activity={snapshot.recent_activity ?? []}
                        project={p.code}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ) : example?.building ? null : (
          <div className="px-8 py-12 text-12 text-tertiary">{t('No projects yet. Add one on the Setup page.')}</div>
        )}
        {example && <SidebarExampleNote state={example} />}

        {snapshot?.agents?.length ? (
          <div className="mt-16">
            <SectionLabel>
              <span>{t('Agents')}</span>
              <span className="text-11 tabular text-tertiary font-mono normal-case tracking-normal">
                {snapshot.agents.length}
              </span>
            </SectionLabel>
            <div className="px-8 text-11 font-mono text-tertiary">
              {t('{nested} nested · {root} root', {
                nested: snapshot.agents.filter((a) => a.parent_agent_id).length,
                root: snapshot.agents.filter((a) => !a.parent_agent_id).length,
              })}
            </div>
          </div>
        ) : null}
      </div>}
      </div>

      <RunningTimerChip collapsed={collapsed} />
      <SidebarFooter live={(snapshot?.recent_activity?.length ?? 0) > 0} collapsed={collapsed} />
    </aside>
  )
}

/**
 * RunningTimerChip — a manual timer you cannot see is a timer you forget.
 * Any open entry, on any project, surfaces here with a live clock and a
 * link straight to its Timer tab.
 */
function RunningTimerChip({ collapsed }: { collapsed: boolean }) {
  const { data } = useQuery({
    queryKey: ['time-running'],
    queryFn: async ({ signal }) => {
      return getJson<{ running: TimeEntry[] }>('/api/time/running', signal)
    },
  })
  const running = data?.running ?? []
  if (running.length === 0) return null

  return (
    <div className={`${collapsed ? 'px-8 items-center' : 'px-16'} py-6 border-t border-border-subtle flex flex-col gap-2`}>
      {running.map((entry) => (
        // One clock for the whole app (lib/clock): only this link redraws each second.
        <Live key={entry.id} on={!entry.paused_at}>{(nowMs) => (
        <NavLink
          to={`/project/${encodeURIComponent(entry.project)}#tools`}
          className={`flex items-center ${collapsed ? 'justify-center w-32 h-24' : 'gap-6'} text-11 font-mono no-underline group`}
          title={collapsed
            ? `${formatClock(liveElapsed(entry, nowMs))} · ${entry.project}${entry.note ? ` · ${entry.note}` : ''}`
            : entry.note || t('Running timer')}
          aria-label={collapsed ? t('Timer {project}', { project: entry.project }) : undefined}
        >
          <span
            aria-hidden
            className={`inline-block w-6 h-6 rounded-pill ${entry.paused_at ? '' : 'animate-pulse'}`}
            style={{
              backgroundColor: entry.paused_at
                ? 'var(--status-amber)'
                : 'var(--brand)',
            }}
          />
          {!collapsed && (
            <>
              <span className="text-primary tabular">
                {formatClock(liveElapsed(entry, nowMs))}
              </span>
              <span className="text-tertiary truncate group-hover:text-secondary">
                {entry.project}{entry.source === 'auto' && <span className="text-brand"> · {t('auto')}</span>}
              </span>
            </>
          )}
        </NavLink>
        )}</Live>
      ))}
    </div>
  )
}

function SidebarFooter({ live, collapsed }: { live: boolean; collapsed: boolean }) {
  const clock = useStrSetting('ui.clock', 'utc')
  return <Live on={clock !== 'hidden'}>{(ms) => <SidebarFooterAt live={live} collapsed={collapsed} clock={clock} now={new Date(ms)} />}</Live>
}

function SidebarFooterAt({ live, collapsed, clock, now }: { live: boolean; collapsed: boolean; clock: string; now: Date }) {
  const useUtc = clock === 'utc'
  const hh = String(useUtc ? now.getUTCHours() : now.getHours()).padStart(2, '0')
  const mm = String(useUtc ? now.getUTCMinutes() : now.getMinutes()).padStart(2, '0')
  const ss = String(useUtc ? now.getUTCSeconds() : now.getSeconds()).padStart(2, '0')
  const time = `${hh}:${mm}:${ss}${useUtc ? ' UTC' : ''}`
  const dot = (
    <span
      aria-hidden
      className={`inline-block w-8 h-8 rounded-pill ${live ? 'animate-pulse' : ''}`}
      style={{
        backgroundColor: live ? 'var(--status-green)' : 'var(--status-neutral)',
        boxShadow: live ? '0 0 6px var(--status-green)' : 'none',
      }}
    />
  )
  if (collapsed) {
    return (
      <div
        className="h-32 border-t border-border-subtle flex items-center justify-center"
        title={clock === 'hidden' ? (live ? t('LIVE') : t('IDLE')) : `${live ? t('LIVE') : t('IDLE')} · ${time}`}
        aria-label={live ? t('Live') : t('Idle')}
      >
        {dot}
      </div>
    )
  }
  return (
    <div className="px-16 py-8 border-t border-border-subtle flex items-center justify-between text-11 text-tertiary font-mono tabular">
      <span className="inline-flex items-center gap-4">
        {dot}
        {live ? t('LIVE') : t('IDLE')}
      </span>
      {clock !== 'hidden' && (
        <span title={useUtc ? t('UTC clock') : t('Local clock')}>{time}</span>
      )}
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-8 pt-8 pb-4 text-11 uppercase tracking-wider text-tertiary font-medium flex items-center justify-between">
      {children}
    </div>
  )
}
