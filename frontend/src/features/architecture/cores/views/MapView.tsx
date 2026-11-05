import { useMemo, useState } from 'react'

import { Segmented } from '../../../../components/Segmented'
import { toast } from '../../../../components/primitives'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../../../components/states'
import { coreColor, useCoreWrites, useCoresMap, type ClaimHow, type CoresMap, type MapClaimRow } from '../data'
import { TypeDot, typeWord } from '../parts'
import type { CoreViewProps } from './types'
import { t, tn } from '../../../../i18n/scope/system'

type Mode = 'one' | 'all' | 'none'

/**
 * The cores over the map of the program. The map's parts stand in columns
 * by kind; each part carries a dot for every core that claims it: set by
 * you on this page (solid), under a file the core lives in (outlined), or
 * changed by two or more of its tasks (faint). Pick a core to see its parts
 * and the parts it shares with other cores; click a part to add it to the
 * core or take it out. "Not in a core" shows what no core covers.
 */
export function MapView({ projectCode, cores, onOpen }: CoreViewProps) {
  const { data, isLoading, isError, error, refetch } = useCoresMap(projectCode)
  if (isError) return <ErrorBanner title={t('Could not load the map.')} message={error instanceof Error ? error.message : String(error)} onRetry={() => void refetch()} hideDismiss />
  if (isLoading || !data) return <LoadingSkeleton variant="card" count={2} />
  if (data.rows.length === 0) {
    return <EmptyState title={t('This project has no map yet.')} subtitle={t('Type #map in a chat with an agent of this project. The cores are drawn over the map once it exists.')} />
  }
  return <MapBody data={data} projectCode={projectCode} wanted={new Set(cores.filter((c) => c.status === 'view').map((c) => c.id))} onOpen={onOpen} />
}

function MapBody({ data, projectCode, wanted, onOpen }: { data: CoresMap; projectCode: string; wanted: Set<string>; onOpen: (id: string) => void }) {
  const cores = useMemo(() => data.cores.filter((c) => wanted.has(c.id)), [data.cores, wanted])
  const [mode, setMode] = useState<Mode>('one')
  const [picked, setPicked] = useState(() => [...cores].sort((a, b) => b.rows - a.rows)[0]?.id ?? '')
  const selected = cores.find((c) => c.id === picked) ?? cores[0]
  const byId = useMemo(() => new Map(cores.map((c) => [c.id, c])), [cores])
  const kinds = useMemo(() => {
    const order: string[] = []
    for (const r of data.rows) if (!order.includes(r.kind)) order.push(r.kind)
    return order.map((k) => ({ kind: k, rows: data.rows.filter((r) => r.kind === k) }))
  }, [data.rows])
  const rowsOf = (id: string) => data.rows.filter((r) => r.cores.some((c) => c.id === id))
  const mine = selected ? rowsOf(selected.id) : []
  const shared = mine.filter((r) => r.cores.filter((c) => wanted.has(c.id)).length > 1)

  return (
    <div className="flex gap-20 min-w-0 flex-wrap">
      <div className="flex-[999_1_640px] min-w-0 flex flex-col gap-12">
        <div className="flex items-center gap-12 flex-wrap text-11 font-mono text-tertiary">
          <Segmented label={t('Show')} shape="pill" value={mode} onChange={setMode}
            options={[['one', t('One core')], ['all', t('All cores')], ['none', t('Not in a core')]]} />
          <span>{t('Map version {n}', { n: data.version ?? '—' })} · {tn(data.rows.length, '{n} part', '{n} parts')}</span>
          <span className="ml-auto flex items-center gap-12">
            <span className="flex items-center gap-6"><i className="block w-[8px] h-[8px] rounded-[2px] bg-secondary" />{t('set by you')}</span>
            <span className="flex items-center gap-6"><i className="block w-[8px] h-[8px] rounded-[2px]" style={{ boxShadow: 'inset 0 0 0 1.5px var(--text-secondary)' }} />{t('a file of the core')}</span>
            <span className="flex items-center gap-6"><i className="block w-[8px] h-[8px] rounded-[2px] bg-secondary opacity-40" />{t('changed by its tasks')}</span>
          </span>
        </div>
        <div className="grid gap-12 items-start" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))' }}>
          {kinds.map((k) => (
            <div key={k.kind} className="flex flex-col gap-8 min-w-0">
              <div className="flex items-baseline justify-between px-2">
                <span className="text-10 font-mono uppercase tracking-wider text-secondary">{k.kind}</span>
                <span className="text-10 font-mono text-tertiary">{k.rows.length}</span>
              </div>
              {k.rows.map((r) => <Part key={r.name} row={r} mode={mode} selected={selected?.id ?? ''} byId={byId} projectCode={projectCode} />)}
            </div>
          ))}
        </div>
      </div>

      <aside className="flex-[1_1_300px] max-w-[360px] min-w-0 flex flex-col gap-14">
        {selected && mode === 'one' && (
          <div className="flex flex-col gap-10 rounded-card border border-border-subtle p-14">
            <span className="text-10 font-mono uppercase tracking-wider text-tertiary">{t('Selected core')}</span>
            <button type="button" onClick={() => onOpen(selected.id)} className="flex items-center gap-8 text-left">
              <TypeDot type={selected.type} size={12} />
              <span className="text-16 font-semibold text-primary">{selected.name}</span>
              <span className="ml-auto text-10 font-mono uppercase tracking-wider" style={{ color: coreColor(selected.type) }}>{typeWord(selected.type)}</span>
            </button>
            <div className="grid grid-cols-3 gap-8">
              <Stat n={mine.length} label={t('parts')} />
              <Stat n={shared.length} label={t('shared')} />
              <Stat n={mine.filter((r) => r.cores.find((c) => c.id === selected.id)?.how === 'linked').length} label={t('set by you')} />
            </div>
            {shared.length > 0 && (
              <div className="flex flex-col gap-4">
                <span className="text-10 font-mono uppercase tracking-wider text-tertiary">{t('Shared with other cores')}</span>
                {shared.slice(0, 6).map((r) => (
                  <span key={r.name} className="text-12 text-secondary truncate" title={r.where}>
                    {r.name} <span className="text-10 font-mono text-tertiary">· {r.cores.filter((c) => c.id !== selected.id && byId.has(c.id)).map((c) => byId.get(c.id)?.name).join(', ')}</span>
                  </span>
                ))}
              </div>
            )}
            <p className="m-0 text-11 text-tertiary leading-relaxed">{t('Click a part to add it to this core or take it out. Parts found by its files or tasks stay; add the part to keep it.')}</p>
          </div>
        )}
        <div className="flex flex-col gap-4">
          <span className="text-10 font-mono uppercase tracking-wider text-tertiary">{t('Cores')}</span>
          {cores.map((c) => (
            <button key={c.id} type="button" onClick={() => { setPicked(c.id); setMode('one') }}
              className={`flex items-center gap-8 rounded-input px-8 py-6 text-left ${mode === 'one' && selected?.id === c.id ? 'bg-elevated' : 'hover:bg-surface'}`}>
              <TypeDot type={c.type} />
              <span className="flex-1 text-13 text-primary truncate">{c.name}</span>
              <span className="text-11 font-mono text-tertiary">{tn(c.rows, '{n} part', '{n} parts')}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-4 border-t border-dashed border-border-subtle pt-10">
          <span className="text-10 font-mono uppercase tracking-wider text-tertiary">{t('Not in any core · {n} of {total}', { n: data.unclaimed, total: data.rows.length })}</span>
          <span className="text-12 text-secondary leading-relaxed">
            {data.rows.filter((r) => !r.cores.some((c) => wanted.has(c.id))).slice(0, 12).map((r) => r.name).join(' · ')}
          </span>
        </div>
      </aside>
    </div>
  )
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-input bg-surface px-8 py-6">
      <span className="text-20 font-semibold text-primary leading-none">{n}</span>
      <span className="text-10 font-mono text-tertiary">{label}</span>
    </div>
  )
}

function Part({ row, mode, selected, byId, projectCode }: {
  row: MapClaimRow; mode: Mode; selected: string; byId: Map<string, { id: string; name: string; type: string }>; projectCode: string
}) {
  const claims = row.cores.filter((c) => byId.has(c.id))
  const mineHow = claims.find((c) => c.id === selected)?.how
  const lit = mode === 'one' ? !!mineHow : mode === 'none' ? claims.length === 0 : claims.length > 0
  const sel = byId.get(selected)
  const color = sel ? coreColor(sel.type) : 'var(--brand)'
  const clickable = mode === 'one' && !!sel
  const style = mode === 'one' && mineHow
    ? { background: `color-mix(in srgb, ${color} 10%, transparent)`, borderColor: color }
    : undefined
  const body = (
    <>
      <span className="flex items-start justify-between gap-8">
        <span className="text-12 font-medium text-primary leading-snug break-words min-w-0">{row.name}</span>
        <span className="flex gap-[3px] pt-[3px] shrink-0">
          {claims.map((c) => <Dot key={c.id} type={byId.get(c.id)?.type ?? ''} how={c.how} title={`${byId.get(c.id)?.name ?? ''} · ${howWord(c.how)}`} />)}
        </span>
      </span>
      <span className="text-10 font-mono text-tertiary truncate">{row.where || '—'}</span>
      {mode === 'one' && mineHow && claims.length > 1 && (
        <span className="text-10 font-mono break-words" style={{ color: 'var(--status-amber-ink)' }}>
          {t('also in {cores}', { cores: claims.filter((c) => c.id !== selected).map((c) => byId.get(c.id)?.name).join(', ') })}
        </span>
      )}
    </>
  )
  const cls = `flex flex-col gap-4 rounded-card border px-10 py-8 text-left min-w-0 transition-opacity ${mineHow && mode === 'one' ? 'border-[1.5px]' : 'border-border-subtle bg-surface'} ${lit ? '' : 'opacity-45'}`
  if (!clickable || !sel) return <div className={cls} style={style} title={row.what}>{body}</div>
  return <ToggleablePart row={row} core={sel} how={mineHow} projectCode={projectCode} className={cls} style={style}>{body}</ToggleablePart>
}

function ToggleablePart({ row, core, how, projectCode, className, style, children }: {
  row: MapClaimRow; core: { id: string; name: string }; how?: ClaimHow; projectCode: string
  className: string; style?: React.CSSProperties; children: React.ReactNode
}) {
  const writes = useCoreWrites(projectCode, core.id)
  // The overlay names the map link a part stands on: no second read, and no
  // click that adds while the link is still loading.
  const linkId = row.cores.find((c) => c.id === core.id && c.how === 'linked')?.link_id
  const link = linkId ? { id: linkId } : undefined
  const busy = writes.link.isPending || writes.unlink.isPending
  const toggle = () => {
    const fail = (e: unknown) => toast.error(t('Could not change the core.'), { description: e instanceof Error ? e.message : String(e) })
    if (link) writes.unlink.mutate(link.id, { onError: fail })
    else writes.link.mutate({ kind: 'map', target: row.name }, { onError: fail })
  }
  const label = link ? t('Take {part} out of {core}', { part: row.name, core: core.name }) : t('Add {part} to {core}', { part: row.name, core: core.name })
  return (
    <button type="button" onClick={toggle} disabled={busy} aria-pressed={!!link} aria-label={label}
      title={`${row.what}\n${how && how !== 'linked' && !link ? t('Found by {how}. Click to keep it in the core.', { how: howWord(how) }) : label}`}
      className={`${className} hover:border-border-strong disabled:opacity-60`} style={style}>
      {children}
    </button>
  )
}

function Dot({ type, how, title }: { type: string; how: ClaimHow; title: string }) {
  const color = coreColor(type)
  const style = how === 'linked' ? { background: color } : how === 'files' ? { boxShadow: `inset 0 0 0 1.5px ${color}` } : { background: color, opacity: 0.4 }
  return <i title={title} aria-label={title} className="block w-[8px] h-[8px] rounded-[2px]" style={style} />
}

function howWord(how: ClaimHow): string {
  return how === 'linked' ? t('set by you') : how === 'files' ? t('a file of the core') : t('changed by its tasks')
}
