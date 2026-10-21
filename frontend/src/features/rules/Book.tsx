import { copyText } from '../../lib/useCopy'
import { useCallback, useMemo, useState } from 'react'
import { Archive, ArchiveRestore, BookOpen, Copy, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { useHashState } from '../../hooks/useHashState'
import { fail } from '../../lib/getJson'
import { KeptBook, KeptSection, type BookCtx } from '../kept/Book'
import { LABEL, PillGroup } from '../promptlib/taskstyle'
import { chaptersOf, type Chapter, type ChapterMode } from '../visions/chapters'
import {
  cleanTitle, isExample, useAllRules, useIntegrations, useKept, useSetFields, useSets, useSyncAllRules,
  type KeptSet, type Vision,
} from '../visions/data'
import { RULES_GUIDE } from '../visions/guides'
import { Switch, isArchived, isForAll, reachOf, ruleHeadline, type Reach } from './reach'
import { t } from '../../i18n/scope/system'

/**
 * Rules — one model for where a rule reaches. A rule on its own reaches no
 * one. It reaches agents in two ways only: "For all agents", which Slightly Parallel
 * keeps written into the AGENTS.md of every project set up in Setup, and a
 * set of rules written into chosen projects from the Projects panel.
 * Archive hides a rule and takes it out of every written copy; Restore
 * brings it back. Each rule says where it reaches. The page is the kept
 * book (features/kept/Book) with those parts.
 */

/** The page's own grouping: where a rule reaches. */
function reachChapters(shown: Vision[], reach: (v: Vision) => Reach): Chapter[] {
  const groups: Array<[string, string, (r: Reach) => boolean]> = [
    ['reach:all', t('All projects'), (r) => r.all],
    ['reach:chosen', t('Chosen projects'), (r) => !r.all && r.places.length > 0],
    ['reach:none', t('Nowhere'), (r) => !r.all && r.places.length === 0],
  ]
  return groups
    .map(([key, title, test]) => ({ key, title, full: shown.filter((v) => test(reach(v))), refs: [] }))
    .filter((c) => c.full.length > 0)
}

export function RulesBook({ project }: { project?: string } = {}) {
  const [hash, setHash] = useHashState()
  const showing = hash.status === 'archived' ? 'archived' : 'active'
  const { visions: rules, loading, error, near, complete } = useKept('rule')
  const setsData = useSets('rule').data
  const integrationsData = useIntegrations().data
  const sets = useMemo(() => setsData ?? [], [setsData])
  const integrations = useMemo(() => integrationsData ?? [], [integrationsData])
  const reach = useCallback((v: Vision) => reachOf(v, sets, integrations), [sets, integrations])
  // In a project's tab: the rules that reach its agents, and the ones kept in it.
  const belongs = useCallback((v: Vision) => {
    const r = reach(v)
    return r.all || r.places.some((p) => p.project === project) || v.row.project === project
  }, [reach, project])
  const mine = useMemo(() => (project ? rules.filter(belongs) : rules), [rules, project, belongs])
  const current = useMemo(() => mine.filter((v) => !isArchived(v)), [mine])
  const archived = useMemo(() => mine.filter(isArchived), [mine])
  const chapters = useCallback(
    (shown: Vision[], mode: string, s: KeptSet[]) =>
      mode === 'reach'
        ? showing === 'archived' ? chaptersOf(shown, 'tag', s) : reachChapters(shown, reach)
        : chaptersOf(shown, mode as ChapterMode, s),
    [showing, reach],
  )
  const headline = (v: Vision) => ruleHeadline(v, cleanTitle(v.row.l1))

  return (
    <KeptBook kind="rule" title={t('Rules')} icon={BookOpen} guide={RULES_GUIDE}
      entries={rules} pool={showing === 'archived' ? archived : current} loading={loading} error={error} projects
      empty={showing === 'archived' ? t('No archived rules.') : t('No rules yet. Add #rule to a message to keep it.')}
      modes={[['tag', 'tag'], ['project', 'project'], ['month', 'month'], ['set', 'sets'], ['reach', 'reach']]} defaultMode="tag"
      chapters={chapters} headline={headline} near={near} complete={complete}
      mark={(v) => isForAll(v) && <span className="h-6 w-6 rounded-pill bg-brand shrink-0 self-center" title={t('For all agents')} aria-hidden />}
      aboveGuide={!loading && rules.length > 0 && <ForAll current={current} />}
      controls={
        <PillGroup label={t('show')} value={showing}
          onChange={(v) => setHash({ status: v === 'archived' ? 'archived' : '' })}
          options={[['active', t('rules {n}', { n: current.length })], ['archived', t('archived {n}', { n: archived.length })]]} />
      }
      inProject={project} belongs={belongs}
      section={(v, ctx) => <RuleSection v={v} ctx={ctx} reach={reach(v)} headline={headline(v)} />} />
  )
}

/** How many rules reach every agent, in how many projects they are written, and the text itself. */
function ForAll({ current }: { current: Vision[] }) {
  const allRules = useAllRules().data
  const syncAll = useSyncAllRules()
  const [showBlock, setShowBlock] = useState(false)
  const forAllCount = allRules?.items.length ?? current.filter(isForAll).length
  const targets = allRules?.projects ?? []
  const fresh = targets.filter((p) => p.status === 'fresh').length
  const behind = forAllCount > 0 && targets.some((p) => p.status === 'stale' || p.status === 'missing')
  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center gap-12 flex-wrap">
        <span className="text-13 text-secondary">
          {forAllCount === 0 ? t('No rules for all agents.') : (
            <>
              <span className="font-mono text-primary tabular">{forAllCount}</span>{' '}
              {forAllCount === 1 ? 'rule' : 'rules'} for all agents · written to{' '}
              <span className="font-mono text-primary tabular">{fresh}</span> of {targets.length}{' '}
              {targets.length === 1 ? 'project' : 'projects'}
            </>
          )}
        </span>
        {behind && (
          <button type="button" disabled={syncAll.isPending}
            onClick={() => syncAll.mutate(undefined, { onSuccess: () => toast.success(t('Updated in every project')), onError: fail })}
            className="inline-flex items-center gap-4 text-11 font-mono text-brand hover:underline disabled:opacity-40">
            <RefreshCw size={12} aria-hidden /> Update
          </button>
        )}
        {forAllCount > 0 && allRules?.content && (
          <>
            <button type="button" onClick={() => setShowBlock((x) => !x)} aria-expanded={showBlock}
              className="text-11 font-mono text-tertiary hover:text-brand">
              {showBlock ? t('Hide the text') : t('Show the text')}
            </button>
            <button type="button"
              onClick={() => { void copyText(allRules.content) }}
              className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-brand">
              <Copy size={12} aria-hidden /> Copy
            </button>
          </>
        )}
      </div>
      {showBlock && allRules?.content && (
        <div className="flex flex-col gap-3">
          <span className="text-10 font-mono text-tertiary">What every AGENTS.md holds · {allRules.words} words</span>
          <pre className="max-h-[320px] overflow-y-auto rounded-input border border-border-subtle bg-elevated px-12 py-10 text-12 font-mono text-primary whitespace-pre-wrap break-words">
            {allRules.content}
          </pre>
        </div>
      )}
    </div>
  )
}

/** "All projects", "atlas · Design rounds", "Nowhere", "Archived". */
function ReachLine({ v, reach }: { v: Vision; reach: Reach }) {
  if (isArchived(v)) return <span className="text-11 font-mono text-tertiary">{t('Archived · removed from every project')}</span>
  if (isExample(v.row)) return <span className="text-11 font-mono text-tertiary">{t('Example · stays on this page')}</span>
  const nowhere = !reach.all && reach.places.length === 0
  return (
    <div className="flex items-center gap-6 flex-wrap text-11 font-mono">
      <span className={LABEL}>{t('reaches')}</span>
      {reach.all && (
        <span className="inline-flex items-center h-20 px-6 rounded-pill border border-brand/40 bg-brand-glow text-brand">{t('All projects')}</span>
      )}
      {reach.places.map((p) => (
        <span key={`${p.project}:${p.set}`} className="inline-flex items-center h-20 px-6 rounded-pill border border-border-subtle text-secondary">
          {p.project} · {p.set}
        </span>
      ))}
      {nowhere && <span className="text-tertiary">{t('Nowhere')}</span>}
    </div>
  )
}

function RuleSection({ v, ctx, reach, headline }: { v: Vision; ctx: BookCtx; reach: Reach; headline: string }) {
  const fields = useSetFields('rule')
  const archived = isArchived(v)
  const fromProblem = v.kept?.from ?? null
  return (
    <KeptSection v={v} kind="rule" ctx={ctx} headline={headline} dim={archived}
      meta={fromProblem && <><span aria-hidden>·</span><span className="text-secondary" aria-label={t('From problem {id}', { id: fromProblem })}>{t('From problem {id}', { id: fromProblem })}</span></>}
      belowTags={<ReachLine v={v} reach={reach} />}
      actions={<>
        <Switch
          on={isForAll(v)}
          disabled={archived || fields.isPending}
          label={t('For all agents')}
          title={archived ? t('Restore the rule first') : undefined}
          onChange={(next) => fields.mutate(
            { id: v.row.id, auto: next ? 'yes' : '' },
            { onSuccess: () => toast.success(next ? t('Added to every project') : t('Removed from every project')), onError: fail },
          )}
        />
        <button type="button" disabled={fields.isPending}
          onClick={() => fields.mutate(
            { id: v.row.id, status: archived ? 'active' : 'archived' },
            { onSuccess: () => toast.success(archived ? t('Restored') : t('Archived')), onError: fail },
          )}
          className="inline-flex items-center gap-4 text-11 font-mono text-tertiary hover:text-primary disabled:opacity-40">
          {archived ? <ArchiveRestore size={12} aria-hidden /> : <Archive size={12} aria-hidden />} {archived ? t('Restore') : t('Archive')}
        </button>
      </>}
      wordsLabel={fromProblem ? t('The problem') : t('Your words')} />
  )
}
