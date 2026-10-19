/**
 * C8 — Per-Project Page (shell)
 *
 * Route: /project/:code
 * Fetches: GET /api/project/{code}
 *
 * Composition (per architecture §5, table row C8):
 *   Header (color dot + name + one-line L1 subtitle)
 *   Tab bar (Overview / Agents / Tasks / Sprints / Terminals / Decisions /
 *   Chats / Files / Architecture / Timer)
 *
 * This file is the page shell only: header, data fetch, tab switching, and
 * the Overview tab. Everything heavier lives in src/features/project/:
 *   types.ts        — payload types + normalizer
 *   AgentsTab.tsx   — the cards and the stage
 *   TasksKanban.tsx — kanban board + task modal
 *   SprintsPanel.tsx — the sprint deck
 *   TerminalsTab.tsx — xterm terminals + snippets
 *   FilesTab.tsx    — file × date heatmap
 *
 * Cyrillic-safe throughout: agent_name / task titles / activity descriptions
 * carry Russian text like "рекогниция" and "матолимп" — no character
 * classes narrower than \p{L} anywhere, no toLowerCase without NFC.
 */

import { PanelBoundary } from '../components/ErrorBoundary'
import { Suspense, lazy, useEffect, useMemo } from 'react'
import { useParams } from 'react-router-dom'
import { useWork } from '../lib/timer'
import { useQuery } from '@tanstack/react-query'
import { Row, Chip } from '../components/primitives'
import { StatTile, StatTiles } from '../components/StatTile'
import { projectColor } from '../utils/projectColor'
import { AgentTimelinePanel } from '../features/project/AgentTimelinePanel'
import { TaskTimelinePanel } from '../features/project/TaskTimelinePanel'
import { SprintGanttPanel } from '../features/project/SprintGanttPanel'
import { OverviewAnalytics } from '../features/project/OverviewAnalytics'
import type { Decision as DecisionLogDecision } from '../components/DecisionLog'
import { TabBar } from '../components/TabBar'
import { useTabFromHash } from '../hooks/useTabFromHash'
import { api, qk } from '../lib/api'
import { getJson } from '../lib/getJson'
import { useStrSetting } from '../lib/settings'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../components/states'
import {
  normalizeProjectPayload,
  toAgentMeta,
  type Decision,
  type ProjectPayload,
} from '../features/project/types'
import { t } from '../i18n/scope/pages'

// Every tab but the first is its own chunk, loaded when it is opened: the
// page used to carry all eleven (half the app) to draw the Overview.
const DecisionLog = lazy(() => import('../components/DecisionLog').then((m) => ({ default: m.DecisionLog })))
const SessionsTab = lazy(() => import('../features/project/SessionsTab').then((m) => ({ default: m.SessionsTab })))
const ToolsTab = lazy(() => import('../features/project/ToolsTab').then((m) => ({ default: m.ToolsTab })))
const AgentsTab = lazy(() => import('../features/project/AgentsTab').then((m) => ({ default: m.AgentsTab })))
const TasksKanban = lazy(() => import('../features/project/TasksKanban').then((m) => ({ default: m.TasksKanban })))
const SprintsPanel = lazy(() => import('../features/project/SprintsPanel').then((m) => ({ default: m.SprintsPanel })))
const CalendarTab = lazy(() => import('../features/calendar/CalendarTab').then((m) => ({ default: m.CalendarTab })))
const TerminalsTab = lazy(() => import('../features/project/TerminalsTab').then((m) => ({ default: m.TerminalsTab })))
const FilesTab = lazy(() => import('../features/project/FilesTab').then((m) => ({ default: m.FilesTab })))
const ArchitectureTab = lazy(() => import('../features/project/ArchitectureTab').then((m) => ({ default: m.ArchitectureTab })))

// Re-exports so existing consumers (tests) keep importing from this module.
export type {
  DecisionSource,
  Decision,
  Activity,
  Agent,
  ProjectPayload,
} from '../features/project/types'

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

const TABS = [
  { id: 'overview',  label: t('Overview')   },
  { id: 'agents',    label: t('Agents')     },
  { id: 'tasks',     label: t('Tasks')      },
  { id: 'sprints',   label: t('Sprints')    },
  { id: 'calendar',  label: t('Calendar')   },
  { id: 'terminals', label: t('Terminals')  },
  { id: 'decisions', label: t('Decisions')  },
  { id: 'activity',  label: t('Chats')      },
  { id: 'files',     label: t('Files')      },
  { id: 'architecture', label: t('Architecture') },
  // The id is what links and the saved default tab hold, so it stays.
  { id: 'tools',     label: t('Timer')      },
] as const

type TabId = typeof TABS[number]['id']

const DEFAULT_TAB: TabId = 'overview'

function isTabId(x: string): x is TabId {
  return TABS.some((tab) => tab.id === x)
}

// ---------------------------------------------------------------------------
// Data fetch
// ---------------------------------------------------------------------------

async function fetchProject(code: string, signal?: AbortSignal): Promise<ProjectPayload> {
  const raw = await getJson<unknown>(`/api/project/${encodeURIComponent(code)}`, signal)
  return normalizeProjectPayload(code, raw)
}

// ---------------------------------------------------------------------------
// Adapters — Project payload shapes → shipped component contracts
// ---------------------------------------------------------------------------

/**
 * Adapt payload decisions to the DecisionLog contract. The extended fields
 * (created_time / files_affected_n / alternatives_n) are passed through for
 * DecisionLog versions that render them; the intersection type keeps this
 * compatible whether or not the component's own Decision declares them yet.
 */
type DecisionLogRow = DecisionLogDecision & {
  created_time?: string
  files_affected_n?: number
  alternatives_n?: number
}

function toDecisionLogDecisions(decisions: Decision[]): DecisionLogDecision[] {
  return decisions.map((d): DecisionLogRow => ({
    id: d.id,
    decision_text: d.decision_text,
    rationale: d.rationale ?? '',
    source: d.source,
    agent_id: d.agent_id ?? '',
    related_goal_id: d.related_goal_id,
    tags: d.tags,
    created_date: d.created_date,
    created_time: d.created_time,
    files_affected_n: d.files_affected_n,
    alternatives_n: d.alternatives_n,
  }))
}

// ---------------------------------------------------------------------------
// Overview tab — the numbers, then the timelines
// ---------------------------------------------------------------------------

function OverviewTab({ payload }: { payload: ProjectPayload }) {
  // The agents' working minutes (a session's wall clock also counts waiting on you).
  const totalMin = payload.activity.reduce((s, a) => s + (a.agent_min ?? a.duration_min ?? 0), 0)
  const totalH = Math.round((totalMin / 60) * 10) / 10
  const { open_tasks, tasks_total, tasks_done_7d } = payload.summary

  return (
    <div className="flex flex-col gap-24">
      <StatTiles>
        <StatTile label={t('Agents')} value={payload.agents.length} sub={t('in this project')} />
        <StatTile label={t('Open tasks')} value={open_tasks} sub={t('of {total}', { total: tasks_total })} />
        <StatTile label={t('Done this week')} value={tasks_done_7d} sub={t('tasks closed in 7 days')} />
        <StatTile label={t('Hours logged')} value={totalH} sub={t('from recorded chats')} />
      </StatTiles>
      {/* Each panel fails alone: one bad payload costs one panel, not the tab. */}
      <PanelBoundary name={t('Agent timeline')} resetKey={payload.code}>
        <AgentTimelinePanel agents={toAgentMeta(payload.agents)} projectCode={payload.code} />
      </PanelBoundary>
      <PanelBoundary name={t('Sprints')} resetKey={payload.code}><SprintGanttPanel projectCode={payload.code} /></PanelBoundary>
      <PanelBoundary name={t('Task timeline')} resetKey={payload.code}><TaskTimelinePanel projectCode={payload.code} /></PanelBoundary>
      <PanelBoundary name={t('Task analytics')} resetKey={payload.code}><OverviewAnalytics projectCode={payload.code} /></PanelBoundary>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function ProjectHeader({ payload }: { payload: ProjectPayload }) {
  return (
    <header>
      <Row gap="12" align="center" className="mb-8">
        <span
          aria-hidden
          className="inline-block rounded-pill flex-shrink-0"
          style={{
            width: 12,
            height: 12,
            backgroundColor: projectColor(payload.code),
          }}
        />
        <h1
          className="text-32 font-semibold text-primary leading-none"
          style={{ letterSpacing: '-0.022em' }}
        >
          {payload.name}
        </h1>
        <Chip>{payload.code}</Chip>
      </Row>
      <p className="text-14 text-secondary italic max-w-[900px]">
        {payload.l1_headline}
      </p>
    </header>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export interface ProjectPageProps {
  /** Optional injected fetcher (tests). Defaults to real fetch. */
  fetcher?: (code: string, signal?: AbortSignal) => Promise<ProjectPayload>
  /** Optional injected code (tests / storybook). Defaults to route param. */
  codeOverride?: string
}

export default function ProjectPage({
  fetcher = fetchProject,
  codeOverride,
}: ProjectPageProps = {}) {
  const params = useParams<{ code: string }>()
  const code = codeOverride ?? params.code ?? ''
  // On a project's page you are working on it (the smart timer).
  useWork('route', code ? { project: code } : null)

  // Server capabilities ride on the snapshot (already polled by the sidebar,
  // so this is a cache read). Terminals hide when the server has them off.
  const { data: snapshot } = useQuery({
    queryKey: qk.snapshot(),
    queryFn: ({ signal }) => api.snapshot(signal),
  })
  const terminalEnabled = snapshot?.capabilities?.terminal_enabled ?? true
  const visibleTabs = useMemo(
    () => (terminalEnabled ? TABS : TABS.filter((t) => t.id !== 'terminals')),
    [terminalEnabled],
  )

  const configuredDefault = useStrSetting('ui.default_project_tab', DEFAULT_TAB)
  const defaultTab: TabId =
    isTabId(configuredDefault) &&
    visibleTabs.some((t) => t.id === configuredDefault)
      ? (configuredDefault as TabId)
      : DEFAULT_TAB

  const [rawTab, selectTab] = useTabFromHash<TabId>(isTabId, defaultTab)
  // A hash may still name a hidden tab (e.g. #terminals with terminals off).
  const tab: TabId = visibleTabs.some((t) => t.id === rawTab)
    ? rawTab
    : DEFAULT_TAB

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['project', code],
    queryFn: ({ signal }) => fetcher(code, signal),
    enabled: !!code,
  })

  useEffect(() => { document.title = code ? `${code} — Slightly Parallel` : `${t('Project')} — Slightly Parallel` }, [code])

  if (!code) {
    return (
      <div>
        <EmptyState
          title={t('No project at this address')}
          subtitle={t('Pick one from the Overview.')}
        />
      </div>
    )
  }

  if (isLoading && !data) {
    return (
      <div className="flex flex-col gap-24">
        <LoadingSkeleton variant="text"  count={2} label={t('Loading project header')} />
        <LoadingSkeleton variant="card"  count={1} label={t('Loading standup')} />
        <LoadingSkeleton variant="row"   count={1} label={t('Loading tabs')} />
        <LoadingSkeleton variant="card"  count={2} label={t('Loading project content')} />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div>
        <ErrorBanner
          title={t('Could not load project "{code}".', { code })}
          message={(error as Error | null)?.message ?? t('Unknown error.')}
          onRetry={() => refetch()}
          hideDismiss
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-24">
      <ProjectHeader payload={data} />

      <TabBar tabs={visibleTabs} active={tab} onSelect={selectTab} ariaLabel={t('Project sections')} />

      <div
        role="tabpanel"
        id={`tabpanel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        tabIndex={0}
        className="focus:outline-none"
      >
        <PanelBoundary name={t('The {tab} tab', { tab })} resetKey={`${data.code}:${tab}`}>
        {/* Keyed by the project: /project/A → /project/B keeps this page,
            and a tab kept A's state — a selection, a task armed for a link —
            to act on B's board. */}
        <Suspense key={data.code} fallback={<LoadingSkeleton variant="card" count={3} />}>
        {tab === 'overview'  && <OverviewTab   payload={data} />}
        {tab === 'agents'    && <AgentsTab     agents={data.agents} projectCode={data.code} />}
        {tab === 'decisions' && (
          <DecisionLog
            decisions={toDecisionLogDecisions(data.decisions)}
            emptyHint={t('No decisions match. Agents log decisions as they work.')}
          />
        )}
        {tab === 'tasks'     && <TasksKanban   projectCode={data.code} />}
        {tab === 'sprints'   && <SprintsPanel  projectCode={data.code} />}
        {tab === 'calendar'  && <CalendarTab   projectCode={data.code} />}
        {tab === 'terminals' && <TerminalsTab  projectCode={data.code} />}
        {tab === 'activity'  && <SessionsTab   projectCode={data.code} />}
        {tab === 'tools'     && <ToolsTab      projectCode={data.code} />}
        {tab === 'files'     && <FilesTab      projectCode={data.code} />}
        {tab === 'architecture' && <ArchitectureTab projectCode={data.code} />}
        </Suspense>
        </PanelBoundary>
      </div>
    </div>
  )
}
