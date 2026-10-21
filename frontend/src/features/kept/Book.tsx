/**
 * The page every kept kind reads as — Visions, Rules, Problems: the
 * entries of one kind as a book of chapters (by tag, project, month, set,
 * or a page's own grouping), the contents down the left following the
 * section being read, the sets (and projects) down the right, and each
 * entry a section with its versions, tags, the words it was kept from and
 * the chat around them.
 *
 * `KeptBook` owns everything the three pages share; a page passes what is
 * its own through slots — a strip under the header, controls beside
 * "group by", a mark in the contents, the parts of a section.
 */

import { copyText as copy } from '../../lib/useCopy'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Copy, GripVertical, Pencil, type LucideIcon } from 'lucide-react'

import { AgentName } from '../../components/AgentName'
import { PageHeader } from '../../components/PageHeader'
import { Button, Input } from '../../components/primitives'
import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { useHashState } from '../../hooks/useHashState'
import { LABEL, PillGroup } from '../promptlib/taskstyle'
import { PageTourLink } from '../tour/PageTourLink'
import {
  Changes, DOT, Words, anchor, chaptersOf, dropOnChapter, jump, landOn, matches, members, shortDate, useActiveSection,
  type Chapter, type ChapterMode,
} from '../visions/chapters'
import {
  cleanTitle, dateOf, isExample, tagCounts, taskIds, useSetTags, useSetWrites, useSets, useTaskIndex, visionText,
  type KeptKind, type KeptSet, type SetWrites, type TaskRef, type Vision,
} from '../visions/data'
import type { Guide } from '../visions/guides'
import type { Near } from '../visions/near'
import { ContextFold, CopyButton, ExampleChip, InterpretationEditor, InterpretationText, PageGuide, VersionPills, stamp, whoOf } from '../visions/parts'
import { ProjectPills } from '../../components/ProjectPills'
import { ProjectsPanel } from './projects'
import { AddToSetMenu, SetsPanel, kindN } from './sets'
import { DRAG_TYPE, TagRow } from './tags'
import { t } from '../../i18n/scope/system'

const NO_SETS: KeptSet[] = []

const FIND: Record<string, string> = { vision: t('Find in visions'), rule: t('Find in rules'), problem: t('Find in problems'), entrypoint: t('Find in entry points') }
/** The sections drawn with their records before the page shows at all. */
const FIRST_SCREEN = 4
const asIs = async (vs: Vision[]) => vs
const startDrag = (id: string) => (e: React.DragEvent) => {
  e.dataTransfer.setData(DRAG_TYPE, id)
  e.dataTransfer.setData('text/plain', id)
  e.dataTransfer.effectAllowed = 'copy'
}

/** What a page's slots are handed: the shared state of the book. */
export interface BookCtx {
  mode: string
  sets: KeptSet[]
  writes: SetWrites
  tasks: Map<string, TaskRef>
  known: string[]
  draggable: boolean
}

export function KeptBook({
  kind, title, icon, guide, entries, pool = entries, loading, error, empty,
  modes, defaultMode, chapters: chaptersFn, headline = (v) => cleanTitle(v.row.l1), mark,
  aboveGuide, belowGuide, controls, projects: withProjects = false, section, near, complete = asIs,
  inProject, belongs,
}: {
  kind: KeptKind
  title: string
  icon: LucideIcon
  guide: Guide
  /** Every entry of the kind (tags, sets and drops reach them all). */
  entries: Vision[]
  /** The entries this view reads (Rules: the active or the archived ones). */
  pool?: Vision[]
  loading: boolean
  error: unknown
  /** What to say when the pool is empty. */
  empty: string
  modes: Array<[string, string]>
  defaultMode: string
  /** A page's own grouping; the shared modes go to chaptersOf. */
  chapters?: (shown: Vision[], mode: string, sets: KeptSet[]) => Chapter[] | null
  headline?: (v: Vision) => string
  /** A mark before an entry in the contents (open, for all agents). */
  mark?: (v: Vision) => ReactNode
  aboveGuide?: ReactNode
  belowGuide?: (shown: Vision[]) => ReactNode
  /** Beside "group by". */
  controls?: ReactNode
  /** The Projects panel above the sets: a set can be written into a project. */
  projects?: boolean
  section: (v: Vision, ctx: BookCtx) => ReactNode
  /** The sections whose records are read (useKept's `near`); without it every entry comes complete. */
  near?: Near
  /** The records of entries not read yet, for a copy (useKept's `complete`). */
  complete?: (vs: Vision[]) => Promise<Vision[]>
  /** A tab of this project's page: its entries only, no page header, no grouping by project. */
  inProject?: string
  /** In a project's tab, which entries are this project's (Rules: the ones that reach it); else the project they were kept in. */
  belongs?: (v: Vision) => boolean
}) {
  const Icon = icon
  useEffect(() => { if (!inProject) document.title = `${title} — Slightly Parallel` }, [title, inProject])
  const [hash, setHash] = useHashState()
  const project = inProject ?? hash.project ?? ''
  const q = (hash.q ?? '').trim()
  const shownModes = inProject ? modes.filter(([m]) => m !== 'project') : modes
  const firstMode = shownModes.some(([m]) => m === defaultMode) ? defaultMode : shownModes[0]?.[0] ?? defaultMode
  const mode = shownModes.some(([m]) => m === hash.group) ? String(hash.group) : firstMode
  const tasks = useTaskIndex()
  const sets = useSets(kind).data ?? NO_SETS
  const writes = useSetWrites(kind)
  const writeTags = useSetTags(kind)
  const [over, setOver] = useState<string | null>(null)

  const projectCounts = useMemo(() => {
    const n = new Map<string, number>()
    for (const v of pool) if (v.row.project) n.set(v.row.project, (n.get(v.row.project) ?? 0) + 1)
    return [...n.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [pool])
  const known = useMemo(() => tagCounts(entries).map(([t]) => t), [entries])
  const shown = useMemo(
    () => pool
      .filter((v) => (!project || (inProject && belongs ? belongs(v) : v.row.project === project)) && matches(v, q))
      .sort((a, b) => dateOf(b.row).getTime() - dateOf(a.row).getTime()),
    [pool, project, q, inProject, belongs],
  )
  const chapters = useMemo(
    () => chaptersFn?.(shown, mode, sets) ?? chaptersOf(shown, mode as ChapterMode, sets),
    [chaptersFn, shown, mode, sets],
  )
  const drop = dropOnChapter({ entries, sets, writes, writeTags, onDone: () => setOver(null) })
  const draggable = mode === 'tag' || mode === 'set'
  const ctx = useMemo<BookCtx>(() => ({ mode, sets, writes, tasks, known, draggable }),
    [mode, sets, writes, tasks, known, draggable])

  // A search reads the words each entry was kept from, so it reads every record.
  const want = near?.want
  const poolIds = useMemo(() => pool.map((v) => v.row.id), [pool])
  useEffect(() => { if (q && want) want(poolIds) }, [q, want, poolIds])
  // The first screen waits for its records, as the whole page used to: the
  // book opens drawn, not filling in. Later reads fill in below the reader.
  const firstIds = useMemo(() => chapters.flatMap((c) => c.full).slice(0, FIRST_SCREEN).map((v) => v.row.id), [chapters])
  useEffect(() => { if (want && firstIds.length) want(firstIds) }, [want, firstIds])
  const [opened, setOpened] = useState(false)
  const firstPending = !loading && chapters.flatMap((c) => c.full).slice(0, FIRST_SCREEN).some((v) => v.pending)
  useEffect(() => { if (!loading && !firstPending) setOpened(true) }, [loading, firstPending])
  const drawing = loading || (!opened && firstPending)

  const copyAll = async () => {
    const all = await complete(shown)
    void copy(all.map(visionText).join('\n'), t('Copied {what}', { what: kindN(shown.length, kind) }))
  }
  const copyChapter = async (c: Chapter) => {
    const list = await complete(members(c))
    void copy(`# ${c.title}\n\n${list.map(visionText).join('\n')}`, t('Copied {what}', { what: `${c.title} · ${kindN(list.length, kind)}` }))
  }

  const findAndCopy = (
    <>
      <Input value={hash.q ?? ''} onChange={(e) => setHash({ q: e.target.value })} placeholder={FIND[kind] ?? `Find in ${kind}s`} aria-label={FIND[kind] ?? `Find in ${kind}s`} className="w-[220px] h-24 text-12" />
      <button type="button" onClick={() => void copyAll()} disabled={!shown.length}
        className="inline-flex items-center gap-6 h-24 px-10 rounded-input border border-border-default text-12 text-secondary hover:text-primary hover:bg-hover disabled:opacity-50">
        <Copy size={12} aria-hidden /> {t('Copy all')}
      </button>
    </>
  )

  return (
    <div className="flex flex-col gap-16">
      {inProject ? null : (
        <PageHeader
          variant="lens" icon={Icon} title={title}
          actions={<>
            <PageTourLink script={`${kind}s`} />
            {findAndCopy}
          </>}
        >
          <ProjectPills projects={projectCounts.map(([code, count]) => ({ code, count }))} value={project}
            all={{ count: pool.length }} clearable onPick={(v) => setHash({ project: v })} />
        </PageHeader>
      )}

      {aboveGuide}
      {!inProject && <PageGuide id={`${kind}s`} guide={guide} examples={entries.filter((v) => isExample(v.row)).length} />}
      {belowGuide?.(shown)}

      <div className="flex items-center gap-16 flex-wrap">
        <PillGroup label={t('group by')} value={mode}
          onChange={(v) => setHash({ group: v && v !== firstMode ? v : '' })}
          options={shownModes} />
        {controls}
        {inProject && <div className="ml-auto flex items-center gap-8">{findAndCopy}</div>}
      </div>

      {drawing && <LoadingSkeleton variant="card" count={3} />}
      {!!error && <ErrorBanner title={`Could not read ${kind}s`} hideDismiss />}
      {!drawing && !error && (inProject ? shown.length === 0 && !q : pool.length === 0) && <p className="text-13 text-secondary">{empty}</p>}
      {!drawing && (inProject ? q !== '' : pool.length > 0) && shown.length === 0 && <p className="text-12 font-mono text-tertiary">{t('Nothing matches.')}</p>}

      {!drawing && (
        <div className="grid gap-24 lg:grid-cols-[200px_minmax(0,1fr)] xl:grid-cols-[200px_minmax(0,1fr)_280px]">
          <Contents kind={kind} shown={shown} chapters={chapters} mode={mode} sets={sets} loading={drawing}
            draggable={draggable} over={over} setOver={setOver} drop={drop} headline={headline} mark={mark} />

          <div className="order-first lg:col-span-2 xl:order-last xl:col-span-1">
            <div className="xl:sticky xl:top-[16px] flex flex-col gap-12 xl:max-h-[calc(100vh-32px)] xl:overflow-y-auto">
              {withProjects && !inProject && <ProjectsPanel />}
              <SetsPanel draggable={withProjects} noun={kind} sets={sets} visions={entries} writes={writes} complete={complete}
                active={hash.set ?? ''} onActive={(id) => setHash({ set: id })} />
            </div>
          </div>

          <article className="flex flex-col gap-32 min-w-0">
            {chapters.map((c) => (
              <div key={c.key} id={c.key} className="scroll-mt-[16px] flex flex-col gap-24">
                <div className="flex items-center gap-12">
                  <span className="text-12 uppercase tracking-wide font-mono text-primary font-medium">{c.title}</span>
                  <span className="text-11 font-mono text-tertiary tabular">{members(c).length}</span>
                  <span className="h-1 flex-1 bg-border-subtle" />
                  <Button variant="text" size="bare" onClick={() => void copyChapter(c)} disabled={!members(c).length}
                    iconLeft={<Copy size={12} aria-hidden />}>
                    {t('Copy chapter')}
                  </Button>
                  {!c.setId && members(c).length > 0 && (
                    <AddToSetMenu ids={members(c).map((v) => v.row.id)} sets={sets} writes={writes} label={t('Add all to set')} />
                  )}
                </div>
                {c.full.length === 0 && c.refs.length === 0 && (
                  <p className="text-12 text-tertiary">{t('Empty. Drag a {kind} onto this set in the contents, or use Add to set.', { kind })}</p>
                )}
                {c.full.map((v) => <div key={v.row.id} ref={near?.watch(v.row.id)}>{section(v, ctx)}</div>)}
                {c.refs.length > 0 && (
                  <div className="flex flex-col gap-4 rounded-input border border-dashed border-border-subtle px-12 py-8">
                    <span className={LABEL}>{t('Also in {title}', { title: c.title })}</span>
                    {c.refs.map(({ v, home }) => (
                      <button key={v.row.id} type="button" onClick={() => jump(v.row.id)}
                        className="text-left text-13 text-secondary hover:text-brand leading-snug">
                        {headline(v)} <span className="text-11 font-mono text-tertiary">— {t('in {home}', { home })}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </article>
        </div>
      )}
    </div>
  )
}

/**
 * One entry as a section: the title, when and by whom, the tasks it names,
 * its tags; the version line (versions, Add to set, Copy, Edit); the text
 * of the version shown (or what changed since an older one); the words it
 * was kept from, and the chat around them.
 */
export function KeptSection({
  v, kind, ctx, headline = cleanTitle(v.row.l1), dim = false, meta, belowTags, status, actions,
  renderBody = (text) => <InterpretationText text={text} />, emptyBody, wordsLabel, after,
}: {
  v: Vision
  kind: KeptKind
  ctx: BookCtx
  headline?: string
  dim?: boolean
  /** More of "when and by whom" (Rules: the problem it came from). */
  meta?: ReactNode
  belowTags?: ReactNode
  /** Beside the versions (Problems: open or resolved, the severity). */
  status?: ReactNode
  /** First in the version line's actions. */
  actions?: ReactNode
  renderBody?: (text: string) => ReactNode
  /** When nothing is written yet (the default says so). */
  emptyBody?: ReactNode
  wordsLabel?: string
  after?: ReactNode
}) {
  const versions = v.kept?.versions ?? []
  const current = versions[versions.length - 1]
  const [shownN, setShownN] = useState(current?.n ?? 0)
  const [editing, setEditing] = useState(false)
  useEffect(() => { setShownN(current?.n ?? 0) }, [current?.n])
  const shownV = versions.find((x) => x.n === shownN) ?? current
  const older = !!(shownV && current && shownV.n !== current.n)
  const refs = taskIds(`${v.row.l1} ${v.kept?.message ?? ''}`)
    .map((id) => ctx.tasks.get(id))
    .filter((t): t is TaskRef => !!t)
  const body = shownV?.text ?? v.l2
  const who = shownV ? `v${shownV.n} · ${whoOf(shownV)} · ${stamp(shownV.at)}${shownV.note ? ` · ${shownV.note}` : ''}` : ''

  return (
    <section id={anchor(v.row.id)} className={`scroll-mt-[16px] flex flex-col gap-12 ${dim ? 'opacity-70' : ''}`}>
      <div className="flex flex-col gap-6">
        <div className="flex items-start gap-4">
          {ctx.draggable && (
            <span draggable onDragStart={startDrag(v.row.id)}
              title={t('Drag onto a tag or a set')} aria-label={t('Drag {what}', { what: headline })}
              className="mt-4 -ml-[20px] text-tertiary/60 hover:text-tertiary cursor-grab active:cursor-grabbing">
              <GripVertical size={16} aria-hidden />
            </span>
          )}
          <h2 className="text-20 font-semibold text-primary tracking-tight leading-snug">{headline}</h2>
        </div>
        <div className="flex items-center gap-8 flex-wrap text-11 font-mono text-tertiary">
          <span className="tabular">{stamp(`${v.row.created_date} ${v.row.created_time}`)}</span>
          {v.row.project && <><span aria-hidden>·</span><span>{v.row.project}</span></>}
          {v.row.agent_id && <><span aria-hidden>·</span><AgentName id={v.row.agent_id} /></>}
          {meta}
          {isExample(v.row) && <ExampleChip />}
          {refs.map((t) => (
            <span key={t.id} title={`${t.id} · ${t.status}`}
              className="inline-flex items-center gap-4 px-6 h-20 rounded-pill border border-border-subtle text-secondary max-w-[260px]">
              <span className={`h-6 w-6 rounded-pill shrink-0 ${DOT[t.status] ?? 'bg-border-strong'}`} aria-hidden />
              <span className="truncate">{t.title}</span>
            </span>
          ))}
        </div>
        <TagRow v={v} known={ctx.known} kind={kind} />
        {belowTags}
      </div>

      <div className="flex items-center gap-12 border-y border-border-subtle py-6 flex-wrap">
        <span className="shrink-0 inline-flex">
          <VersionPills versions={versions} value={shownV?.n ?? 0} onChange={setShownN} />
        </span>
        {status}
        {shownV && <span className="text-11 font-mono text-tertiary min-w-0 truncate" title={who}>{who}</span>}
        <span className="ml-auto flex items-center gap-12 shrink-0">
          {actions}
          <AddToSetMenu ids={[v.row.id]} sets={ctx.sets} writes={ctx.writes} />
          <CopyButton vision={v} />
          {v.kept && !editing && (
            <Button variant="text" size="bare" onClick={() => setEditing(true)}
              iconLeft={<Pencil size={12} aria-hidden />}>
              {t('Edit')}
            </Button>
          )}
        </span>
      </div>

      {editing ? (
        <InterpretationEditor vision={v} kind={kind} onDone={() => setEditing(false)} />
      ) : older && shownV && current ? (
        <Changes from={shownV.text} to={current.text} a={shownV.n} b={current.n} />
      ) : body ? (
        renderBody(body)
      ) : v.pending ? null : (
        emptyBody ?? <p className="text-13 text-tertiary">{t('No interpretation yet.')}</p>
      )}

      {v.kept?.message && <Words text={v.kept.message} label={wordsLabel} />}
      {v.kept && <ContextFold kept={v.kept} />}
      {after}
    </section>
  )
}


/**
 * The contents rail. It owns the scroll-following highlight, so a scroll
 * re-renders this list alone, never the sections beside it.
 */
function Contents({ kind, shown, chapters, mode, sets, loading, draggable, over, setOver, drop, headline, mark }: {
  kind: KeptKind
  shown: Vision[]
  chapters: Chapter[]
  mode: string
  sets: KeptSet[]
  loading: boolean
  draggable: boolean
  over: string | null
  setOver: (f: (o: string | null) => string | null) => void
  drop: (c: Chapter) => (e: React.DragEvent) => void
  headline: (v: Vision) => string
  mark?: (v: Vision) => ReactNode
}) {
  // The contents list follows the section being read.
  const active = useActiveSection(shown, chapters, loading)
  return (
    <nav aria-label={t('Contents')} className="hidden lg:block">
      {shown.length > 0 && (
        <div className="sticky top-[16px] max-h-[calc(100vh-120px)] overflow-y-auto pr-4 flex flex-col gap-12">
          <div className="text-11 font-mono text-tertiary tabular">
            {kindN(shown.length, kind)}
            {mode === 'tag' && <span className="block text-10 text-tertiary/80">{t('Drag a {kind} onto a tag to add the tag.', { kind })}</span>}
            {mode === 'set' && <span className="block text-10 text-tertiary/80">{t('Drag a {kind} onto a set to add it.', { kind })}</span>}
          </div>
          {mode === 'set' && sets.length === 0 && (
            <p className="text-12 text-tertiary leading-relaxed">{t('No sets yet. Make one in the Sets panel.')}</p>
          )}
          {chapters.map((c) => {
            const target = (mode === 'tag' && !!c.tag) || (mode === 'set' && !!c.setId)
            const hot = target && over === c.key
            return (
              <div key={c.key} className="flex flex-col gap-2">
                <button type="button" onClick={() => landOn(document.getElementById(c.key))}
                  onDragOver={target ? (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setOver(() => c.key) } : undefined}
                  onDragLeave={target ? () => setOver((o) => (o === c.key ? null : o)) : undefined}
                  onDrop={target ? drop(c) : undefined}
                  className={`flex items-center gap-6 px-8 h-24 rounded-input border text-left transition-colors ${
                    hot ? 'border-brand bg-brand-glow text-brand' : 'border-transparent hover:bg-hover'}`}>
                  <span className={`${LABEL} ${hot ? 'text-brand' : ''} flex-1 truncate`}>{c.title}</span>
                  <span className="text-10 font-mono text-tertiary tabular">{members(c).length}</span>
                </button>
                {c.full.map((v) => (
                  <button key={v.row.id} type="button" onClick={() => jump(v.row.id)}
                    draggable={draggable} onDragStart={startDrag(v.row.id)}
                    className={`text-left rounded-input px-8 py-3 flex items-baseline gap-8 ${active === v.row.id ? 'bg-brand-glow text-brand' : 'text-secondary hover:text-primary hover:bg-hover'} ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}`}>
                    {mark?.(v)}
                    <span className="text-12 leading-snug line-clamp-2 flex-1 min-w-0">{headline(v)}</span>
                    <span className="text-10 font-mono text-tertiary tabular shrink-0">{shortDate(v)}</span>
                  </button>
                ))}
                {c.refs.map(({ v }) => (
                  <button key={`ref-${v.row.id}`} type="button" onClick={() => jump(v.row.id)}
                    className="block w-full text-left rounded-input px-8 py-3 text-12 leading-snug text-tertiary hover:text-primary hover:bg-hover truncate">
                    {headline(v)}
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      )}
    </nav>
  )
}
