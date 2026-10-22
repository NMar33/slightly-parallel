import { usePopover } from '../../hooks/usePopover'
import { useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { Settings2 } from 'lucide-react'
import { toast } from 'sonner'

import { Card } from '../../components/primitives'
import { Segmented } from '../../components/Segmented'
import { getJson } from '../../lib/getJson'
import { fetchTask } from '../tasks/data'
import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import type { Payload } from './taskLaneModel'
import { readJsonPref, useKeyedPref } from '../../lib/uiPrefs'
import { Chronicle, River, ms, type TTask } from './taskViz'
import { TaskTablePage } from '../tasktable/TaskTable'
import { ProjectAnalytics } from '../analytics/PipelineNext'
import { Days } from './taskVizProduct'
import { TaskAddModal } from './kanban/TaskWindow'
import { LABEL } from '../promptlib/taskstyle'
import { t } from '../../i18n/scope/project'

/**
 * OverviewAnalytics — the task visualisations that graduated from the
 * variants gallery (River, Ledger, Chronicle), mounted on the project
 * Overview behind a gear: each panel can be switched off, because three
 * charts is insight for one operator and noise for another. Choices are
 * remembered per project.
 */

const PANELS = [
  ['river', t('Status flow'), t('Tasks per status, per day')],
  ['days', t('Days'), t('A week of task changes, day by day')],
  ['ledger', t('Table'), t('Every task as a row. Pick columns, filter, click a row to open it.')],
  ['analytics', t('Analytics'), t('Query the project in one line, e.g. messages | last 30d | by day | count')],
  ['chronicle', t('Log'), t('Board changes as text, newest day first')],
] as const
type PanelKey = typeof PANELS[number][0]

const KEY = (p: string) => `sp-overview-analytics:${p}`
const DEFAULTS: Record<PanelKey, boolean> = { river: true, days: true, ledger: true, analytics: true, chronicle: false }

function readPanels(key: string): Record<PanelKey, boolean> {
  const raw = readJsonPref<Record<string, unknown> | null>(key, null) ?? {}
  const out = { ...DEFAULTS }
  for (const [k] of PANELS) if (typeof raw[k] === 'boolean') out[k] = raw[k] as boolean
  return out
}

export function OverviewAnalytics({ projectCode }: { projectCode: string }) {
  // Read again for the next project: the page is reused across projects.
  const [panels, setPanels] = useKeyedPref(KEY(projectCode), readPanels)
  const [win, setWin] = useState<'week' | 'month' | 'all'>('week')
  // Opening a task from a panel: fetch the whole row first, so saving the
  // editor cannot blank a field the visualisation never carried.
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null)
  const openTask = (id: string) => {
    void fetchTask(id)
      .then((row) => { if (row) setEditing(row as Record<string, unknown>) })
      .catch((e: unknown) => toast.error(t('The task could not be opened: {reason}', { reason: (e as Error).message })))
  }
  const anyOn = PANELS.some(([k]) => panels[k])

  const setPanel = (k: PanelKey, v: boolean) => {
    setPanels({ ...panels, [k]: v })
  }

  // The window's tasks with something on them; the last window's stay up
  // while another one loads.
  const qc = useQueryClient()
  const read = useQuery({
    queryKey: ['tasks', 'timeline', projectCode, win, 0],
    queryFn: ({ signal }) => getJson<Payload>(`/api/tasks/timeline?project=${encodeURIComponent(projectCode)}&window=${win}&limit=0`, signal),
    select: (d): { since: number; tasks: TTask[] } => ({
      since: ms(String(d.since)),
      tasks: (Array.isArray(d.tasks) ? d.tasks : []).filter((t) => t.events?.length),
    }),
    enabled: anyOn,
    placeholderData: keepPreviousData,
  })
  const data = read.data ?? null
  const reread = () => void qc.invalidateQueries({ queryKey: ['tasks', 'timeline', projectCode] })

  const now = Date.now()
  return (
    <section aria-labelledby="overview-analytics">
      <div className="flex items-center gap-8 mb-16 flex-wrap">
        <h2 id="overview-analytics" className="text-20 font-semibold text-primary" style={{ letterSpacing: '-0.022em' }}>
          {t('Task analytics')}
        </h2>
        <PanelsGear panels={panels} onChange={setPanel} />
        {anyOn && (
          <Segmented label={t('Window')} value={win} onChange={setWin} height={20} className="ml-auto"
            options={(['week', 'month', 'all'] as const).map((w) => [w, w] as const)} />
        )}
      </div>
      {!anyOn ? (
        <p className="text-12 text-tertiary -mt-8">
          {t('All panels are off — the gear brings back River, Days, Ledger, Analytics or Chronicle.')}
        </p>
      ) : read.isError && !data ? (
        <ErrorBanner title={t('Could not load the task analytics')} message={(read.error as Error).message} onRetry={() => void read.refetch()} hideDismiss />
      ) : !data ? (
        <LoadingSkeleton variant="row" count={3} />
      ) : data.tasks.length === 0 ? (
        <p className="text-12 text-tertiary -mt-8">{t('No task activity in this window.')}</p>
      ) : (
        <div className="flex flex-col gap-16">
          {panels.river && (
            <Card padding="md">
              <PanelTitle name={PANELS[0][1]} hint={PANELS[0][2]} />
              <River tasks={data.tasks} since={data.since} now={now} />
            </Card>
          )}
          {panels.days && (
            <Card padding="md">
              <PanelTitle name="Days" hint={PANELS[1][2]} />
              <Days tasks={data.tasks} since={data.since} now={now} onOpenTask={openTask} />
            </Card>
          )}
          {panels.ledger && (
            <Card padding="md">
              <PanelTitle name={PANELS[2][1]} hint={PANELS[2][2]} />
              {/* The task table (Lab: task-table-builder), chosen 2026-09-27; it keeps
                  its own period in the query, not the panel's window. */}
              <TaskTablePage projectCode={projectCode} />
            </Card>
          )}
          {panels.analytics && (
            <Card padding="md">
              <PanelTitle name="Analytics" hint={PANELS[3][2]} />
              {/* The analytics pipeline (Lab: analytics-pipeline-mixed), chosen 2026-09-27, on this project's rows. */}
              <ProjectAnalytics project={projectCode} />
            </Card>
          )}
          {panels.chronicle && (
            <Card padding="md">
              <PanelTitle name={PANELS[4][1]} hint={PANELS[4][2]} />
              <Chronicle tasks={data.tasks} since={data.since} />
            </Card>
          )}
        </div>
      )}
      {editing && (
        <TaskAddModal
          projectCode={projectCode}
          initialStatus={String(editing.status ?? 'unclassified')}
          existingTask={editing as never}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reread() }}
        />
      )}
    </section>
  )
}

function PanelTitle({ name, hint }: { name: string; hint: string }) {
  return (
    <div className="flex items-baseline gap-8 mb-8">
      <span className={`${LABEL} font-semibold`}>{name}</span>
      <span className="text-11 text-tertiary/80 truncate">{hint}</span>
    </div>
  )
}

/** The gear: a small popup of on/off switches, one per panel. */
function PanelsGear({
  panels, onChange,
}: {
  panels: Record<PanelKey, boolean>
  onChange: (k: PanelKey, v: boolean) => void
}) {
  const { open, setOpen, rootRef } = usePopover()
  return (
    <span ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        aria-label={t('Choose analytics panels')}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        title={t('Show or hide panels for this project')}
        className={`h-20 w-20 inline-flex items-center justify-center rounded-pill transition-colors ${
          open ? 'text-brand bg-brand/12' : 'text-tertiary hover:text-primary hover:bg-hover'
        }`}
      >
        <Settings2 size={13} aria-hidden />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={t('Analytics panels')}
          className="absolute left-0 top-[calc(100%+6px)] z-dropdown w-[360px] max-w-[90vw] rounded-card border border-border-default bg-surface shadow-lg p-12 flex flex-col gap-8"
        >
          <p className="text-11 text-tertiary leading-relaxed">
            {t('Tick a panel to show it under Task analytics and untick it to hide it. The choice applies to this project only and is remembered for next time.')}
          </p>
          {PANELS.map(([k, name, hint]) => (
            <label key={k} className="flex items-start gap-8 cursor-pointer rounded-input px-6 py-4 hover:bg-hover">
              <input
                type="checkbox"
                checked={panels[k]}
                onChange={(e) => onChange(k, e.currentTarget.checked)}
                className="mt-2 accent-[var(--brand)]"
              />
              <span className="text-12 leading-relaxed">
                <span className="text-primary font-medium">{name}</span>{' '}
                <span className="text-tertiary">— {hint}</span>
              </span>
            </label>
          ))}
          <p className="text-10 font-mono text-tertiary">
            {t('more shapes live under Variants → task timeline')}
          </p>
        </div>
      )}
    </span>
  )
}
