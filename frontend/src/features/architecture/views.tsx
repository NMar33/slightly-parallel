import { useMemo, useState } from 'react'
import { FilterPill } from '../../components/FilterPill'
import { ChevronDown, ChevronRight, File, Folder } from 'lucide-react'

import { Segmented } from '../../components/Segmented'
import { useHashState } from '../../hooks/useHashState'
import { LensDrawer } from '../../lenses/LensDrawer'
import { LENSES } from '../../lenses/config'
import { persistPref, readPref } from '../../lib/uiPrefs'
import {
  type Change, type Entity, type Model, type PathNode, type ScanAnswer,
  fmtDate, groupTone, splitSymbol,
} from './ledger'
import { ChangeLine, CoverageRibbon, OpMark, PathBits, TypeChip } from './ledgerParts'
import { t, tn } from '../../i18n/scope/system'

/**
 * The three readings of the architecture ledger, as the product uses them.
 *
 *   register — every named thing, folded from the changes that made it
 *   stream   — every scan in order, its changes under it, its silences shown
 *   codebase — the declared anchors as a tree over the repo
 *
 * Each is a pure body over one folded `Model`, so the project tab and the
 * fleet-wide page render the very same components.
 * The frame around them owns the project, the standing owes and the
 * switch; a view owns its own filters.
 */

type ArchView = 'register' | 'stream' | 'codebase'

const ARCH_VIEWS: Array<[ArchView, string, string]> = [
  ['register', t('register'), t('Every named part, with its paths, fields and history')],
  ['stream', t('stream'), t('Every scan in order with its changes, including scans without an architecture form')],
  ['codebase', t('codebase'), t('The repository as a tree, with the named parts in each file')],
]

const VIEW_KEY = 'sp-architecture-view'

/** The operator's last reading, remembered. */
export function useArchView(): [ArchView, (v: ArchView) => void] {
  const [view, setView] = useState<ArchView>(() => {
    const kept = readPref(VIEW_KEY)
    return kept === 'stream' || kept === 'codebase' ? kept : 'register'
  })
  return [view, (v) => { setView(v); persistPref(VIEW_KEY, v) }]
}

export function ArchViewSwitch({ value, onChange }: { value: ArchView; onChange: (v: ArchView) => void }) {
  return (
    <Segmented label={t('Architecture view')} shape="pill" value={value} onChange={onChange} options={ARCH_VIEWS} />
  )
}

export function ArchitectureView({ m, view, find = true }: { m: Model; view: ArchView; find?: boolean }) {
  if (view === 'stream') return <StreamView m={m} />
  if (view === 'codebase') return <CodebaseView m={m} />
  return <RegisterView m={m} find={find} />
}

// ---------------------------------------------------------------------------
// register
// ---------------------------------------------------------------------------

/** `find={false}` where the page above already carries the find box. */
function RegisterView({ m, find = true }: { m: Model; find?: boolean }) {
  const [hash, setHash] = useHashState()
  const q = hash.q ?? ''
  const setQ = (v: string) => setHash({ q: v })
  const [gone, setGone] = useState(true)
  const [picked, setPicked] = useState<string>('')
  const [drawer, setDrawer] = useState<{ lens: string; id: string } | null>(null)

  const needle = q.trim().toLowerCase()
  const shown = useMemo(
    () => m.entities.filter((e) =>
      (gone || !e.gone) &&
      (!needle || `${e.type} ${e.name} ${e.note} ${e.paths.join(' ')}`.toLowerCase().includes(needle))),
    [m.entities, needle, gone],
  )
  const blocks = m.groups
    .map((g) => ({ group: g, rows: shown.filter((e) => e.group === g) }))
    .filter((b) => b.rows.length > 0)
  const current = shown.find((e) => e.key === picked) ?? shown[0] ?? null

  return (
    <div className="grid gap-16 min-w-0" style={{ gridTemplateColumns: 'minmax(220px, 300px) minmax(0, 1fr)' }}>
      <div className="flex flex-col gap-8 min-w-0 self-start sticky top-16 max-h-[85vh] overflow-auto pr-4">
        <div className="flex items-center gap-6">
          {find && (
            <input
              value={q}
              onChange={(e) => setQ(e.currentTarget.value)}
              placeholder={t('find')}
              aria-label={t('Find an entry')}
              className="flex-1 min-w-0 h-24 px-10 rounded-input border border-border-subtle bg-elevated text-12 text-primary placeholder:text-tertiary focus:outline-none focus:border-brand"
            />
          )}
          <button
            type="button"
            onClick={() => setGone((v) => !v)}
            aria-pressed={!gone}
            title={t('Hide removed items')}
            className={`h-24 px-8 rounded-pill border text-10 font-mono ${gone ? 'border-border-subtle bg-elevated text-tertiary hover:text-primary' : 'border-brand bg-brand-glow text-primary'}`}
          >
            {gone ? t('all') : t('standing')}
          </button>
        </div>
        {blocks.length === 0 && <p className="text-12 text-tertiary italic">{t('Nothing matches.')}</p>}
        {blocks.map((b) => (
          <section key={b.group} className="flex flex-col gap-2 min-w-0">
            <header className="flex items-baseline gap-6 pt-6">
              <span className="w-6 h-6 rounded-pill shrink-0" style={{ background: groupTone(b.group) }} aria-hidden />
              <h3 className="text-10 font-mono uppercase tracking-wide text-tertiary">{t(b.group)}</h3>
              <span className="ml-auto text-10 font-mono text-tertiary tabular-nums">{b.rows.length}</span>
            </header>
            <ul className="flex flex-col">
              {b.rows.map((e) => (
                <li key={e.key}>
                  <button
                    type="button"
                    onClick={() => setPicked(e.key)}
                    aria-current={current?.key === e.key}
                    className={`w-full text-left rounded-input px-8 py-4 flex flex-col gap-1 min-w-0 ${current?.key === e.key ? 'bg-brand-glow' : 'hover:bg-hover'}`}
                  >
                    <span className="flex items-baseline gap-6 min-w-0">
                      <span className="text-10 font-mono text-tertiary shrink-0">{t(e.type)}</span>
                      <span className={`text-12 text-primary truncate ${e.gone ? 'line-through opacity-70' : ''}`}>{e.name}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className="min-w-0">
        {current
          ? <EntityDetail e={current} m={m} onScan={(id) => setDrawer({ lens: 'scans', id })} />
          : <p className="text-12 text-tertiary italic">{t('Nothing selected.')}</p>}
      </div>

      {drawer && LENSES[drawer.lens] && (
        <LensDrawer lens={LENSES[drawer.lens]!} id={drawer.id} presentation="reading" onClose={() => setDrawer(null)} />
      )}
    </div>
  )
}

function EntityDetail({ e, m, onScan }: { e: Entity; m: Model; onScan: (id: string) => void }) {
  const fields = Object.entries(e.fields)
  const scanOf = (id: string) => m.scans.find((s) => s.id === id) ?? null
  return (
    <article className="flex flex-col gap-14 min-w-0">
      <header className="flex flex-col gap-6">
        <div className="flex items-baseline gap-8 flex-wrap">
          <TypeChip type={e.type} group={e.group} />
          <span className="text-10 font-mono text-tertiary">{t(e.group)}</span>
          {e.gone && (
            <span className="text-10 font-mono px-6 rounded-pill" style={{ color: 'var(--status-red)', background: 'color-mix(in srgb, var(--status-red) 12%, transparent)' }}>
              {t('removed')}
            </span>
          )}
          {e.task && <span className="text-10 font-mono text-brand">{e.task}</span>}
        </div>
        <h2 className={`text-20 font-semibold text-primary ${e.gone ? 'line-through opacity-70' : ''}`} style={{ letterSpacing: '-0.015em' }}>
          {e.name}
        </h2>
        {e.note && <p className="text-13 text-secondary max-w-reading">{e.note}</p>}
      </header>

      {e.paths.length > 0 && (
        <section className="flex flex-col gap-4">
          <h3 className="text-10 font-mono uppercase tracking-wide text-tertiary">{t('where')}</h3>
          <ul className="flex flex-col gap-2">
            {e.paths.map((p) => {
              const [file, symbol] = splitSymbol(p)
              return (
                <li key={p} className="text-11 font-mono text-secondary break-all">
                  {file}{symbol && <span className="text-brand">:{symbol}</span>}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      {fields.length > 0 && (
        <section className="flex flex-col gap-4">
          <h3 className="text-10 font-mono uppercase tracking-wide text-tertiary">{t('fields of this type')}</h3>
          <dl className="grid gap-x-14 gap-y-2" style={{ gridTemplateColumns: 'max-content minmax(0, 1fr)' }}>
            {fields.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-10 font-mono text-tertiary">{k}</dt>
                <dd className="text-12 text-secondary min-w-0 break-words">{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section className="flex flex-col gap-4">
        <h3 className="text-10 font-mono uppercase tracking-wide text-tertiary">
          {t('history')} · {tn(e.changes.length, '{n} change', '{n} changes')}
        </h3>
        <ol className="flex flex-col divide-y divide-border-subtle">
          {[...e.changes].reverse().map((c) => {
            const s = c.trigger_id ? scanOf(c.trigger_id) : null
            return (
              <li key={c.id} className="py-6 flex flex-col gap-2 min-w-0">
                <div className="flex items-baseline gap-8 flex-wrap">
                  <OpMark op={c.op} />
                  <span className="text-12 text-primary">{t(c.op)}</span>
                  <span className="text-10 font-mono text-tertiary">{fmtDate(c.created_date)} {c.created_time}</span>
                  <span className="text-10 font-mono text-tertiary">{c.agent_id}</span>
                  {c.trigger_id ? (
                    <button type="button" onClick={() => onScan(c.trigger_id)} className="ml-auto text-10 font-mono text-brand hover:underline">
                      {c.trigger_id}
                    </button>
                  ) : (
                    <span className="ml-auto text-10 font-mono text-tertiary">{t('without a scan')}</span>
                  )}
                </div>
                {c.note && <p className="text-12 text-secondary">{c.note}</p>}
                {s && <p className="text-11 text-tertiary truncate">{s.l1}</p>}
              </li>
            )
          })}
        </ol>
      </section>
    </article>
  )
}

// ---------------------------------------------------------------------------
// stream
// ---------------------------------------------------------------------------

type Row =
  | { kind: 'scan'; key: string; date: string; scan: ScanAnswer }
  | { kind: 'loose'; key: string; date: string; changes: Change[] }

function StreamView({ m }: { m: Model }) {
  const [onlyAnswered, setOnlyAnswered] = useState(false)
  const [group, setGroup] = useState('')
  const [drawer, setDrawer] = useState<{ lens: string; id: string } | null>(null)

  const rows = useMemo<Row[]>(() => {
    const looseByDate = new Map<string, Change[]>()
    for (const c of m.loose) {
      const list = looseByDate.get(c.created_date) ?? []
      list.push(c)
      looseByDate.set(c.created_date, list)
    }
    const out: Row[] = [
      ...m.scans.map((s) => ({ kind: 'scan' as const, key: s.id, date: s.date, scan: s })),
      ...[...looseByDate.entries()].map(([date, changes]) => ({ kind: 'loose' as const, key: `loose-${date}`, date, changes })),
    ]
    return out.sort((a, b) => b.date.localeCompare(a.date))
  }, [m])

  const keep = (c: Change) => !group || c.group === group
  const visible = rows.filter((r) => {
    if (r.kind === 'loose') return r.changes.some(keep)
    if (onlyAnswered && !r.scan.answered) return false
    if (group) return r.scan.changes.some(keep)
    return true
  })

  let lastDate = ''
  return (
    <div className="flex flex-col gap-14 min-w-0">
      <section className="rounded-card border border-border-subtle bg-surface px-14 py-10 flex flex-col gap-8">
        <div className="flex items-baseline gap-10 flex-wrap">
          <span className="text-10 font-mono text-tertiary uppercase tracking-wide">{t('every scan, oldest first')}</span>
          <span className="text-11 text-secondary">
            {m.scans.length === 0
              ? t('no scans yet.')
              : m.answered === m.scans.length
                ? t('every scan carries an answer.')
                : t('{n} of {total} scans have no architecture answer behind them.', { n: m.scans.length - m.answered, total: m.scans.length })}
          </span>
          <span className="ml-auto inline-flex items-center gap-4 flex-wrap">
            <Chip label={t('only answered')} active={onlyAnswered} onClick={() => setOnlyAnswered((v) => !v)} />
            <Chip label={t('every group')} active={group === ''} onClick={() => setGroup('')} />
            {m.groups.map((g) => (
              <Chip key={g} label={t(g)} tone={groupTone(g)} active={group === g} onClick={() => setGroup(group === g ? '' : g)} />
            ))}
          </span>
        </div>
        <CoverageRibbon scans={m.scans} onPick={(s) => setDrawer({ lens: 'scans', id: s.id })} />
      </section>

      <div className="flex flex-col gap-6 min-w-0">
        {visible.map((r) => {
          const head = r.date !== lastDate
          lastDate = r.date
          return (
            <div key={r.key} className="flex flex-col gap-4 min-w-0">
              {head && (
                <div className="flex items-center gap-8 pt-6">
                  <span className="text-11 font-mono text-tertiary">{fmtDate(r.date)}</span>
                  <span className="flex-1 border-t border-border-subtle" />
                </div>
              )}
              {r.kind === 'loose' ? (
                <LooseCard changes={r.changes.filter(keep)} />
              ) : (
                <ScanCard s={r.scan} keep={keep} filtering={Boolean(group)} onOpen={() => setDrawer({ lens: 'scans', id: r.scan.id })} />
              )}
            </div>
          )
        })}
        {visible.length === 0 && <p className="text-12 text-tertiary italic">{t('Nothing matches those filters.')}</p>}
      </div>

      {drawer && LENSES[drawer.lens] && (
        <LensDrawer lens={LENSES[drawer.lens]!} id={drawer.id} presentation="reading" onClose={() => setDrawer(null)} />
      )}
    </div>
  )
}

function ScanCard({ s, keep, filtering, onOpen }: { s: ScanAnswer; keep: (c: Change) => boolean; filtering: boolean; onOpen: () => void }) {
  const rows = s.changes.filter(keep)
  if (!s.answered) {
    return (
      <div className="flex items-baseline gap-8 flex-wrap min-w-0 px-14 py-4 rounded-input border border-dashed border-border-subtle opacity-70">
        <span className="text-10 font-mono text-tertiary">{s.time}</span>
        <span className="text-11 text-tertiary truncate min-w-0">{s.l1}</span>
        <span className="ml-auto text-10 font-mono" style={{ color: 'var(--status-amber)' }}>{t('no answer')}</span>
      </div>
    )
  }
  return (
    <section className="rounded-card border border-border-subtle bg-surface px-14 py-10 flex flex-col gap-6 min-w-0">
      <div className="flex items-baseline gap-8 flex-wrap min-w-0">
        <span className="text-10 font-mono text-tertiary">{s.time}</span>
        <span className="text-10 font-mono text-tertiary">{s.agent_id}</span>
        <button type="button" onClick={onOpen} className="text-12 text-primary text-left min-w-0 hover:underline decoration-border-subtle">
          {s.l1}
        </button>
        <span className="ml-auto text-10 font-mono text-tertiary">{s.id}</span>
      </div>
      <ul className="flex flex-col">
        {rows.map((c) => <li key={c.id}><ChangeLine c={c} /></li>)}
      </ul>
      {!filtering && s.checked.length > 0 && (
        <div className="text-10 font-mono text-tertiary">{t('checked, no change:')} {s.checked.map((g) => t(g)).join(' · ')}</div>
      )}
    </section>
  )
}

function LooseCard({ changes }: { changes: Change[] }) {
  if (changes.length === 0) return null
  return (
    <section className="rounded-card border border-border-subtle bg-surface px-14 py-10 flex flex-col gap-6 min-w-0">
      <div className="flex items-baseline gap-8">
        <span className="text-10 font-mono text-tertiary uppercase tracking-wide">{t('without a scan')}</span>
        <span className="text-10 font-mono text-tertiary">{changes.length}</span>
      </div>
      <ul className="flex flex-col">
        {changes.map((c) => (
          <li key={c.id} className="flex items-baseline gap-8 flex-wrap min-w-0 py-2">
            <OpMark op={c.op} />
            <TypeChip type={c.type} group={c.group} />
            <span className={`text-12 text-primary ${c.op === 'remove' ? 'line-through opacity-70' : ''}`}>{c.name}</span>
            {c.note && <span className="text-11 text-secondary min-w-0 truncate">— {c.note}</span>}
            <span className="ml-auto"><PathBits paths={c.path} limit={1} /></span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Chip({ label, active, onClick, tone }: { label: string; active: boolean; onClick: () => void; tone?: string }) {
  return <FilterPill on={active} onClick={onClick} dot={tone}>{label}</FilterPill>
}

// ---------------------------------------------------------------------------
// codebase
// ---------------------------------------------------------------------------

interface Line { node: PathNode; depth: number }

function flatten(node: PathNode, open: Set<string>, depth = 0, out: Line[] = []): Line[] {
  for (const child of node.children) {
    out.push({ node: child, depth })
    if (child.children.length > 0 && open.has(child.path)) flatten(child, open, depth + 1, out)
  }
  return out
}

/** Every folder down to `depth`, so the tree opens on something useful. */
function initialOpen(node: PathNode, depth = 0, acc = new Set<string>()): Set<string> {
  for (const child of node.children) {
    if (child.children.length === 0) continue
    if (depth < 2) acc.add(child.path)
    initialOpen(child, depth + 1, acc)
  }
  return acc
}

function CodebaseView({ m }: { m: Model }) {
  const [open, setOpen] = useState<Set<string>>(() => initialOpen(m.tree))
  const [picked, setPicked] = useState<string>('')
  const lines = useMemo(() => flatten(m.tree, open), [m.tree, open])
  const byPath = useMemo(() => {
    const map = new Map<string, PathNode>()
    const walk = (n: PathNode) => { if (n.path) map.set(n.path, n); n.children.forEach(walk) }
    walk(m.tree)
    return map
  }, [m.tree])
  const current = byPath.get(picked) ?? null
  const homeless = m.entities.filter((e) => e.paths.length === 0)

  const toggle = (path: string) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path); else next.add(path)
      return next
    })

  return (
    <div className="grid gap-16 min-w-0" style={{ gridTemplateColumns: 'minmax(0, 1fr) minmax(240px, 340px)' }}>
      <div className="flex flex-col gap-8 min-w-0">
        <div className="flex items-baseline gap-8 flex-wrap border-b border-border-subtle pb-6">
          <span className="text-10 font-mono text-tertiary">
            {t('Only paths named in architecture answers, not the whole repo')}
          </span>
          <span className="ml-auto inline-flex items-center gap-6 flex-wrap">
            <button type="button" onClick={() => setOpen(new Set(byPath.keys()))} className="text-10 font-mono text-tertiary hover:text-primary">{t('expand all')}</button>
            <span className="text-10 font-mono text-tertiary" aria-hidden>·</span>
            <button type="button" onClick={() => setOpen(new Set())} className="text-10 font-mono text-tertiary hover:text-primary">{t('collapse')}</button>
          </span>
        </div>

        {lines.length === 0 && <p className="text-12 text-tertiary italic">{t('No path has been declared yet.')}</p>}
        <ul className="flex flex-col">
          {lines.map(({ node, depth }) => {
            const isOpen = open.has(node.path)
            const dir = node.children.length > 0
            return (
              <li key={node.path}>
                <div
                  className={`flex items-center gap-6 rounded-input px-6 py-3 min-w-0 ${picked === node.path ? 'bg-brand-glow' : 'hover:bg-hover'}`}
                  style={{ paddingLeft: 6 + depth * 14 }}
                >
                  <button
                    type="button"
                    onClick={() => (dir ? toggle(node.path) : setPicked(node.path))}
                    className="text-tertiary hover:text-primary shrink-0"
                    aria-label={dir ? (isOpen ? t('Collapse') : t('Expand')) : t('Select')}
                    aria-expanded={dir ? isOpen : undefined}
                  >
                    {dir
                      ? (isOpen ? <ChevronDown size={12} aria-hidden /> : <ChevronRight size={12} aria-hidden />)
                      : <span className="inline-block w-12" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => setPicked(picked === node.path ? '' : node.path)}
                    className="flex items-center gap-6 min-w-0 flex-1 text-left"
                  >
                    {node.kind === 'dir'
                      ? <Folder size={12} className="text-tertiary shrink-0" aria-hidden />
                      : <File size={12} className="text-tertiary shrink-0" aria-hidden />}
                    <span className={`text-12 truncate ${node.entities.length > 0 ? 'text-primary' : 'text-secondary'}`}>{node.name}</span>
                    {node.symbols.length > 0 && (
                      <span className="text-10 font-mono text-brand truncate shrink-0">:{node.symbols.join(' :')}</span>
                    )}
                  </button>
                  <GroupBar groups={node.groups} />
                  <span className="text-10 font-mono text-tertiary tabular-nums w-16 text-right shrink-0">{node.total || ''}</span>
                </div>
              </li>
            )
          })}
        </ul>

        {homeless.length > 0 && (
          <section className="flex flex-col gap-4 pt-8 border-t border-border-subtle">
            <h3 className="text-10 font-mono uppercase tracking-wide text-tertiary">{t('no path')} — {homeless.length}</h3>
            <ul className="flex flex-col gap-2">
              {homeless.map((e) => (
                <li key={e.key} className="flex items-baseline gap-8 min-w-0">
                  <TypeChip type={e.type} group={e.group} />
                  <span className={`text-12 text-primary truncate ${e.gone ? 'line-through opacity-70' : ''}`}>{e.name}</span>
                  {e.note && <span className="text-11 text-secondary truncate min-w-0">— {e.note}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <aside className="self-start sticky top-16 flex flex-col gap-10 min-w-0">
        {current ? (
          <>
            <header className="flex flex-col gap-2">
              <span className="text-10 font-mono text-tertiary">{current.kind === 'dir' ? t('folder') : t('file')}</span>
              <h3 className="text-13 font-mono text-primary break-all">{current.path}</h3>
              <span className="text-10 font-mono text-tertiary">
                {tn(current.total, '{n} thing at or under it', '{n} things at or under it')}
              </span>
            </header>
            {current.symbols.length > 0 && (
              <div className="text-11 font-mono text-secondary">
                {t('symbols:')} {current.symbols.map((s) => <span key={s} className="text-brand">:{s} </span>)}
              </div>
            )}
            {current.entities.length === 0 ? (
              <p className="text-12 text-tertiary italic">{t('No entry names this path. Open a file or folder inside it.')}</p>
            ) : (
              <ul className="flex flex-col divide-y divide-border-subtle">
                {current.entities.map((e) => (
                  <li key={e.key} className="py-8 flex flex-col gap-2 min-w-0">
                    <div className="flex items-baseline gap-6 flex-wrap">
                      <TypeChip type={e.type} group={e.group} />
                      <span className={`text-12 text-primary ${e.gone ? 'line-through opacity-70' : ''}`}>{e.name}</span>
                    </div>
                    {e.note && <p className="text-11 text-secondary">{e.note}</p>}
                    <div className="flex items-baseline gap-6 flex-wrap">
                      {[...e.changes].reverse().slice(0, 3).map((c) => (
                        <span key={c.id} className="text-10 font-mono text-tertiary inline-flex items-baseline gap-2">
                          <OpMark op={c.op} size={10} />{fmtDate(c.created_date)}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="text-12 text-tertiary italic">{t('Pick a file or a folder to see what claims it.')}</p>
        )}
      </aside>
    </div>
  )
}

/** The groups present under a node, as one stacked bar. */
function GroupBar({ groups }: { groups: Record<string, number> }) {
  const entries = Object.entries(groups).filter(([, n]) => n > 0)
  const total = entries.reduce((n, [, v]) => n + v, 0)
  if (total === 0) return <span className="w-48 shrink-0" />
  return (
    <span className="w-48 h-6 rounded-pill overflow-hidden inline-flex shrink-0" title={entries.map(([g, n]) => `${g} ${n}`).join(' · ')}>
      {entries.map(([g, n]) => (
        <span key={g} style={{ background: groupTone(g), width: `${(n / total) * 100}%` }} />
      ))}
    </span>
  )
}
