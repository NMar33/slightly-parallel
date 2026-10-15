import { absolutePath, useFolder } from '../../../lib/paths'
import { useState, type ReactNode } from 'react'
import { AgentName } from '../../../components/AgentName'
import { CopyButton } from '../../../components/CopyButton'
import { Markdown } from '../../../components/Markdown'
import { ErrorBanner, LoadingSkeleton } from '../../../components/states'
import { formatStamp } from '../../../utils/dateUtils'
import { LABEL } from '../../promptlib/taskstyle'
import { segments, standingWord, useArchPage, type ArchPage, type Claim, type Facts, type PageSection, type PageVersion } from './data'
import { locale, t, tn } from '../../../i18n/scope/system'

import { rich } from '../../../i18n/rich'
/**
 * The architecture page of one project: what it is, as claims with their
 * evidence. Two layers, kept apart on screen: what Slightly Parallel computed from the
 * folder with no model, and what an agent wrote. Each claim shows where it
 * lives, how the writer knows, who made the thing and who checked it; the
 * server marks a path it did not find and a file that changed since.
 */
export function ArchPagePanel({ projectCode }: { projectCode: string }) {
  const [version, setVersion] = useState<number | undefined>(undefined)
  const { data, isLoading, error } = useArchPage(projectCode, version)

  if (error) return <ErrorBanner title={t('The architecture page could not be read')} message={String((error as Error).message)} />
  if (isLoading && !data) return <LoadingSkeleton variant="row" count={4} />
  if (!data) return null
  const { page, versions, facts } = data
  const newest = versions.length ? versions[versions.length - 1].n : undefined

  return (
    <div className="flex flex-col gap-14 min-w-0">
      {page && (
        <PageHeader
          page={page}
          versions={versions}
          isOld={newest !== undefined && page.n !== newest}
          onPick={(n) => setVersion(n === newest ? undefined : n)}
        />
      )}
      <ComputedBand facts={facts} />
      {page ? (
        <div className="flex flex-col gap-20 max-w-[980px]">
          {page.sections.map((s) => <Section key={s.title} section={s} />)}
          <p className="text-11 font-mono text-tertiary">{t('{n} words · budget {budget}', { n: page.words, budget: data.word_budget })}</p>
        </div>
      ) : (
        <div className="rounded-card border border-border-subtle bg-surface px-16 py-14">
          <p className="text-14 text-primary">{t('No architecture page yet.')}</p>
          <p className="text-12 text-secondary mt-4">
            {t('It is written at the end of a scan, or when you type')} <code className="font-mono">#page</code> {t('in a chat with an agent of this project.')}
          </p>
        </div>
      )}
      <HowItWorks />
    </div>
  )
}

function PageHeader({ page, versions, isOld, onPick }: {
  page: ArchPage; versions: PageVersion[]; isOld: boolean; onPick: (n: number) => void
}) {
  const c = page.counts
  return (
    <div className="flex items-center gap-8 flex-wrap text-12">
      <span className="text-primary font-medium">{t('Version {n}', { n: page.n })}</span>
      <span className="text-tertiary font-mono">
        {t('written {date} by', { date: formatStamp(page.at) })} <AgentName id={page.agent_id} />
      </span>
      {page.note && <span className="text-secondary">· {page.note}</span>}
      {isOld && <Chip tone="amber">{t('An older version. Read only.')}</Chip>}
      <span className="ml-auto flex items-center gap-6 flex-wrap">
        <Chip>{tn(c.claims, '{n} claim', '{n} claims')}</Chip>
        {c.missing > 0 && <Chip tone="red">{t('{n} not found', { n: c.missing })}</Chip>}
        {c.changed_since > 0 && <Chip tone="amber">{t('{n} changed since', { n: c.changed_since })}</Chip>}
        {versions.length > 1 && (
          <label className="flex items-center gap-4">
            <span className={LABEL}>{t('version')}</span>
            <select
              id="arch-page-version"
              aria-label={t('Version')}
              value={page.n}
              onChange={(e) => onPick(Number(e.target.value))}
              className="h-24 rounded-input border border-border-subtle bg-surface text-12 font-mono px-6"
            >
              {[...versions].reverse().map((v) => (
                <option key={v.n} value={v.n}>{v.n} · {formatStamp(v.at)}</option>
              ))}
            </select>
          </label>
        )}
      </span>
    </div>
  )
}

type Tone = 'red' | 'amber' | 'plain'
const TONE: Record<Tone, { className: string; color?: string }> = {
  red: { className: 'border-current', color: 'var(--status-red)' },
  amber: { className: 'border-current', color: 'var(--status-amber)' },
  plain: { className: 'border-border-subtle text-secondary' },
}

function Chip({ tone = 'plain', children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  const t = TONE[tone]
  return (
    <span title={title} style={t.color ? { color: t.color } : undefined}
      className={`inline-flex items-center h-20 px-8 rounded-pill border text-11 font-mono ${t.className}`}>
      {children}
    </span>
  )
}

const STANDING_COLOR: Record<string, string | undefined> = {
  active: 'var(--status-green)', paused: 'var(--status-amber)', dormant: undefined, empty: undefined,
}

function ComputedBand({ facts }: { facts: Facts }) {
  if (!facts.folder) {
    return (
      <section aria-label={t('Computed by Slightly Parallel')} className="rounded-card border border-border-subtle bg-elevated px-14 py-10 text-12 text-secondary">
        <span className={LABEL}>{t('Computed by Slightly Parallel')}</span>
        <p className="mt-4">{facts.note ?? t('No folder is registered for this project.')}</p>
      </section>
    )
  }
  const word = standingWord(facts.standing)
  const rest = (facts.standing ?? '').trim().slice(word.length)
  const git = facts.git
  const folders = facts.top_level ?? []
  return (
    <section aria-label={t('Computed by Slightly Parallel')} className="rounded-card border border-border-subtle bg-elevated px-14 py-10 flex flex-col gap-6">
      <div className="flex items-baseline gap-8 flex-wrap">
        <span className={LABEL}>{t('Computed by Slightly Parallel')}</span>
        <span className="text-11 text-tertiary">{t('From the folder, with no agent. Today is {date}.', { date: facts.today ?? '' })}</span>
      </div>
      <div className="flex items-baseline gap-x-14 gap-y-4 flex-wrap text-12 font-mono text-secondary">
        <span>
          <span data-standing={word} className={`font-semibold ${STANDING_COLOR[word] ? '' : 'text-tertiary'}`} style={{ color: STANDING_COLOR[word] }}>{word}</span>
          {rest}
        </span>
        <span>{tn(facts.files ?? 0, '{n} file', '{n} files', { n: (facts.files ?? 0).toLocaleString(locale()) })}</span>
        {git && <span>{tn(git.commits, '{n} commit', '{n} commits', { n: git.commits.toLocaleString(locale()) })}</span>}
        {git?.last_commit && <span className="truncate max-w-[520px]" title={git.last_commit}>{t('last commit {what}', { what: git.last_commit })}</span>}
        {git && git.uncommitted_files ? <span style={{ color: 'var(--status-amber)' }}>{t('uncommitted files: {n}', { n: git.uncommitted_files })}</span> : null}
        {git?.remote?.[0] && <span className="truncate max-w-[360px]" title={git.remote[0]}>{t('remote')} {git.remote[0].split(/\s+/)[1] ?? git.remote[0]}</span>}
        {!git && <span>{t('not a git repository')}</span>}
        {(facts.nested_repositories?.length ?? 0) > 0 && <span>{t('repositories inside: {n}', { n: facts.nested_repositories!.length })}</span>}
        {(facts.build_and_ci_files?.length ?? 0) > 0 && <span>{t('build files:')} {facts.build_and_ci_files!.join(', ')}</span>}
      </div>
      {folders.length > 0 && (
        <details>
          <summary className="cursor-pointer text-11 font-mono text-tertiary hover:text-primary">{t('Folders')} · {folders.length}</summary>
          <div className="overflow-x-auto mt-6">
            <table className="text-12 font-mono">
              <thead>
                <tr className="text-tertiary text-left">
                  <th className="pr-16 font-normal">{t('folder')}</th><th className="pr-16 font-normal text-right">{t('files')}</th>
                  <th className="pr-16 font-normal text-right">{t('MB')}</th><th className="font-normal">{t('last change')}</th>
                </tr>
              </thead>
              <tbody>
                {folders.map((f) => (
                  <tr key={f.name} className={isOld(f.last_change, facts.today) ? 'text-tertiary' : 'text-secondary'}>
                    <td className="pr-16">{f.name}</td><td className="pr-16 text-right tabular-nums">{f.files.toLocaleString(locale())}</td>
                    <td className="pr-16 text-right tabular-nums">{f.mb}</td><td>{f.last_change}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {(git?.recent_commit_subjects?.length ?? 0) > 0 && (
        <details>
          <summary className="cursor-pointer text-11 font-mono text-tertiary hover:text-primary">{t('Recent commits')} · {git!.recent_commit_subjects!.length}</summary>
          <ul className="mt-6 flex flex-col gap-2 text-12 font-mono text-secondary">
            {git!.recent_commit_subjects!.map((s, i) => <li key={`${i}-${s}`}>{s}</li>)}
          </ul>
        </details>
      )}
    </section>
  )
}

/** A folder unchanged for eight weeks or more is old material: greyed. */
function isOld(lastChange: string, today?: string): boolean {
  const a = Date.parse(lastChange), b = Date.parse(today ?? '')
  return Number.isFinite(a) && Number.isFinite(b) && b - a > 56 * 86400_000
}

function Section({ section }: { section: PageSection }) {
  const parts = segments(section)
  return (
    <section className="flex flex-col gap-8">
      <h3 className="text-16 font-semibold text-primary border-b border-border-subtle pb-4">{section.title}</h3>
      {parts.map((p, i) =>
        p.kind === 'md'
          ? <div key={i} className="text-13 text-secondary"><Markdown text={p.text} /></div>
          : <ClaimRow key={i} claim={p.claim} />,
      )}
    </section>
  )
}

/** The meta line is plain mono text: markdown marks are taken out. */
const plain = (s: string) => s.replace(/[`*]/g, '')

function ClaimRow({ claim }: { claim: Claim }) {
  const missing = claim.path_found === false
  const where = claim.path ?? (claim.where ?? '').replace(/`/g, '')
  const full = absolutePath(useFolder(), where)
  const edge = missing ? 'var(--status-red)' : claim.changed_since ? 'var(--status-amber)' : undefined
  return (
    <div data-claim className="flex flex-col gap-4 pl-10 border-l-2 border-border-subtle" style={edge ? { borderLeftColor: edge } : undefined}>
      <div className="text-13 text-primary"><Markdown text={claim.text} /></div>
      <div className="flex items-center gap-x-10 gap-y-2 flex-wrap text-11 font-mono text-tertiary">
        {where && (
          <span className="inline-flex items-center gap-4 min-w-0">
            <span className="text-secondary truncate max-w-[460px]" title={full}>{where}</span>
            <CopyButton text={full} title={t('Copy path: {path}', { path: full })} />
          </span>
        )}
        {missing && <Chip tone="red" title={t('This path is not in the project folder')}>{t('not found')}</Chip>}
        {claim.changed_since && <Chip tone="amber" title={t('The file changed after this version was written')}>{t('changed {date}', { date: claim.changed_since })}</Chip>}
        {claim.seen && <span>{t('seen')} <span className="text-secondary">{plain(claim.seen)}</span></span>}
        {claim.made_by && <span>{t('made by')} <span className="text-secondary">{plain(claim.made_by)}</span></span>}
        {claim.checked_by && <span>{t('checked by')} <span className="text-secondary">{plain(claim.checked_by)}</span></span>}
      </div>
    </div>
  )
}

function HowItWorks() {
  return (
    <details className="text-12 text-secondary max-w-[760px]">
      <summary className="cursor-pointer text-brand">{t('How it works')}</summary>
      <div className="mt-6 flex flex-col gap-4">
        <p>{t('The page says what the project is, what it does now, what it is made of and what is owed.')}</p>
        <p>{rich(t('An agent of the project writes it when you type {page}, and at the end of a scan. Each new version keeps what is verified and adds what changed.'), { page: <code className="font-mono">#page</code> })}</p>
        <p>{t('Each item is a claim. It says where the thing is, how the writer knows, who made it and who checked it.')}</p>
        <p>{t('Slightly Parallel checks every path. A path that is not in the folder is marked "not found". A file that changed after the version was written is marked "changed".')}</p>
        <p>{t('The band "Computed by Slightly Parallel" comes from the folder itself. No agent writes it.')}</p>
      </div>
    </details>
  )
}
