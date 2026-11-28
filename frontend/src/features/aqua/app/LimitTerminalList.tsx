import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Info } from 'lucide-react'

import { locale, t } from '../../../i18n/scope/aqua'
import { getJson } from '../../../lib/getJson'
import { TERMINAL_AGENT_KINDS, type TerminalAgentKind, type TerminalLimitSession } from '../../../lib/terminalLimit'
import { limitAgents, memoryText } from './limitLabels'
import { triageTerminals, type FilterState, type GroupMode, type SortColumn, type Triage } from './limitModel'

const sortedColumns: { key: SortColumn; name: string }[] = [
  { key: 'label', name: t('Name') }, { key: 'project', name: t('Project') }, { key: 'agent_kind', name: t('Agent') },
  { key: 'created', name: t('Created') }, { key: 'last_opened', name: t('Last opened') },
  { key: 'last_activity', name: t('Last action') }, { key: 'activity', name: t('Activity') }, { key: 'memory_bytes', name: t('Memory') },
]
const defaultFilters: Triage = { project: '', agent: '', state: '', inactiveDays: 0, group: 'project', sort: 'last_activity', descending: true }
const bodyCell = 'whitespace-nowrap border-b border-border-subtle px-8 py-4'
const select = 'h-[24px] rounded-input bg-surface px-4 text-12'
const check = 'accent-[var(--aq-accent)]'
const groupsByDate: Record<string, string> = { today: t('Today'), week: t('This week'), older: t('Older') }
const states = { attached: t('Attached'), running: t('Running'), idle: t('Idle') } as const

function when(date: string | number | null): string {
  if (date == null || date === '') return t('Unknown')
  const value = new Date(typeof date === 'number' ? date * 1000 : date)
  if (Number.isNaN(value.getTime())) return t('Unknown')
  return new Intl.DateTimeFormat(locale(), { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(value)
}

interface Excerpts {
  kind: 'messages' | 'lines'
  first: { at?: string; text: string }[]
  last: { at?: string; text: string }[]
}

function RowExcerpts({ id }: { id: string }) {
  const result = useQuery({
    queryKey: ['terminal', 'excerpts', id],
    queryFn: ({ signal }) => getJson<Excerpts>(`/api/terminal/sessions/${encodeURIComponent(id)}/excerpts`, signal),
    retry: false,
  })
  const data = result.data
  if (result.isPending) return <p role="status" className="m-0 py-6 aq-ink3">{t('Loading excerpts…')}</p>
  if (!data) return <p role="alert" className="m-0 py-6">{t('Could not load excerpts.')}</p>
  if (!data.first.length && !data.last.length) return <p className="m-0 py-6 aq-ink3">{t('No excerpts available.')}</p>
  const groups = [
    { title: data.kind === 'messages' ? t('First messages') : t('First lines'), lines: data.first },
    { title: data.kind === 'messages' ? t('Latest messages') : t('Latest lines'), lines: data.last },
  ]
  return (
    <div className="grid grid-cols-2 gap-16 py-8">
      {groups.map(({ title, lines }) => (
        <section key={title}>
          <h3 className="aq-label">{title}</h3>
          <ol className="m-0 list-none divide-y divide-border-subtle p-0">
            {lines.map(({ at, text }, i) => (
              <li key={i} className="flex flex-wrap gap-x-8 py-6 whitespace-normal">
                {at && <time dateTime={at} className="font-mono text-11 aq-ink3">{when(at)}</time>}
                <p className="m-0 whitespace-pre-wrap break-words">{text}</p>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  )
}

export function LimitTerminalList({ rows, selected, setSelected, busy, actions }: {
  rows: TerminalLimitSession[]
  selected: ReadonlySet<string>
  setSelected: (ids: ReadonlySet<string>) => void
  busy: boolean
  actions: React.ReactNode
}) {
  const [filters, setFilters] = useState(defaultFilters)
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set())
  const projects = [...new Set(rows.map(({ project }) => project))].sort()
  const grouped = triageTerminals(rows, filters, Date.now() / 1000)
  const visible = grouped.flatMap(({ rows }) => rows)
  const everyVisibleSelected = visible.length > 0 && visible.every(({ id }) => selected.has(id))
  const maxActivity = Math.max(1, ...visible.map(({ activity }) => activity ?? 0))
  const activityHint = t('Activity is operator turns in the last seven days plus a fraction for how recently the operator typed.')
  const filterBy = (changes: Partial<Triage>) => {
    setFilters((current) => ({ ...current, ...changes }))
    setSelected(new Set())
  }
  const toggle = (id: string, checked: boolean) => {
    const next = new Set(selected)
    if (checked) next.add(id)
    else next.delete(id)
    setSelected(next)
  }
  const toggleExpanded = (id: string) => setExpanded((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })
  const sortBy = (key: SortColumn) => setFilters((current) => ({
    ...current, sort: key, descending: current.sort === key ? !current.descending : key !== 'label' && key !== 'project' && key !== 'agent_kind',
  }))
  const selectVisible = (checked: boolean) => setSelected(new Set(checked ? visible.map(({ id }) => id) : []))

  return (
    <>
      <div className="flex shrink-0 items-center gap-8">
        <h2 className="mr-auto text-13 font-medium">{t('Terminals')}</h2>
        {actions}
      </div>
      <div className="flex shrink-0 flex-wrap items-end gap-8">
        <label className="grid gap-4"><span className="aq-label">{t('Project')}</span>
          <select className={select} value={filters.project} disabled={busy} onChange={(e) => filterBy({ project: e.target.value })}>
            <option value="">{t('All projects')}</option>
            {projects.filter(Boolean).map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className="grid gap-4"><span className="aq-label">{t('Agent')}</span>
          <select className={select} value={filters.agent} disabled={busy} onChange={(e) => filterBy({ agent: e.target.value as TerminalAgentKind | '' })}>
            <option value="">{t('All agents')}</option>
            {TERMINAL_AGENT_KINDS.map((kind) => <option key={kind} value={kind}>{limitAgents[kind]}</option>)}
          </select>
        </label>
        <label className="grid gap-4"><span className="aq-label">{t('State')}</span>
          <select className={select} value={filters.state} disabled={busy} onChange={(e) => filterBy({ state: e.target.value as FilterState })}>
            <option value="">{t('All states')}</option>
            {Object.entries(states).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </label>
        <label className="grid gap-4"><span className="aq-label">{t('Inactive more than (days)')}</span>
          <input type="number" min="1" step="1" placeholder={t('Any time')} className={select + ' w-96'}
            value={filters.inactiveDays || ''} disabled={busy} onChange={(e) => filterBy({ inactiveDays: Math.max(0, Number(e.target.value) || 0) })} />
        </label>
        <label className="grid gap-4"><span className="aq-label">{t('Group by')}</span>
          <select className={select} value={filters.group} disabled={busy} onChange={(e) => setFilters({ ...filters, group: e.target.value as GroupMode })}>
            <option value="project">{t('Project')}</option><option value="date">{t('Date')}</option><option value="">{t('None')}</option>
          </select>
        </label>
        <button type="button" className="aq-btn line ml-auto disabled:opacity-40" disabled={busy || !visible.length} onClick={() => selectVisible(true)}>
          {t('Select all visible')}
        </button>
      </div>
      <div className="aq-scroll min-h-[130px] flex-1 overflow-auto rounded-[6px] border border-border-subtle bg-base">
        <table aria-label={t('Open terminals')} className="w-full min-w-[760px] border-separate border-spacing-0 text-12 tabular-nums">
          <thead className="sticky top-0 z-[1] bg-surface">
            <tr>
              <th scope="col" className={bodyCell}><input type="checkbox" aria-label={t('Select all visible terminals')}
                className={check} checked={everyVisibleSelected} disabled={busy || !visible.length} onChange={(e) => selectVisible(e.target.checked)} /></th>
              {sortedColumns.map(({ key, name }) => (
                <th key={key} scope="col" className={bodyCell + ' text-left'} aria-sort={key === filters.sort ? filters.descending ? 'descending' : 'ascending' : undefined}>
                  <span className="flex items-center gap-4">
                    <button type="button" className="aq-btn" onClick={() => sortBy(key)}>{name}
                      {key === filters.sort && (filters.descending ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
                    </button>
                    {key === 'activity' && <span tabIndex={0} aria-label={activityHint} title={activityHint}><Info size={11} /></span>}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          {grouped.map(({ key, rows }) => (
            <tbody key={key}>
              {filters.group && <tr className="bg-surface"><th scope="rowgroup" colSpan={9} className={bodyCell + ' text-left font-mono font-normal'}>
                {filters.group === 'date' ? groupsByDate[key] : key || t('No project')}
                <span className="ml-8 aq-ink3">{rows.length}</span>
              </th></tr>}
              {rows.map((row) => (
                <Fragment key={row.id}>
                  <tr className={selected.has(row.id) ? 'bg-[var(--aq-hover)]' : ''}>
                    <td className={bodyCell}><input type="checkbox" className={check} aria-label={t('Select {name}', { name: row.label })}
                      checked={selected.has(row.id)} disabled={busy} onChange={(e) => toggle(row.id, e.target.checked)} /></td>
                    <td className={bodyCell}>
                      <div className="flex items-center gap-4">
                        <button type="button" className="aq-btn icon" aria-expanded={expanded.has(row.id)}
                          aria-label={t('Excerpts for {name}', { name: row.label })} onClick={() => toggleExpanded(row.id)}>
                          {expanded.has(row.id) ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        </button>
                        <span className="font-medium">{row.label}</span>
                        {row.recent_output && <span className="inline-flex items-center gap-4 text-11"><span className="aq-dot working" />{t('Running')}</span>}
                        {row.attached && <span className="text-11 aq-ink3">{t('Attached')}</span>}
                      </div>
                    </td>
                    <td className={bodyCell}>{row.project || t('No project')}</td>
                    <td className={bodyCell}>{limitAgents[row.agent_kind] ?? t('Shell')}</td>
                    <td className={bodyCell + ' font-mono text-11 aq-ink2'}>{when(row.created)}</td>
                    <td className={bodyCell + ' font-mono text-11 aq-ink2'}>{when(row.last_opened)}</td>
                    <td className={bodyCell + ' font-mono text-11 aq-ink2'}>{when(row.last_activity)}</td>
                    <td className={bodyCell}>
                      <div className="flex items-center gap-6 font-mono text-11">
                        <span aria-hidden="true" className="h-[3px] w-32 bg-border-strong">
                          <span className="block h-full bg-[var(--aq-accent)]" style={{ width: (row.activity ?? 0) / maxActivity * 100 + '%' }} />
                        </span>
                        {new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(row.activity ?? 0)}
                      </div>
                    </td>
                    <td className={bodyCell + ' font-mono text-11'}>{memoryText(row.memory_bytes ?? null)}</td>
                  </tr>
                  {expanded.has(row.id) && <tr className="bg-surface"><td className="border-b border-border-subtle" />
                    <td colSpan={8} className="border-b border-border-subtle px-10"><RowExcerpts id={row.id} /></td></tr>}
                </Fragment>
              ))}
            </tbody>
          ))}
          {!visible.length && <tbody><tr><td colSpan={9} className="px-10 py-12 aq-ink3">{t('No terminals match these filters.')}</td></tr></tbody>}
        </table>
      </div>
    </>
  )
}
