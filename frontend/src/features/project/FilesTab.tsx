import { Fragment, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, X } from 'lucide-react'
import { IconButton } from '../../components/primitives'
import { Segmented } from '../../components/Segmented'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../components/states'
import { LensDrawer } from '../../lenses/LensDrawer'
import { LENSES } from '../../lenses/config'
import { type Cell, type Entry, type Payload, buildRows, sortRows } from '../files/rows'
import { Controls, CountSwitch, useControls } from '../files/parts'
import { Ranking, Story, Weight } from '../files/views'
import { getJson } from '../../lib/getJson'
import { projectColor } from '../../utils/projectColor'
import { persistPref, readPref } from '../../lib/uiPrefs'
import { Modal } from '../../components/Modal'
import { t, tn } from '../../i18n/scope/project'

/**
 * Files tab — the file × checkpoint heatmap.
 *
 * Columns are file entries (one per scan), grouped under their date by
 * default: a date column is the day's aggregate, and its chevron ungroups
 * it into the day's checkpoints. Clicking a checkpoint header opens the
 * drawer with three views — the entry's per-path judgment, the scan it
 * completed, and the chat the agent was in when it posted — in a centered
 * popup, so the grid stays put underneath.
 */

type HeatmapMode = 'lines' | 'importance'

/** A rendered column: either one date (grouped) or one entry (ungrouped). */
type Column =
  | { kind: 'date'; date: string; entries: Entry[] }
  | { kind: 'entry'; date: string; entry: Entry; first: boolean; last: boolean }

const GROUP_KEY = 'sp-files-group-by-date'
const VIEW_KEY = 'sp-files-view'

/** How the same file activity can be read. The grid is the original. */
const VIEWS = [
  ['grid', 'grid', t('Files per scan, as a heatmap')],
  ['ranking', 'ranking', t('One row per file, with the agent\'s latest note')],
  ['story', 'story', t('One card per file, with what agents wrote about it')],
  ['weight', 'weight', t('Size shows lines changed, shade shows how recent')],
] as const
type ViewKind = (typeof VIEWS)[number][0]

function readGroupPref(): boolean {
  try {
    return readPref(GROUP_KEY) !== 'off'
  } catch {
    return true
  }
}

/**
 * The file activity of one project, or of every project at once (no
 * `projectCode`: the Files page). Over every project the rows carry their
 * project, and a row of project chips narrows them.
 */
export function FilesTab({ projectCode = '' }: { projectCode?: string }) {
  const [mode, setMode] = useState<HeatmapMode>('lines')
  const [scope, setScope] = useState('')
  const [groupByDate, setGroupByDate] = useState<boolean>(readGroupPref)
  const [openDates, setOpenDates] = useState<Set<string>>(() => new Set())
  const [selected, setSelected] = useState<Entry | null>(null)

  // Everything, because ordering a page of fifty would rank the wrong
  // fifty; the count control slices after the sort. Through the query
  // cache (a "files" lens key), so a scan's new file entry shows without
  // a reload.
  const heat = useQuery({
    queryKey: ['lens', 'files', 'heatmap', projectCode],
    queryFn: ({ signal }) =>
      getJson<Payload>(`/api/files/heatmap?${projectCode ? `project=${encodeURIComponent(projectCode)}&` : ''}limit_files=500`, signal),
  })
  // Every project's payload, narrowed to one project by its chip; the
  // cells and the matrix stay whole (their keys carry the project).
  const projects = useMemo(
    () => (projectCode ? [] : [...new Set((heat.data?.entries ?? []).map((e) => e.project ?? ''))].filter(Boolean).sort()),
    [heat.data, projectCode],
  )
  const data = useMemo<Payload | null>(() => {
    const all = heat.data ?? null
    if (!all || !scope || projectCode) return all
    const entries = all.entries.filter((e) => e.project === scope)
    return { ...all, entries, files: all.files.filter((f) => f.project === scope), dates: [...new Set(entries.map((e) => e.date))].sort() }
  }, [heat.data, scope, projectCode])
  const loading = heat.isLoading
  const err = heat.isError ? String((heat.error as Error)?.message ?? heat.error) : null

  const { sort, count, weight, setSort, setCount, setWeight } = useControls()
  const [view, setView] = useState<ViewKind>(() => {
    // readPref: a blocked site store must not take the tab down.
    const saved = readPref(VIEW_KEY) as ViewKind | null
    return saved && VIEWS.some(([k]) => k === saved) ? saved : 'grid'
  })
  const pickView = (v: ViewKind) => {
    setView(v)
    persistPref(VIEW_KEY, v)
  }
  const [openPath, setOpenPath] = useState<string | null>(null)
  // Checkpoints oldest first, for the spark; and one scale so every churn
  // bar on the tab is measured against the same widest file.
  const entryIds = useMemo(
    () => [...(data?.entries ?? [])]
      .sort((a, b) => `${a.date} ${a.time}`.localeCompare(`${b.date} ${b.time}`))
      .map((e) => e.id),
    [data],
  )
  const rows = useMemo(() => (data ? buildRows(data, weight) : []), [data, weight])
  const ordered = useMemo(() => sortRows(rows, sort), [rows, sort])
  const files = useMemo(() => (count === 0 ? ordered : ordered.slice(0, count)), [ordered, count])
  const churnScale = useMemo(
    () => Math.max(1, ...rows.map((r) => Math.max(r.lines_add, r.lines_del))),
    [rows],
  )
  const entries = useMemo(() => data?.entries ?? [], [data])
  const cells = useMemo(() => data?.cells ?? {}, [data])
  const matrix = data?.matrix ?? {}

  const toggleGroup = () => {
    setGroupByDate((g) => {
      try {
        persistPref(GROUP_KEY, g ? 'off' : 'on')
      } catch {
        /* preference just won't persist */
      }
      return !g
    })
  }
  const toggleDate = (d: string) =>
    setOpenDates((s) => {
      const next = new Set(s)
      if (next.has(d)) next.delete(d)
      else next.add(d)
      return next
    })

  // Columns: dates in order; a date is a single aggregate column unless the
  // grouping is off or the date has been ungrouped by its chevron.
  const columns: Column[] = useMemo(() => {
    const byDate = new Map<string, Entry[]>()
    for (const e of entries) {
      const list = byDate.get(e.date) ?? []
      list.push(e)
      byDate.set(e.date, list)
    }
    const out: Column[] = []
    for (const [date, list] of [...byDate.entries()].sort(([a], [b]) => (a < b ? -1 : 1))) {
      const open = !groupByDate || openDates.has(date)
      if (open && list.length > 0) {
        list.forEach((entry, i) =>
          out.push({ kind: 'entry', date, entry, first: i === 0, last: i === list.length - 1 }),
        )
      } else {
        out.push({ kind: 'date', date, entries: list })
      }
    }
    return out
  }, [entries, groupByDate, openDates])

  const cellFor = (path: string, col: Column): Cell | undefined =>
    col.kind === 'date' ? matrix[`${path}||${col.date}`] : cells[`${path}||${col.entry.id}`]

  // Quantile-based intensity over the cells actually on screen — the weight
  // source depends on the selected mode.
  const weightOf = (c: Cell | undefined) => {
    if (!c) return 0
    if (mode === 'importance') return c.semantic_score || 0
    return (c.lines_add || 0) + (c.lines_del || 0) || c.count || 0
  }
  const nonZero: number[] = []
  for (const f of files) {
    for (const col of columns) {
      const w = weightOf(cellFor(f.key ?? f.path, col))
      if (w > 0) nonZero.push(w)
    }
  }
  nonZero.sort((a, b) => a - b)
  // The lowest step must still read as brand beside an untouched cell's
  // grey, on screen and in a screenshot; 22% was lost against --bg-hover.
  const BUCKET_PCTS = [42, 56, 70, 85, 100]
  const quartiles: number[] = []
  if (nonZero.length > 0) {
    for (const p of [0.2, 0.4, 0.6, 0.8]) {
      const idx = Math.min(nonZero.length - 1, Math.floor(nonZero.length * p))
      quartiles.push(nonZero[idx]!)
    }
  }
  const bucketPct = (w: number): number => {
    if (w <= 0) return 0
    if (quartiles.length === 0) return BUCKET_PCTS[4]!
    for (let i = 0; i < quartiles.length; i++) {
      if (w <= quartiles[i]!) return BUCKET_PCTS[i]!
    }
    return BUCKET_PCTS[4]!
  }

  if (loading) return <LoadingSkeleton variant="chart" label={t('Loading file activity')} />
  if (err) {
    return (
      <ErrorBanner
        title={t('Could not load file activity')}
        message={err}
        onRetry={() => void heat.refetch()}
      />
    )
  }
  if (files.length === 0 || entries.length === 0) {
    return (
      <EmptyState
        title={t('No file activity yet')}
        subtitle={t('Each #scan writes a file entry.')}
      />
    )
  }

  const COL_W = 14
  const gridCols = `minmax(160px, auto) ${columns
    .map((c) => (c.kind === 'date' ? '22px' : `${COL_W}px`))
    .join(' ')}`

  return (
    <>
      {/* No frame of its own: the tab sits on the page, and the order-by box is the one frame. */}
      <div>
        <div className="mb-12 flex flex-col gap-8">
          <div className="flex items-center gap-10 flex-wrap">
          {projects.length > 0 && (
            <Segmented label={t('Project')} shape="pill" value={scope} onChange={setScope}
              options={[['', t('all'), t('Every project')] as const, ...projects.map((p) => [p, p, p] as const)]} />
          )}
          <Segmented label={t('File view')} shape="pill" value={view} onChange={pickView}
            options={VIEWS.map(([k, label, hint]) => [k, label, hint] as const)} />
          <span className="ml-auto"><CountSwitch count={count} onCount={setCount} /></span>
          </div>
          <Controls
            sort={sort} weight={weight}
            onSort={setSort} onWeight={setWeight}
            total={ordered.length} shown={files.length}
          />
        </div>
        <div className="flex items-center gap-8 mb-12 flex-wrap">
          <span className="text-11 uppercase tracking-wide text-tertiary font-mono">{t('File activity')}</span>
          <span className="text-11 text-tertiary font-mono">
            {files.length === ordered.length ? tn(files.length, '{n} file', '{n} files') : t('{n} of {total} files', { n: files.length, total: ordered.length })}
            {' · '}{tn(entries.length, '{n} scan', '{n} scans')} · {tn(data?.dates.length ?? 0, '{n} date', '{n} dates')}
          </span>
          {view === 'grid' && (
          <button
            type="button"
            onClick={toggleGroup}
            aria-pressed={groupByDate}
            className={`text-11 font-mono px-8 h-24 rounded-pill border transition-colors ${
              groupByDate
                ? 'border-brand text-brand'
                : 'border-border-default text-tertiary hover:text-primary'
            }`}
            title={t('Grouped: one column per date. Off: one column per scan.')}
          >
            {t('group by date')}
          </button>
          )}
          {(view === 'grid' || view === 'weight') && (
          <div className="ml-auto flex items-center gap-4">
            <span className="text-10 text-tertiary font-mono">{t('color by')}</span>
            <Segmented label={t('Color by')} shape="pill" value={mode} onChange={setMode}
              options={(['lines', 'importance'] as HeatmapMode[]).map((m) => [m, m] as const)} />
          </div>
          )}
        </div>
        {view === 'grid' ? (
        <div className="overflow-x-auto">
          <div
            aria-label={t('Files changed per scan')}
            className="inline-grid gap-2 items-end"
            style={{ gridTemplateColumns: gridCols }}
          >
            <div />
            {columns.map((col) =>
              col.kind === 'date' ? (
                <ColumnHeader
                  key={`d-${col.date}`}
                  label={col.date}
                  title={t('{date} · {scans} — click to ungroup', { date: col.date, scans: tn(col.entries.length, '{n} scan', '{n} scans') })}
                  onClick={() => toggleDate(col.date)}
                  chevron={groupByDate ? 'closed' : undefined}
                  disabled={col.entries.length === 0}
                />
              ) : (
                <ColumnHeader
                  key={`e-${col.entry.id}`}
                  label={col.first ? `${col.date} ${col.entry.time}` : col.entry.time}
                  title={`${col.date} ${col.entry.time} · ${col.entry.l1 || col.entry.id}${
                    col.entry.scan_id ? ` · ${t('scan')} ${col.entry.scan_id}` : ''
                  } — ${t('click to open')}`}
                  onClick={() => setSelected(col.entry)}
                  active={selected?.id === col.entry.id}
                  chevron={groupByDate && col.first ? 'open' : undefined}
                  onChevron={groupByDate && col.first ? () => toggleDate(col.date) : undefined}
                />
              ),
            )}
            {files.map((f) => (
              <Fragment key={f.key ?? f.path}>
                <div
                  className="text-12 text-secondary font-mono truncate pr-8 text-right"
                  title={`${f.project ? `${f.project} · ` : ''}${f.path} · ${f.total} touches · +${f.lines_add}/−${f.lines_del}`}
                  style={{ direction: 'rtl', maxWidth: 280 }}
                >
                  {/* rtl puts the ellipsis on the left, so a long path keeps
                      its file name; the path itself stays left to right, or a
                      leading dot (.github/…) jumps to the end. */}
                  {f.project && <span className="inline-block h-6 w-6 rounded-pill mr-4 align-middle" style={{ backgroundColor: projectColor(f.project) }} title={f.project} aria-hidden />}
                  <bdi dir="ltr">{f.path}</bdi>
                </div>
                {columns.map((col) => {
                  const cell = cellFor(f.key ?? f.path, col)
                  const w = weightOf(cell)
                  const pct = bucketPct(w)
                  const key = col.kind === 'date' ? `d-${col.date}` : `e-${col.entry.id}`
                  const when = col.kind === 'date' ? col.date : `${col.date} ${col.entry.time}`
                  const tip = cell
                    ? [
                        `${f.path} · ${when}`,
                        col.kind === 'date'
                          ? `${cell.count}× touched · +${cell.lines_add}/−${cell.lines_del}`
                          : `${cell.action ?? 'modified'} · +${cell.lines_add}/−${cell.lines_del}`,
                        `importance: ${cell.semantic_score ?? '—'}`,
                        cell.why ? `why: ${cell.why}` : null,
                        cell.tags && cell.tags.length > 0 ? `tags: ${cell.tags.join(', ')}` : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')
                    : t('{path} · {when} · not changed', { path: f.path, when })
                  const onClick =
                    !cell
                      ? undefined
                      : col.kind === 'entry'
                        ? () => setSelected(col.entry)
                        : () => toggleDate(col.date)
                  return (
                    <div
                      key={key}
                      title={tip}
                      role={onClick ? 'button' : undefined}
                      tabIndex={onClick ? 0 : undefined}
                      onClick={onClick}
                      onKeyDown={(e) => {
                        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
                          e.preventDefault()
                          onClick()
                        }
                      }}
                      className={`rounded-bar ${onClick ? 'cursor-pointer hover:outline hover:outline-1 hover:outline-brand' : ''}`}
                      style={{
                        width: col.kind === 'date' ? 22 : COL_W,
                        height: COL_W,
                        backgroundColor:
                          w === 0
                            ? 'var(--bg-hover)'
                            : `color-mix(in oklab, var(--brand) ${pct}%, transparent)`,
                      }}
                    />
                  )
                })}
              </Fragment>
            ))}
          </div>
        </div>
        ) : view === 'ranking' ? (
          <Ranking rows={files} entryIds={entryIds} scale={churnScale} open={openPath} onOpen={setOpenPath} />
        ) : view === 'story' ? (
          <Story rows={files} scale={churnScale} />
        ) : (
          <Weight rows={files} open={openPath} onOpen={setOpenPath} mode={mode} />
        )}
      </div>

      {selected && (
        <CheckpointDrawer entry={selected} onClose={() => setSelected(null)} />
      )}
    </>
  )
}

function ColumnHeader({
  label,
  title,
  onClick,
  active,
  chevron,
  onChevron,
  disabled,
}: {
  label: string
  title: string
  onClick: () => void
  active?: boolean
  chevron?: 'open' | 'closed'
  onChevron?: () => void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-col items-center gap-2">
      {chevron && (
        <button
          type="button"
          onClick={onChevron ?? onClick}
          aria-label={chevron === 'open' ? t('Group this date') : t('Ungroup this date')}
          className="h-14 w-14 inline-flex items-center justify-center text-tertiary hover:text-primary"
        >
          {chevron === 'open' ? (
            <ChevronDown size={11} aria-hidden />
          ) : (
            <ChevronRight size={11} aria-hidden />
          )}
        </button>
      )}
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        title={title}
        className={`text-11 tabular font-mono leading-none whitespace-nowrap transition-colors ${
          active ? 'text-brand' : 'text-tertiary hover:text-primary'
        } disabled:cursor-default disabled:hover:text-tertiary`}
        style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', letterSpacing: '0.04em' }}
      >
        {label}
      </button>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Checkpoint drawer — files · scan · chat
 * ------------------------------------------------------------------------- */

type View = 'files' | 'scan' | 'chat'

function CheckpointDrawer({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const [view, setView] = useState<View>('files')

  const views: Array<{ key: View; label: string; id: string; missing: string }> = [
    { key: 'files', label: t('Files'), id: entry.id, missing: '' },
    {
      key: 'scan',
      label: t('Scan'),
      id: entry.scan_id,
      missing: entry.trigger_lens
        ? t('This entry was triggered by a {kind}, not a scan.', { kind: entry.trigger_lens })
        : t('This entry was posted without a scan.'),
    },
    {
      key: 'chat',
      label: t('Chat'),
      id: entry.session_id,
      missing: t('No chat for agent "{agent}" on {date}. The link needs the entry\'s agent id to match a chat.', { agent: entry.agent_id, date: entry.date }),
    },
  ]
  const current = views.find((v) => v.key === view)!
  const lensFor: Record<View, string> = { files: 'files', scan: 'scans', chat: 'sessions' }

  return (
    <Modal label={t('Scan detail')} onClose={onClose} width="w-[760px]" padding="p-0" top>
      <section className="max-h-[86vh] flex flex-col overflow-hidden">
        <div className="flex items-center gap-8 px-16 py-10 border-b border-border-subtle">
          <span className="text-12 font-mono text-secondary truncate">
            {entry.date} {entry.time} · {entry.agent_id} · {current.id || entry.id}
          </span>
          <div
            role="tablist"
            aria-label={t('Scan views')}
            className="ml-auto inline-flex rounded-input border border-border-subtle overflow-hidden"
          >
            {views.map((v) => (
              <button
                key={v.key}
                type="button"
                role="tab"
                aria-selected={view === v.key}
                onClick={() => setView(v.key)}
                className={`px-12 h-24 text-12 transition-colors ${
                  view === v.key ? 'bg-hover text-primary' : 'text-tertiary hover:text-secondary'
                } ${!v.id ? 'opacity-60' : ''}`}
              >
                {v.label}
              </button>
            ))}
          </div>
          <IconButton label={t('Close scan detail')} onClick={onClose}>
            <X size={15} aria-hidden />
          </IconButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {current.id ? (
            <LensDrawer
              key={`${view}-${current.id}`}
              lens={LENSES[lensFor[view]]!}
              id={current.id}
              presentation="embedded"
              header={false}
              onClose={onClose}
            />
          ) : (
            <p className="text-13 text-tertiary leading-relaxed px-16 py-16">{current.missing}</p>
          )}
        </div>
      </section>
    </Modal>
  )
}
