import { absolutePath, useFolder } from '../../../lib/paths'
import { useState } from 'react'
import { AgentName } from '../../../components/AgentName'
import { CopyButton } from '../../../components/CopyButton'
import { EmptyState, ErrorBanner, LoadingSkeleton } from '../../../components/states'
import { Badge } from '../../../components/primitives'
import { formatStamp } from '../../../utils/dateUtils'
import { LABEL } from '../../promptlib/taskstyle'
import { groupRows, KIND_WORDS, problemsFor, useMap, type MapCurrent, type MapFacts, type MapRow } from './data'
import { t, tn } from '../../../i18n/scope/system'

/**
 * The map of a program: every part as a row of one kind, and what connects
 * to what. The table is grouped by kind in reading order; a row the
 * server could not check is marked. Under the table: the relations, the
 * notes, and what came and went since the version before. The computed
 * band on top comes from the repository with no agent, as on the page.
 */
export function MapPanel({ projectCode }: { projectCode: string }) {
  const [version, setVersion] = useState<number | undefined>(undefined)
  const { data, isLoading, isError, error, refetch } = useMap(projectCode, version)

  if (isError) return <ErrorBanner title={t('The map could not be read')} message={error instanceof Error ? error.message : String(error)} onRetry={() => void refetch()} hideDismiss />
  if (isLoading || !data) return <LoadingSkeleton variant="row" count={4} />

  const cur = data.map
  return (
    <div className="flex flex-col gap-14 min-w-0">
      {cur && (
        <div className="flex items-center gap-10 flex-wrap text-11 font-mono text-tertiary">
          <span className="text-12 text-primary">{t('Version {n}', { n: cur.n })}</span>
          <span>{t('written {date} by', { date: formatStamp(cur.at) })} <AgentName id={cur.agent_id} /></span>
          {cur.note && <span className="text-secondary font-sans">· {cur.note}</span>}
          <span className="ml-auto flex items-center gap-8 flex-wrap">
            <Badge tone="neutral">{cur.template}</Badge>
            <Badge tone="neutral">{tn(cur.map.rows.length, '{n} row', '{n} rows')}</Badge>
            <Badge tone="neutral">{tn(cur.map.relations.length, '{n} relation', '{n} relations')}</Badge>
            {cur.problems.length > 0 && <Badge tone="warning">{t('{n} to fix', { n: cur.problems.length })}</Badge>}
            {cur.changes.added.length > 0 && <Badge tone="done">+{tn(cur.changes.added.length, '{n} row', '{n} rows')}</Badge>}
            {cur.changes.removed.length > 0 && <Badge tone="idle">−{tn(cur.changes.removed.length, '{n} row', '{n} rows')}</Badge>}
            {data.versions.length > 1 && (
              <label className="inline-flex items-center gap-4">
                <span className={LABEL}>{t('version')}</span>
                <select
                  className="h-20 rounded-input border border-border-subtle bg-elevated text-11 font-mono text-secondary px-4"
                  value={version ?? cur.n}
                  onChange={(e) => setVersion(Number(e.target.value) === data.versions[data.versions.length - 1].n ? undefined : Number(e.target.value))}
                >
                  {[...data.versions].reverse().map((v) => (
                    <option key={v.n} value={v.n}>{v.n} · {formatStamp(v.at)}</option>
                  ))}
                </select>
              </label>
            )}
          </span>
        </div>
      )}

      <ComputedBand facts={data.facts} />

      {!cur && (
        <EmptyState
          title={t('No map yet')}
          subtitle={t('It is written at the standup, when you choose write and map, or when you type #map. The agent asks before it reads the repository.')}
        />
      )}
      {cur && <MapTable cur={cur} />}
    </div>
  )
}

function ComputedBand({ facts }: { facts: MapFacts }) {
  if (facts.note) return <p className="text-11 text-tertiary">{facts.note}</p>
  const langs = (facts.languages ?? []).slice(0, 4).map(([l, n]) => `${l} ${n}`).join(' · ')
  const manifests = (facts.manifests ?? []).map((m) => m.file.split('/').slice(-2).join('/'))
  return (
    <div className="rounded-card border border-border-subtle bg-elevated px-14 py-10 flex flex-col gap-4 text-11 font-mono text-secondary">
      <div className="flex items-baseline gap-8 flex-wrap">
        <span className={LABEL}>{t('Computed by Slightly Parallel')}</span>
        <span className="text-tertiary font-sans">{t('From the repository, with no agent.')}</span>
      </div>
      <div className="flex flex-wrap gap-x-12 gap-y-2">
        {facts.files != null && <span>{tn(Number(facts.files), '{n} file', '{n} files')}</span>}
        {langs && <span>{langs}</span>}
        {facts.git && <span>{t('{n} commits · last {when}', { n: facts.git.commits, when: facts.git.last_commit })}</span>}
        {(facts.ports_named_in_code ?? []).length > 0 && <span>{t('ports {list}', { list: facts.ports_named_in_code!.join(', ') })}</span>}
        {(facts.env_variables_read_by_code ?? []).length > 0 && <span>{t('environment variables read: {n}', { n: facts.env_variables_read_by_code!.length })}</span>}
      </div>
      {manifests.length > 0 && (
        <details>
          <summary className="cursor-pointer text-11 font-mono text-tertiary hover:text-primary">{t('Manifests')} · {manifests.length}</summary>
          <ul className="mt-4 flex flex-col gap-1">
            {(facts.manifests ?? []).map((m) => (
              <li key={m.file} className="flex gap-8 flex-wrap">
                <span className="text-primary">{m.file.split('/').slice(-2).join('/')}</span>
                <span className="text-tertiary">{describeManifest(m.declares)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {(facts.build_and_ci_files ?? []).length > 0 && <span className="text-tertiary">{t('build and CI:')} {facts.build_and_ci_files!.join(', ')}</span>}
    </div>
  )
}

function describeManifest(d: Record<string, unknown>): string {
  const parts: string[] = []
  if (typeof d.name === 'string') parts.push(d.name)
  if (typeof d.version === 'string') parts.push(d.version)
  for (const k of ['dependencies', 'requires', 'services', 'targets', 'variables', 'scripts']) {
    const v = d[k]
    if (Array.isArray(v) && v.length) parts.push(`${v.length} ${t(k)}`)
  }
  return parts.join(' · ')
}

function MapTable({ cur }: { cur: MapCurrent }) {
  const groups = groupRows(cur.map.rows)
  const added = new Set(cur.changes.added.map((r) => `${r.kind}:${r.name}`))
  return (
    <div className="flex flex-col gap-14">
      {cur.problems.length > 0 && (
        <div className="rounded-card border bg-elevated px-12 py-8 flex flex-col gap-2" style={{ borderColor: 'var(--status-amber)' }}>
          <span className={LABEL}>{t('To fix')}</span>
          {cur.problems.map((p) => <span key={p} className="text-11 text-secondary">{p}</span>)}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-12 border-collapse" style={{ tableLayout: 'fixed' }}>
          <colgroup><col style={{ width: '11%' }} /><col style={{ width: '19%' }} /><col style={{ width: '30%' }} /><col style={{ width: '22%' }} /><col style={{ width: '18%' }} /></colgroup>
          <thead>
            <tr className="text-left">
              {[t('Kind'), t('Name'), t('What'), t('Where'), t('Evidence')].map((h) => (
                <th key={h} className={`${LABEL} font-normal py-4 pr-12 border-b border-border-subtle`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map(([kind, rows]) => rows.map((r, i) => (
              <Row key={`${kind}:${r.name}`} row={r} first={i === 0} kindWord={KIND_WORDS[kind] ?? kind}
                   problems={problemsFor(cur.problems, r.name)} isNew={added.has(`${r.kind}:${r.name}`)} />
            )))}
          </tbody>
        </table>
      </div>

      {cur.map.relations.length > 0 && (
        <section className="flex flex-col gap-4">
          <span className={LABEL}>{t('What connects to what')}</span>
          <ul className="flex flex-col gap-1 text-12">
            {cur.map.relations.map((rel, i) => (
              <li key={i} className="flex gap-6 items-baseline">
                <span className="text-primary">{rel.from}</span>
                <span className="text-11 font-mono text-tertiary">{rel.verb}</span>
                <span className="text-primary">{rel.to}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {Object.keys(cur.map.notes).length > 0 && (
        <section className="flex flex-col gap-4">
          <span className={LABEL}>{t('Notes')}</span>
          <dl className="grid grid-cols-[auto_1fr] gap-x-12 gap-y-2 text-12">
            {Object.entries(cur.map.notes).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-11 font-mono text-tertiary">{t(k.replace(/_/g, ' '))}</dt>
                <dd className="text-secondary leading-relaxed">{v}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {cur.changes.removed.length > 0 && (
        <section className="flex flex-col gap-2">
          <span className={LABEL}>{t('Gone since version {n}', { n: cur.n - 1 })}</span>
          {cur.changes.removed.map((r) => (
            <span key={`${r.kind}:${r.name}`} className="text-12 text-tertiary line-through">{KIND_WORDS[r.kind] ?? r.kind} · {r.name}</span>
          ))}
        </section>
      )}
    </div>
  )
}

function Row({ row, first, kindWord, problems, isNew }: { row: MapRow; first: boolean; kindWord: string; problems: string[]; isNew: boolean }) {
  const bad = problems.length > 0
  const full = absolutePath(useFolder(), row.where ?? '')
  return (
    <tr className={`align-top border-b border-border-subtle ${first ? 'border-t-2 border-t-border-subtle' : ''}`} title={problems.join('\n') || undefined}>
      <td className="py-4 pr-12 text-11 font-mono text-tertiary whitespace-nowrap">{first ? kindWord : ''}</td>
      <td className="py-4 pr-12 text-primary break-words">
        {row.name}
        {row.version && <span className="ml-4 text-11 font-mono text-tertiary">{row.version}</span>}
        {isNew && <span className="ml-4 text-10 font-mono" style={{ color: 'var(--status-green)' }}>{t('new')}</span>}
        {bad && <span className="ml-4 text-10 font-mono" style={{ color: 'var(--status-red)' }}>{t('not found')}</span>}
      </td>
      <td className="py-4 pr-12 text-secondary">
        {row.what}
        {row.note && <div className="text-11 text-tertiary leading-snug">{row.note}</div>}
      </td>
      <td className="py-4 pr-12 text-11 font-mono text-tertiary">
        {row.where && (
          <span className="inline-flex items-start gap-2 break-all" title={full}>
            {row.where}
            <CopyButton text={full} title={t('Copy path')} size={10} />
          </span>
        )}
      </td>
      <td className="py-4 text-11 font-mono text-tertiary">{row.evidence}</td>
    </tr>
  )
}
