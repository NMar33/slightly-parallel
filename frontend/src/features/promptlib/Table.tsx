import { copyText } from '../../lib/useCopy'
import { TH, TH_BUTTON } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { useEffect, useMemo, useState } from 'react'
import { PROMPTS_GUIDE } from '../../features/visions/guides'
import { PageGuide } from '../../features/visions/parts'
import { Archive, ArchiveRestore, ArrowDown, ArrowUp, Copy, MessagesSquare } from 'lucide-react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { Input } from '../../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { useHashState } from '../../hooks/useHashState'
import { LABEL, PillGroup, RunChips } from './taskstyle'
import { ageOf, matches, tagList, useLibrary, useLibraryWrites, type PromptRow } from './data'
import {
  DaysOfSends, NoticedRow, pulse, useDismissed, useOverview,
} from './overview'
import { usePrompt } from './data'
import { Compare } from './ComparePage'
import { t, tn } from '../../i18n/scope/system'
import { isTypingTarget } from '../../lib/typing'

/**
 * Prompt library v07 — the table, a row opening into the whole prompt.
 *
 * v06 with the pane replaced: a row opens into the prompt's page itself —
 * A and B, the judgement rows, the diff — and, folded under it, the chats:
 * every session the prompt was sent in, the turn that carried it, what it
 * changed. Nothing to navigate to; compare and judge in the table, unfold
 * the chats when the evidence is wanted. The page route stays for a link.
 */
type Col = 'name' | 'project' | 'version' | 'task' | 'score' | 'sends' | 'made' | 'last' | 'pulse'

const COLS: Array<{ key: Col; label: string; right?: boolean; w?: string }> = [
  { key: 'pulse', label: '', w: '20px' },
  { key: 'name', label: t('prompt') },
  { key: 'project', label: t('project'), w: '120px' },
  { key: 'version', label: 'v', right: true, w: '44px' },
  { key: 'task', label: t('task'), w: '96px' },
  { key: 'score', label: t('score'), right: true, w: '64px' },
  { key: 'sends', label: t('sends'), right: true, w: '64px' },
  { key: 'made', label: t('made'), w: '140px' },
  { key: 'last', label: t('last sent'), right: true, w: '96px' },
]

const ORDER = { today: 0, week: 1, quiet: 2, never: 3 }

function valueOf(r: PromptRow, k: Col): number | string {
  switch (k) {
    case 'name': return (r.title ?? '').toLowerCase()
    case 'project': return (r.project ?? '').toLowerCase()
    case 'version': return r.current_version ?? r.versions_n
    case 'task': return r.current_rating?.task_success ?? ''
    case 'score': return r.current_rating?.score ?? -1
    case 'sends': return r.metrics.uses
    case 'made': return (r.made?.commits ?? 0) * 1000 + (r.made?.files ?? 0) + (r.made?.tasks ?? 0)
    case 'last': return r.metrics.last_used || ''
    case 'pulse': return ORDER[pulse(r)]
  }
}

export function PromptsTable() {
  useEffect(() => { document.title = `${t('Prompts')} — Slightly Parallel` }, [])
  const [hash, setHash] = useHashState()
  const { library, candidates, rows: kept, byDay, range, totals } = useOverview()
  const archived = useLibrary('archived')
  const { keep, update } = useLibraryWrites()
  const status = hash.status === 'archived' ? 'archived' : 'active'
  const rows = useMemo(
    () => status === 'archived' ? (archived.data?.prompts ?? []) : kept,
    [status, archived.data, kept],
  )
  const { dismissed, dismiss } = useDismissed()
  const [sort, setSort] = useState<Col>('last')
  const [desc, setDesc] = useState(true)
  const [open, setOpen] = useState<string | null>(hash.sel ?? null)
  const q = (hash.q ?? '').trim()
  const project = hash.project ?? ''

  // A prompt belongs to the project it was harvested in, and to every
  // project it was later sent in — the chips narrow by either.
  const projectsOf = (r: PromptRow) => [...new Set([r.project, ...(r.metrics.projects ?? [])].filter(Boolean))]
  const projects = useMemo(() => {
    const n = new Map<string, number>()
    for (const r of rows) for (const pj of projectsOf(r)) n.set(pj, (n.get(pj) ?? 0) + 1)
    return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [rows])

  const shown = useMemo(() => {
    const out = rows.filter((r) => matches(r, q) && (!project || projectsOf(r).includes(project))).sort((a, b) => {
      const av = valueOf(a, sort), bv = valueOf(b, sort)
      return av === bv ? 0 : av < bv ? -1 : 1
    })
    return desc ? out.reverse() : out
  }, [rows, q, project, sort, desc])
  const offers = (candidates.data?.candidates ?? []).filter((c) => !dismissed.includes(c.cluster))

  // Keys: j/k walk the rows, Enter opens in place, c copies, o goes to the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // A chord is the browser's: Ctrl+C copies the selection, not the open prompt.
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (isTypingTarget(e)) return
      const i = Math.max(0, shown.findIndex((r) => r.id === open))
      const at = shown[i]
      if (e.key === 'j' || e.key === 'k') {
        const next = shown[Math.min(shown.length - 1, Math.max(0, i + (e.key === 'j' ? 1 : -1)))]
        if (next) setOpen(next.id)
      } else if (e.key === 'c' && at) {
        void copyText(at.preview)
      } else if (e.key === 'o' && at) {
        window.location.assign(`/prompts/${at.id}`)
      } else if (e.key === 'Enter' && at) {
        // Enter on a focused link or button is that control's own press.
        if ((e.target as HTMLElement | null)?.closest?.('a, button, [role=button]')) return
        setOpen(open === at.id ? null : at.id)
      } else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [shown, open])

  const head = (k: Col) => () => {
    if (sort === k) setDesc((d) => !d)
    else { setSort(k); setDesc(k !== 'name') }
  }

  return (
    <div className="flex flex-col gap-12">
      <PageHeader
        variant="lens" icon={MessagesSquare} title={t('Prompts')}
        actions={
          <Input value={hash.q ?? ''} onChange={(e) => setHash({ q: e.target.value })} placeholder={t('Find across prompts')} aria-label={t('Find across prompts')} className="w-[240px] h-24 text-12" />
        }
      >
        <span className={LABEL}>{t('project')}</span>
        {projects.map(([pj, n]) => (
          <button key={pj} type="button" onClick={() => setHash({ project: project === pj ? '' : pj })}
            className={`text-11 font-mono px-8 h-20 inline-flex items-center rounded-pill border ${project === pj ? 'border-brand text-brand bg-brand-glow' : 'border-border-subtle text-secondary hover:text-primary'}`}>
            {pj} <span className="opacity-60 ml-4">{n}</span>
          </button>
        ))}
      </PageHeader>
      <PageGuide id="prompts" guide={PROMPTS_GUIDE} examples={0} />
      <div className="flex items-end gap-12 flex-wrap">
        <DaysOfSends byDay={byDay} range={range} />
        <PillGroup label={t('show')} value={status} onChange={(v) => setHash({ status: v === 'archived' ? 'archived' : '' })}
          options={[['active', t('kept {n}', { n: kept.length })], ['archived', t('archived {n}', { n: archived.data?.prompts.length ?? 0 })]]} />
        <div className="text-11 font-mono text-tertiary tabular whitespace-nowrap">
          {shown.length}{project ? ` ${t('of {n}', { n: rows.length })}` : ''} {t('prompts · {sends} sends · {judged} judged', { sends: totals.sends, judged: totals.judged })}
        </div>
        <span className="ml-auto text-10 font-mono text-tertiary/70">{t('j k move · enter opens · c copies · o the page')}</span>
      </div>

      {offers.length > 0 && (
        <div className="grid gap-8" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))' }}>
          {offers.map((c) => (
            <NoticedRow key={c.cluster} c={c} busy={keep.isPending}
              onKeep={() => keep.mutate(c.cluster, { onSuccess: (d) => { setOpen(d?.prompt?.id ?? null); toast.success(t('Added to the prompt library.')) } })}
              onDismiss={() => dismiss(c.cluster)} />
          ))}
        </div>
      )}

      {library.isLoading && <LoadingSkeleton variant="row" count={5} />}
      {library.isError && <ErrorBanner title={t('Could not read the library')} hideDismiss />}

      {library.data && (
        <div className="rounded-card border border-border-subtle bg-surface overflow-x-auto">
          {/* The name keeps at least 220px: below that the table scrolls sideways instead of cutting it. */}
          <table className="w-full table-fixed text-12 font-mono border-collapse" style={{ minWidth: 1040 }}>
            <thead>
              <tr className={`border-b border-border-subtle ${TH}`}>
                {COLS.map((c) => (
                  <th key={c.key} style={{ width: c.w }} className={`px-8 py-6 ${c.right ? 'text-right' : 'text-left'}`}>
                    {c.label && (
                      <button type="button" onClick={head(c.key)} className={`inline-flex items-center gap-4 whitespace-nowrap ${TH_BUTTON}`} aria-label={t('sort by {col}', { col: c.label })}>
                        {c.label}{sort === c.key && (desc ? <ArrowDown size={10} /> : <ArrowUp size={10} />)}
                      </button>
                    )}
                  </th>
                ))}
                <th style={{ width: '120px' }} className="px-8 py-6 text-left">{t('tags')}</th>
                <th style={{ width: '56px' }} />
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const p = pulse(r)
                const on = open === r.id
                return (
                  <FragmentRow key={r.id} on={on}>
                    <tr className={`border-b border-border-subtle cursor-pointer ${on ? 'bg-brand-glow' : 'hover:bg-hover'}`} onClick={() => setOpen(on ? null : r.id)}>
                      <td className="px-8 py-6"><span className={`inline-block h-6 w-6 rounded-pill ${p === 'today' ? 'bg-status-green' : p === 'week' ? 'bg-brand' : p === 'quiet' ? 'bg-status-amber' : 'bg-border-strong'}`} title={p} /></td>
                      <td className="px-8 py-6 text-primary font-sans truncate">{r.title}</td>
                      <td className="px-8 py-6">
                        <span className="inline-flex items-center gap-4 flex-wrap">
                          {r.project && <span className="px-4 py-1 rounded-input bg-elevated text-secondary">{r.project}</span>}
                          {(r.metrics.projects ?? []).filter((pj) => pj !== r.project).map((pj) => (
                            <span key={pj} className="px-4 py-1 rounded-input bg-brand/16 text-brand" title={t('also sent here')}>{pj}</span>
                          ))}
                          {!r.project && !(r.metrics.projects ?? []).length && <span className="text-tertiary/60">—</span>}
                        </span>
                      </td>
                      <td className="px-8 py-6 text-right text-tertiary tabular">v{r.current_version ?? r.versions_n}</td>
                      <td className="px-8 py-6">{r.current_rating?.task_success ? <RunChips rating={{ ...r.current_rating, regression: '', intervention: '', score: null }} /> : <span className="text-tertiary/60">—</span>}</td>
                      <td className="px-8 py-6 text-right tabular">{r.current_rating?.score != null ? <span className="text-brand">{r.current_rating.score}/10</span> : <span className="text-tertiary/60">—</span>}</td>
                      <td className="px-8 py-6 text-right tabular text-secondary">{r.metrics.uses || <span className="text-tertiary/60">—</span>}</td>
                      <td className="px-8 py-6 text-tertiary tabular truncate" title={t('commits · files · tasks, over the chats it was sent in')}>
                        {r.made && (r.made.commits || r.made.tasks)
                          ? [r.made.commits ? tn(r.made.commits, '{n} commit', '{n} commits') : '', r.made.files ? t('{n} files', { n: r.made.files }) : '', r.made.tasks ? tn(r.made.tasks, '{n} task', '{n} tasks') : ''].filter(Boolean).join(' · ')
                          : <span className="text-tertiary/60">—</span>}
                      </td>
                      <td className="px-8 py-6 text-right tabular text-tertiary whitespace-nowrap">{r.metrics.last_used ? ageOf(r.metrics.last_used) : '—'}</td>
                      <td className="px-8 py-6 text-tertiary truncate" style={{ width: '160px' }}>{tagList(r).join(', ')}</td>
                      <td className="px-4 py-6 text-right whitespace-nowrap">
                        <button type="button" title={t('copy the current wording')} aria-label={t('copy {name}', { name: r.title })} className="text-tertiary hover:text-brand px-4"
                          onClick={(e) => { e.stopPropagation(); void copyText(r.preview) }}>
                          <Copy size={12} />
                        </button>
                        <button type="button" title={status === 'archived' ? t('restore') : t('archive')} aria-label={`${status === 'archived' ? t('restore') : t('archive')} ${r.title}`} className="text-tertiary hover:text-primary px-4"
                          onClick={(e) => { e.stopPropagation(); update.mutate({ id: r.id, status: status === 'archived' ? 'active' : 'archived' }, { onSuccess: () => toast.success(status === 'archived' ? t('Restored') : t('Archived')) }) }}>
                          {status === 'archived' ? <ArchiveRestore size={12} /> : <Archive size={12} />}
                        </button>
                      </td>
                    </tr>
                    {on && (
                      <tr className="border-b border-border-subtle bg-base">
                        <td colSpan={11} className="px-12 py-10"><div className="min-w-0 max-w-full overflow-hidden"><OpenPrompt id={r.id} /></div></td>
                      </tr>
                    )}
                  </FragmentRow>
                )
              })}
            </tbody>
          </table>
          {shown.length === 0 && <p className="px-12 py-8 text-11 font-mono text-tertiary">{t('nothing matches')}</p>}
        </div>
      )}
      <p className="text-10 font-mono text-tertiary">
        {t('Click a row to compare versions, rate them and see the chats.')}
      </p>
    </div>
  )
}

function FragmentRow({ children }: { children: React.ReactNode; on: boolean }) {
  return <>{children}</>
}

/** The prompt's page, inside the row: compare, judge, and the chats folded. */
function OpenPrompt({ id }: { id: string }) {
  const detail = usePrompt(id)
  if (detail.isLoading || !detail.data) return <p className="text-11 font-mono text-tertiary">{t('reading…')}</p>
  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-baseline gap-8">
        <span className="text-14 font-medium text-primary font-sans">{detail.data.prompt.title}</span>
        <Link to={`/prompts/${id}`} className="text-10 font-mono text-brand hover:underline">{t('the page →')}</Link>
      </div>
      <Compare detail={detail.data} head={false} chats="collapsed" />
    </div>
  )
}
