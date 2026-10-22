import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { Info } from 'lucide-react'
import { readJsonPref, useKeyedPref } from '../../lib/uiPrefs'

import { Card } from '../../components/primitives'
import { Segmented } from '../../components/Segmented'
import { getJson } from '../../lib/getJson'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { useMentionChat } from './mentions'
import { WINDOWS, fmt, parseIso, type Payload, type TimelineTask, type Window } from './taskLaneModel'
import { LANE_COLS, Lane, LaneLegend } from './taskLanes'
import { TaskAddModal } from './kanban/TaskWindow'
import { t } from '../../i18n/scope/project'

/**
 * TaskTimelinePanel — each task as a lane over time.
 *
 * What a lane shows (./taskLanes): the window cut into cells, each the
 * status the task ended it in (from the task's event log), a ring where
 * the status changed, a dot where it was handed to an agent (a captured
 * user turn naming the task id) or named in a reply. Hover for the
 * detail; click a title to open the task, a cell with a dot to open the
 * chat it came from.
 */

const LIMITS = [10, 20, 0] as const

const PREF_KEY = (p: string) => `sp-task-timeline:${p}`

function readPrefs(key: string): { window: Window; limit: number } {
  const raw = readJsonPref<{ window?: unknown; limit?: unknown } | null>(key, null) ?? {}
  return {
    window: WINDOWS.includes(raw.window as Window) ? raw.window as Window : 'week',
    limit: (LIMITS as readonly number[]).includes(raw.limit as number) ? raw.limit as number : 10,
  }
}

export function TaskTimelinePanel({ projectCode }: { projectCode: string }) {
  // Read again for the next project: the page is reused across projects.
  const [prefs, setPrefs] = useKeyedPref(PREF_KEY(projectCode), readPrefs)
  const [editing, setEditing] = useState<TimelineTask | null>(null)
  const { open: openMention, chat } = useMentionChat()

  const setPref = (next: Partial<{ window: Window; limit: number }>) => {
    setPrefs({ ...prefs, ...next })
  }

  // The last window's lanes stay up while another one loads.
  const qc = useQueryClient()
  const read = useQuery({
    queryKey: ['tasks', 'timeline', projectCode, prefs.window, prefs.limit],
    queryFn: ({ signal }) =>
      getJson<Partial<Payload>>(`/api/tasks/timeline?project=${encodeURIComponent(projectCode)}&window=${prefs.window}&limit=${prefs.limit}`, signal),
    select: (d): Payload => ({
      window: String(d?.window ?? prefs.window),
      since: String(d?.since ?? ''),
      tasks: Array.isArray(d?.tasks) ? d.tasks : [],
    }),
    placeholderData: keepPreviousData,
  })
  const data = read.data ?? null
  const loading = read.isFetching
  const err = read.isError ? (read.error as Error).message : null
  const reread = () => void qc.invalidateQueries({ queryKey: ['tasks', 'timeline', projectCode] })

  const now = Date.now()
  const since = (data && parseIso(data.since)) || now - 7 * 86400e3
  const span = Math.max(1, now - since)
  const x = (ms: number) => Math.max(0, Math.min(100, ((ms - since) / span) * 100))

  const ticks = useMemo(() => {
    const n = prefs.window === 'day' ? 6 : prefs.window === 'week' ? 7 : 6
    return Array.from({ length: n + 1 }, (_, i) => since + (span * i) / n)
  }, [since, span, prefs.window])

  return (
    <section aria-labelledby="task-timeline">
      <div className="flex items-center gap-8 mb-16 flex-wrap">
        <h2 id="task-timeline" className="text-20 font-semibold text-primary" style={{ letterSpacing: '-0.022em' }}>
          {t('Task timeline')}
        </h2>
        <TimelineInfo />
        <span className="ml-auto flex items-center gap-8">
          <Switch value={prefs.window} options={WINDOWS} onChange={(v) => setPref({ window: v })} label={t('Window')} />
          <Switch
            value={String(prefs.limit)}
            options={LIMITS.map(String)}
            render={(v) => (v === '0' ? 'all' : v)}
            onChange={(v) => setPref({ limit: Number(v) })}
            label={t('Tasks')}
          />
        </span>
      </div>

      <Card padding="md">
        {loading && !data ? (
          <LoadingSkeleton variant="row" count={4} />
        ) : err ? (
          <ErrorBanner title={t('Could not load the task timeline')} message={err} onRetry={() => void read.refetch()} />
        ) : !data || data.tasks.length === 0 ? (
          <EmptyState
            title={`Nothing moved in the last ${prefs.window}`}
            subtitle={t('A task appears here when it is created, edited, moved or mentioned in a chat.')}
          />
        ) : (
          <div className="flex flex-col gap-2">
            {/* Axis */}
            <div className="grid" style={{ gridTemplateColumns: LANE_COLS }}>
              <div />
              <div className="relative h-16">
                {ticks.map((t, i) => (
                  <span
                    key={i}
                    className="absolute top-0 text-10 font-mono text-tertiary -translate-x-1/2 whitespace-nowrap"
                    style={{ left: `${x(t)}%` }}
                  >
                    {i === ticks.length - 1 ? 'now' : fmt(t, prefs.window)}
                  </span>
                ))}
              </div>
            </div>
            {data.tasks.map((t) => (
              <Lane key={t.id} task={t} since={since} now={now}
                window={prefs.window} onOpen={() => setEditing(t)} onMention={openMention} />
            ))}
            <LaneLegend />
          </div>
        )}
      </Card>

      {editing && (
        <TaskAddModal
          projectCode={projectCode}
          initialStatus={editing.status || 'unclassified'}
          existingTask={{ id: editing.id, title: editing.title, status: editing.status, priority: editing.priority, impact: editing.impact, effort: editing.effort, assignee: editing.assignee, project: editing.project, projects: editing.projects }}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); reread() }}
        />
      )}
      {chat}
    </section>
  )
}

function Switch<T extends string>({
  value, options, onChange, label, render,
}: {
  value: T
  options: readonly T[]
  onChange: (v: T) => void
  label: string
  render?: (v: T) => string
}) {
  return (
    <Segmented
      label={label}
      value={value}
      onChange={onChange}
      height={20}
      options={options.map((o) => [o, render ? render(o) : o] as const)}
    />
  )
}

function TimelineInfo() {
  return (
    <span
      className="inline-flex h-20 w-20 items-center justify-center rounded-pill text-tertiary hover:text-primary hover:bg-hover"
      title={
        t('Each row is a task over time, one cell per stretch of the window. The colour of a cell: the status it ended in; filled means something happened; a ring means the status changed; a dot: your message naming the task id (amber) or an agent reply naming it. Click a title to open the task, a cell with a dot to open the chat.')
      }
      aria-label={t('About the task timeline')}
    >
      <Info size={12} aria-hidden />
    </span>
  )
}
