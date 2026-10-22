import { absolutePath, useFolder } from '../../lib/paths'
import { ProjectPills } from '../../components/ProjectPills'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { useHashState } from '../../hooks/useHashState'
import { api, qk } from '../../lib/api'
import { persistPref } from '../../lib/uiPrefs'
import { type Change, type Model, type ScanAnswer, OP_GLYPH, OP_TONE, fmtDate, groupTone, splitSymbol, useLedgers } from './ledger'
import { t, tn } from '../../i18n/scope/system'

/**
 * What the ledger-driven architecture pages share.
 *
 * `ArchPage` is the frame: the title, the project the page is reading
 * (in the URL, so a link keeps it), the switch between compositions, and
 * the three states a ledger can be in — loading, unreadable, or empty
 * because no agent has answered the form yet. Everything below it is the
 * vocabulary of the ledger rendered once: an op, a type, a path, a
 * change, a scan tick.
 */

/**
 * The project a ledger page is reading: the URL wins, else the project
 * that actually has a ledger. The picker says how many changes each one
 * holds, so an empty project is visibly empty before it is opened.
 */
export function useLedgerProject() {
  const [params] = useSearchParams()
  const [hash, setHash] = useHashState()
  const snapshot = useQuery({ queryKey: qk.snapshot(), queryFn: ({ signal }) => api.snapshot(signal) })
  const codes = useMemo(() => (snapshot.data?.projects ?? []).map((p) => p.code), [snapshot.data])
  const { models, busiest, loading, error } = useLedgers(codes)
  // `#project=` is the house convention. `?project=` is still read so the
  // links written before it stay good.
  const project = hash.project || params.get('project') || busiest || codes[0] || ''
  return {
    codes,
    project,
    setProject: (c: string) => setHash({ project: c }),
    model: models.get(project) ?? null,
    models,
    loading: snapshot.isLoading || loading,
    error,
  }
}

export function ProjectPicker({
  codes, project, models, onPick,
}: {
  codes: string[]
  project: string
  models: Map<string, Model>
  onPick: (c: string) => void
}) {
  if (codes.length < 2) return null
  return (
    <ProjectPills label={false} dots value={project} onPick={(c) => c && onPick(c)}
      projects={codes.map((c) => {
        const n = models.get(c)?.totalChanges ?? 0
        return { code: c, count: n, dim: !n, hint: n ? tn(n, '{n} change', '{n} changes') : t('no architecture answers yet') }
      })} />
  )
}

/** The op, as its glyph in its tone — never colour alone. */
export function OpMark({ op, size = 12 }: { op: string; size?: number }) {
  return (
    <span
      className="font-mono inline-block text-center shrink-0"
      style={{ color: OP_TONE[op] ?? 'var(--text-secondary)', width: size, fontSize: size }}
      title={op}
      aria-label={op}
    >
      {OP_GLYPH[op] ?? '·'}
    </span>
  )
}

/** A type, with its group's colour as a dot beside the word. */
export function TypeChip({ type, group, dim }: { type: string; group: string; dim?: boolean }) {
  return (
    <span className={`text-10 font-mono inline-flex items-center gap-4 shrink-0 ${dim ? 'text-tertiary' : 'text-secondary'}`}>
      <span className="w-6 h-6 rounded-pill shrink-0" style={{ background: groupTone(group) }} aria-hidden />
      {t(type)}
    </span>
  )
}

/** Repo anchors: the file, and the symbol it named, if it named one. */
export function PathBits({ paths, limit = 3 }: { paths: string[]; limit?: number }) {
  const folder = useFolder()
  if (paths.length === 0) return <span className="text-10 font-mono text-tertiary italic">{t('no path')}</span>
  const shown = paths.slice(0, limit)
  return (
    <span className="inline-flex items-center gap-8 flex-wrap min-w-0">
      {shown.map((p) => {
        const [file, symbol] = splitSymbol(p)
        return (
          <span key={p} className="text-10 font-mono text-tertiary truncate max-w-full" title={absolutePath(folder, p)}>
            {file}
            {symbol && <span className="text-brand">:{symbol}</span>}
          </span>
        )
      })}
      {paths.length > shown.length && <span className="text-10 font-mono text-tertiary">+{paths.length - shown.length}</span>}
    </span>
  )
}

/** One change, as the stream and the histories draw it. */
export function ChangeLine({
  c,
  onOpen,
  showDate,
}: {
  c: Change
  onOpen?: (c: Change) => void
  showDate?: boolean
}) {
  const inner = (
    <>
      <OpMark op={c.op} />
      <TypeChip type={c.type} group={c.group} />
      <span className={`text-12 text-primary min-w-0 ${c.op === 'remove' ? 'line-through opacity-70' : ''}`}>{c.name}</span>
      {c.note && <span className="text-11 text-secondary min-w-0 truncate">— {c.note}</span>}
      {c.task && <span className="text-10 font-mono text-brand shrink-0">{c.task}</span>}
      <span className="ml-auto inline-flex items-center gap-8 shrink-0">
        {showDate && <span className="text-10 font-mono text-tertiary">{fmtDate(c.created_date)}</span>}
        <PathBits paths={c.path} limit={1} />
      </span>
    </>
  )
  if (!onOpen) return <div className="flex items-baseline gap-8 flex-wrap min-w-0 py-2">{inner}</div>
  return (
    <button
      type="button"
      onClick={() => onOpen(c)}
      className="flex items-baseline gap-8 flex-wrap min-w-0 py-2 w-full text-left rounded-input px-6 -mx-6 hover:bg-hover"
    >
      {inner}
    </button>
  )
}

/** One tick per scan: filled when it was answered, hollow when it was not. */
export function CoverageRibbon({ scans, onPick }: { scans: ScanAnswer[]; onPick?: (s: ScanAnswer) => void }) {
  const oldestFirst = [...scans].reverse()
  return (
    <div
      className="flex items-end gap-2 flex-wrap pb-4"
      style={{ borderBottom: '1px solid var(--border-subtle)' }}
      aria-label={t('Scans, oldest first. Filled: the form is answered.')}
    >
      {oldestFirst.map((s) => {
        const n = s.changes.length
        const h = s.answered ? Math.min(24, 8 + n * 3) : 6
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onPick?.(s)}
            title={`${s.date} ${s.time} · ${s.agent_id} · ${s.answered ? tn(n, '{n} change', '{n} changes') : t('no answer')}\n${s.l1}`}
            className="w-6 rounded-input shrink-0"
            style={{
              height: h,
              background: s.answered ? 'var(--brand)' : 'transparent',
              border: s.answered ? 'none' : '1px solid var(--border-default)',
            }}
          />
        )
      })}
    </div>
  )
}

const DISMISSED_KEY = 'sp-owes-dismissed'
/** From here up the strip speaks in one sentence instead of a list. */
const OWES_SUMMARY_AT = 3
/** Ids kept, oldest dropped — a paid debt never comes back, so this only grows slowly. */
const DISMISSED_MAX = 200


/** "3 debts and 1 action" — actions first, and only what is actually there. */
export function owesSummary(rows: Change[]): string {
  const actions = rows.filter((r) => r.type === 'action-needed').length
  const debts = rows.length - actions
  const parts = [
    ...(actions ? [tn(actions, '{n} action', '{n} actions')] : []),
    ...(debts ? [tn(debts, '{n} debt', '{n} debts')] : []),
  ]
  return parts.join(t(' and '))
}

function readDismissed(): string[] {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

/**
 * Standing debt and operator actions.
 *
 * It is amber because it is owed, but it is not a wall. One or two
 * items are simply listed. From three the strip says it in a sentence —
 * "You have 2 actions and 4 debts standing." — and opens to the list on
 * a word, so a pile of debt costs one line until it is asked for. An
 * item can be put away with its own ×, all of them with the one in the
 * header. Dismissal is per item and remembered across browsers, so a
 * debt already read stays quiet while a *new* one, an id nobody has
 * dismissed, brings the strip back at full volume. Nothing is ever
 * lost: what was put away is one "show" away, and the items are still
 * in the register under `owes`.
 */
export function OwesStrip({ rows }: { rows: Change[] }) {
  const [dismissed, setDismissed] = useState<string[]>(readDismissed)
  const [showDismissed, setShowDismissed] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const put = (ids: string[]) => {
    const next = [...dismissed.filter((id) => !ids.includes(id)), ...ids].slice(-DISMISSED_MAX)
    setDismissed(next)
    persistPref(DISMISSED_KEY, JSON.stringify(next))
  }
  const restore = () => { setShowDismissed(true); setExpanded(true) }

  // Actions before debts: an action-needed blocks the operator, a debt waits.
  const ordered = [...rows].sort((a, b) =>
    (a.type === b.type ? 0 : a.type === 'action-needed' ? -1 : 1))
  const open = ordered.filter((r) => !dismissed.includes(r.id))
  const hidden = ordered.length - open.length

  if (rows.length === 0) return null

  if (open.length === 0 && !showDismissed) {
    return (
      <button
        type="button"
        onClick={restore}
        className="self-start text-10 font-mono text-tertiary hover:text-primary inline-flex items-center gap-6"
      >
        <span className="w-6 h-6 rounded-pill shrink-0" style={{ background: 'var(--status-amber)', opacity: 0.5 }} aria-hidden />
        {tn(ordered.length, '{n} item dismissed', '{n} items dismissed')} · {t('show')}
      </button>
    )
  }

  const list = showDismissed ? ordered : open
  // Three or more is a pile: say it in a sentence until it is asked for.
  const folded = list.length >= OWES_SUMMARY_AT && !expanded

  const putAll = (
    <button
      type="button"
      onClick={() => { put(open.map((r) => r.id)); setShowDismissed(false); setExpanded(false) }}
      title={t('Dismiss all; the strip shows again when a new item arrives')}
      className="text-11 font-mono text-tertiary hover:text-primary leading-none shrink-0"
      aria-label={t('Dismiss all')}
    >
      ×
    </button>
  )

  if (folded) {
    return (
      <section
        className="rounded-card border px-14 py-10 flex items-baseline gap-8 flex-wrap"
        style={{ borderColor: 'var(--status-amber)', background: 'color-mix(in srgb, var(--status-amber) 7%, transparent)' }}
      >
        <span className="w-6 h-6 rounded-pill shrink-0" style={{ background: 'var(--status-amber)' }} aria-hidden />
        <span className="text-12 text-primary">{t('You have {what} standing.', { what: owesSummary(list) })}</span>
        <button type="button" onClick={() => setExpanded(true)} className="text-10 font-mono text-tertiary hover:text-primary">
          {t('show')}
        </button>
        {hidden > 0 && !showDismissed && (
          <button type="button" onClick={restore} className="text-10 font-mono text-tertiary hover:text-primary">
            {t('{n} dismissed', { n: hidden })} · {t('show')}
          </button>
        )}
        <span className="ml-auto">{putAll}</span>
      </section>
    )
  }

  return (
    <section
      className="rounded-card border px-14 py-10 flex flex-col gap-6"
      style={{ borderColor: 'var(--status-amber)', background: 'color-mix(in srgb, var(--status-amber) 7%, transparent)' }}
    >
      <div className="flex items-baseline gap-8">
        <span className="text-10 font-mono uppercase" style={{ color: 'var(--status-amber)' }}>
          {t('standing — debt & actions')} · {list.length}
        </span>
        {list.length >= OWES_SUMMARY_AT && (
          <button type="button" onClick={() => setExpanded(false)} className="text-10 font-mono text-tertiary hover:text-primary">
            {t('fold')}
          </button>
        )}
        <span className="ml-auto">{putAll}</span>
      </div>
      <ul className="flex flex-col gap-4">
        {list.map((r) => {
          const away = dismissed.includes(r.id)
          return (
            <li key={r.id} className={`text-12 flex items-baseline gap-8 flex-wrap ${away ? 'opacity-50' : ''}`}>
              <TypeChip type={r.type} group={r.group} />
              <span className="text-primary">{r.name}</span>
              {(r.fields.risk || r.fields.action) && (
                <span className="text-11 text-secondary">— {r.fields.risk || r.fields.action}</span>
              )}
              <span className="ml-auto inline-flex items-baseline gap-8 shrink-0">
                <span className="text-10 font-mono text-tertiary">{fmtDate(r.created_date)} · {r.agent_id}</span>
                <button
                  type="button"
                  onClick={() => put([r.id])}
                  title={t('Dismiss')}
                  aria-label={t('Dismiss: {name}', { name: r.name })}
                  className="text-11 font-mono text-tertiary hover:text-primary leading-none"
                >
                  ×
                </button>
              </span>
            </li>
          )
        })}
      </ul>
      <div className="flex items-baseline gap-10 flex-wrap">
        {hidden > 0 && !showDismissed && (
          <button type="button" onClick={restore} className="text-10 font-mono text-tertiary hover:text-primary">
            {t('{n} dismissed', { n: hidden })} · {t('show')}
          </button>
        )}
        {showDismissed && hidden > 0 && (
          <button type="button" onClick={() => { setShowDismissed(false); setExpanded(false) }} className="text-10 font-mono text-tertiary hover:text-primary">
            {t('hide dismissed')}
          </button>
        )}
      </div>
    </section>
  )
}
