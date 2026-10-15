import { copyText } from '../../lib/useCopy'
import { TH } from '../../components/ui'
import { Fragment, useMemo, useState } from 'react'
import { Archive, ArchiveRestore, CheckCircle2, Copy, AlertTriangle, XCircle } from 'lucide-react'
import { toast } from 'sonner'

import { Confirm as SharedConfirm } from '../../components/Confirm'
import { Button } from '../../components/primitives'
import { fail } from '../../lib/getJson'
import { FIELD, LABEL } from '../promptlib/taskstyle'
import { VersionDiff } from '../promptlib/runs'
import { lineDiff } from '../prompts/diff'
import { useIntegrateTargets } from '../visions/data'
import { ContextFold, VersionPills } from '../visions/parts'
import { stamp, whoOf } from '../visions/time'
import {
  ALL_PROJECTS, awaitingDraft, hasErrors, skillTitle, useSkillCopy,
  type InstallResult, type Skill, type SkillInstall, type SkillWrites,
} from './data'
import { isExample } from '../visions/data'
import { SkillFieldsForm, fieldsOk } from './fields'
import { FilesFold, filesLabel } from './files'
import { buildSkillMd, fieldsEqual, splitSkillMd } from './frontmatter'
import { requestLine } from './notwritten'
import { AgentName } from '../../components/AgentName'
import { t, tn } from '../../i18n/scope/system'

/**
 * The opened skill. The projects come before the text, because installing is
 * what the operator acts on; All projects writes the home folders every agent
 * reads; the name and the description are fields, not a YAML block, checked
 * the way the server checks them; an older version shows what it changed;
 * Overwrite and Remove ask first, since both take a copy off the disk.
 */

function Heading({ children }: { children: string }) {
  return (
    <div className="flex items-center gap-12">
      <h2 className={LABEL}>{children}</h2>
      <span className="h-1 flex-1 bg-border-subtle" />
    </div>
  )
}

function StatusActions({ s, writes }: { s: Skill; writes: SkillWrites }) {
  const set = (status: string, done: string) =>
    writes.setFields.mutate({ id: s.row.id, status }, { onSuccess: () => toast.success(done), onError: fail })
  const status = s.row.status ?? 'draft'
  const busy = writes.setFields.isPending
  if (status === 'archived') {
    return (
      <Button size="sm" variant="secondary" disabled={busy} onClick={() => set('active', t('Restored'))}
        iconLeft={<ArchiveRestore size={12} aria-hidden />}>{t('Restore')}</Button>
    )
  }
  return (
    <div className="flex items-center gap-8">
      {status === 'draft' && s.current && (
        <Button size="sm" variant="primary" disabled={busy} onClick={() => set('active', t('The skill is active'))}>
          {t('Make active')}
        </Button>
      )}
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => set('archived', t('Archived'))}
        iconLeft={<Archive size={12} aria-hidden />}>{t('Archive')}</Button>
    </div>
  )
}

/** The skill as fields: name, description, steps, and the files beside them. */
function Editor({ s, writes }: { s: Skill; writes: SkillWrites }) {
  const current = s.current!
  const versions = s.kept?.versions ?? []
  const start = useMemo(() => splitSkillMd(current.skill_md), [current.skill_md])
  const [viewing, setViewing] = useState(current.n)
  const [fields, setFields] = useState(start)
  const [note, setNote] = useState('')
  const md = buildSkillMd(fields)
  // Compared as fields, so a file whose head is spelt differently is not "changed" until it is.
  const dirty = !fieldsEqual(fields, start)
  const old = viewing !== current.n ? versions.find((v) => v.n === viewing) : undefined
  const before = old ? versions.find((v) => v.n === old.n - 1) : undefined
  const shown = versions.find((v) => v.n === (old ? viewing : current.n))

  const save = () =>
    writes.draft.mutate(
      { id: s.row.id, skill_md: md, files: current.files, note },
      {
        onSuccess: (d) => { toast.success(t('Saved as version {n}', { n: d.skill?.current?.n ?? current.n + 1 })); setNote('') },
        onError: fail,
      },
    )

  return (
    <section aria-label="SKILL.md" className="flex flex-col gap-8">
      <Heading>SKILL.md</Heading>
      <div className="flex items-center gap-8 flex-wrap text-11 font-mono text-tertiary">
        <span className="shrink-0 inline-flex">
          <VersionPills versions={versions} value={viewing} onChange={setViewing} />
        </span>
        {shown && (
          <span>
            v{shown.n} · {whoOf(shown)} · {stamp(shown.at)}
            {shown.note && <span className="text-secondary"> · {shown.note}</span>}
          </span>
        )}
        <button type="button" className="ml-auto inline-flex items-center gap-4 hover:text-brand"
          onClick={() => { void copyText(old ? old.text : md) }}>
          <Copy size={12} aria-hidden /> {t('Copy SKILL.md')}
        </button>
      </div>

      {old ? (
        <div className="flex flex-col gap-6">
          {before ? (
            <>
              <p className="text-11 font-mono text-tertiary">{t('What v{a} changed from v{b}', { a: old.n, b: before.n })}</p>
              <VersionDiff before={before} after={old} />
            </>
          ) : (
            <p className="text-11 font-mono text-tertiary">{t('The first version.')}</p>
          )}
          <pre className="max-h-[480px] overflow-auto rounded-input border border-border-subtle bg-base px-12 py-10 text-12 font-mono text-secondary whitespace-pre-wrap break-words">
            {old.text}
          </pre>
          <Button variant="link" size="bare" className="self-start text-11 font-mono" onClick={() => setViewing(current.n)}>
            {t('Back to v{n}', { n: current.n })}
          </Button>
        </div>
      ) : (
        <>
          <SkillFieldsForm id={s.row.id} fields={fields} onChange={setFields} />
          {fields.extra && (
            <p className="text-10 font-mono text-tertiary whitespace-pre-wrap break-words" title={t('Other header lines, unchanged')}>
              {fields.extra}
            </p>
          )}

          <FilesFold files={current.files} skillMd={md} />

          {dirty && (
            <div className="flex items-end gap-8 flex-wrap">
              <div className="flex flex-col gap-3 flex-1 min-w-[200px]">
                <label className={LABEL} htmlFor={`skill-note-${s.row.id}`}>{t('why it changed')}</label>
                <input id={`skill-note-${s.row.id}`} value={note} onChange={(e) => setNote(e.target.value)}
                  placeholder={t('Optional')} className={FIELD} />
              </div>
              <Button size="sm" variant="primary" onClick={save} disabled={writes.draft.isPending || !fieldsOk(fields)}>
                {t('Save as v{n}', { n: current.n + 1 })}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setFields(start); setNote('') }}>
                {t('Cancel')}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}

function Checks({ s }: { s: Skill }) {
  const sorted = [...s.checks].sort((a, b) => (a.level === b.level ? 0 : a.level === 'error' ? -1 : 1))
  return (
    <section aria-label={t('Checks')} className="flex flex-col gap-8">
      <Heading>{t('Checks')}</Heading>
      {sorted.length === 0 ? (
        <p className="text-12 text-secondary inline-flex items-center gap-6">
          <CheckCircle2 size={14} className="text-status-green" aria-hidden /> {t('No problems found.')}
        </p>
      ) : (
        <ul className="flex flex-col gap-4">
          {sorted.map((c) => (
            <li key={c.text} className="flex items-start gap-6 text-12 text-primary">
              {c.level === 'error'
                ? <XCircle size={14} className="text-status-red shrink-0 mt-[2px]" aria-label={t('Error')} />
                : <AlertTriangle size={14} className="text-status-amber shrink-0 mt-[2px]" aria-label={t('Warning')} />}
              <span>{c.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

const STATE: Record<SkillInstall['status'] | 'none', [string, string]> = {
  fresh: [t('Installed'), 'text-status-green'],
  stale: [t('Older copy'), 'text-status-amber'],
  changed: [t('Changed on disk'), 'text-status-amber'],
  missing: [t('Copy missing'), 'text-status-red'],
  none: [t('Not installed'), 'text-tertiary'],
}

interface Place {
  project: string
  title: string
  path: string
}

/** What a copy on disk holds that the current version does not. */
function ChangedCopy({ s, project }: { s: Skill; project: string }) {
  const copy = useSkillCopy(s.row.id, project)
  if (copy.isLoading) return <p className="text-11 font-mono text-tertiary">{t('Reading the copy.')}</p>
  if (copy.isError || !copy.data) return <p className="text-11 font-mono text-status-red">{t('Could not read the copy.')}</p>
  const mine: Record<string, string> = { 'SKILL.md': s.current?.skill_md ?? '', ...(s.current?.files ?? {}) }
  const theirs: Record<string, string> = { 'SKILL.md': copy.data.skill_md, ...copy.data.files }
  return (
    <div className="flex flex-col gap-8">
      <p className="text-11 font-mono text-tertiary break-all">
        {copy.data.path} · <span className="text-brand">+</span> {t('on disk')} · <span className="line-through">−</span> {t('in Slightly Parallel v{n}', { n: s.current?.n ?? '' })}
      </p>
      {copy.data.differs.map((path) => {
        const rows = lineDiff(mine[path] ?? '', theirs[path] ?? '').filter((r) => r.type !== 'same')
        return (
          <div key={path} className="flex flex-col gap-2">
            <span className="text-11 font-mono text-primary">{path}</span>
            <pre className="text-11 font-mono rounded-input border border-border-subtle bg-base p-8 overflow-x-auto">
              {rows.slice(0, 20).map((r, i) => (
                <div key={i} className={r.type === 'add' ? 'text-brand' : 'text-tertiary line-through'}>
                  {r.type === 'add' ? '+ ' : '- '}{r.text || ' '}
                </div>
              ))}
              {rows.length > 20 && <div className="text-tertiary">… {tn(rows.length - 20, '{n} more line', '{n} more lines')}</div>}
            </pre>
          </div>
        )
      })}
    </div>
  )
}

/** What the operator is about to do to a copy on disk, said before it happens. */
interface Ask {
  project: string
  what: 'overwrite' | 'remove'
}

/** The line under the buttons after Overwrite or Remove, then the two buttons. Same shape as deleting a set. */
function Confirm({ ask, s, changed, busy, onYes, onNo }: {
  ask: Ask
  s: Skill
  changed: boolean
  busy: boolean
  onYes: () => void
  onNo: () => void
}) {
  const where = nameOf(ask.project)
  const text = ask.what === 'overwrite'
    ? t('Replace the copy in {where} with v{n}. The edits on disk are lost.', { where, n: s.current?.n ?? '' })
    : changed
      ? t('Remove {name} from {where}. The copy was edited on disk; the edits are lost.', { name: skillTitle(s), where })
      : t('Remove {name} from {where}. The folders are deleted.', { name: skillTitle(s), where })
  return (
    <SharedConfirm text={text} action={ask.what === 'overwrite' ? t('Overwrite') : t('Remove')}
      busy={busy} onYes={onYes} onNo={onNo} />
  )
}

function Projects({ s, writes }: { s: Skill; writes: SkillWrites }) {
  const targetsData = useIntegrateTargets().data
  const targets = useMemo(() => targetsData ?? [], [targetsData])
  const [preview, setPreview] = useState<InstallResult | null>(null)
  const [diffOf, setDiffOf] = useState('')
  const [ask, setAsk] = useState<Ask | null>(null)
  /** The server's refusal, shown under the row it answers. */
  const [problem, setProblem] = useState<{ project: string; text: string } | null>(null)
  const id = s.row.id
  // An example shows what the page does. The server refuses to write one
  // into a project, so the page does not offer it either.
  const example = isExample(s.row)
  const blocked = !s.current || hasErrors(s) || example
  const files = filesLabel(Object.keys(s.current?.files ?? {}).length)

  const refused = (project: string) => (e: unknown) => setProblem({ project, text: String((e as Error).message) })
  const install = (project: string, done: string, force = false) => {
    setProblem(null)
    writes.install.mutate({ id, project, force }, {
      onSuccess: (r) => { toast.success(r.action === 'unchanged' ? t('Already current') : done); setPreview(null); setAsk(null) },
      onError: refused(project),
    })
  }
  const remove = (project: string, force = false) => {
    setProblem(null)
    writes.uninstall.mutate({ id, project, force }, {
      onSuccess: () => { toast.success(t('Removed from {where}', { where: nameOf(project) })); setAsk(null) },
      onError: refused(project),
    })
  }
  const keep = (project: string) => {
    setProblem(null)
    writes.keepDisk.mutate({ id, project }, {
      onSuccess: () => toast.success(t('Saved the copy on disk as a new version')),
      onError: refused(project),
    })
  }
  const preview_ = (project: string) => {
    setProblem(null)
    writes.preview.mutate({ id, project }, { onSuccess: setPreview, onError: refused(project) })
  }

  const rows: Place[] = useMemo(() => {
    const all = s.installs.find((i) => i.project === ALL_PROJECTS)
    const names = new Set([ALL_PROJECTS, ...targets.map((t) => t.project)])
    return [
      { project: ALL_PROJECTS, title: t('All projects'), path: all?.path ?? t('every agent on this machine') },
      ...targets.map((t) => ({ project: t.project, title: t.project, path: t.path })),
      ...s.installs.filter((i) => !names.has(i.project)).map((i) => ({ project: i.project, title: i.project, path: i.path })),
    ]
  }, [targets, s.installs])

  const link = 'text-11 font-mono disabled:no-underline'
  const busy = writes.install.isPending || writes.uninstall.isPending || writes.keepDisk.isPending
  return (
    <section aria-label={t('Projects')} className="flex flex-col gap-8">
      <Heading>{t('Projects')}</Heading>
      {example && (
        <p className="text-11 text-secondary">{t('This is an example. Install is off.')}</p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-12">
          <tbody className="divide-y divide-border-subtle">
            {rows.map(({ project, title, path }) => {
              const inst = s.installs.find((i) => i.project === project)
              const [label, tone] = STATE[inst?.status ?? 'none']
              const all = project === ALL_PROJECTS
              const differs = inst?.status === 'changed' ? inst.differs : []
              const asked = ask?.project === project ? ask : null
              return (
                <Fragment key={project}>
                <tr className="align-top">
                  <td className="py-6 pr-12 w-[160px]">
                    <div className={all ? 'text-primary' : 'font-mono text-primary'}>{title}</div>
                    <div className="text-10 font-mono text-tertiary truncate max-w-[220px]" title={path}>
                      {all ? t('every agent on this machine') : path}
                    </div>
                  </td>
                  <td className={`py-6 pr-12 font-mono text-11 ${tone}`}>
                    <div className="flex flex-col gap-2">
                      <span>
                        {label}{inst && inst.status !== 'missing' ? ` · v${inst.version}` : ''}
                        {/* The count describes the copy, so a project without one does not carry it. */}
                        {files && inst && inst.status !== 'missing' ? ` · ${files}` : ''}
                        {differs.length > 0 && ` · ${tn(differs.length, '{n} file differs', '{n} files differ')}`}
                      </span>
                      {differs.length > 0 && (
                        <>
                          <span className="text-10 text-secondary break-all">{differs.join(', ')}</span>
                          <Button variant="link" size="bare" className="self-start text-10 font-mono"
                            onClick={() => setDiffOf((c) => (c === project ? '' : project))}>
                            {diffOf === project ? t('Hide what changed') : t('What changed')}
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                  <td className="py-6">
                    <div className="flex items-center gap-12 justify-end flex-wrap">
                      {!inst && (
                        <Button variant="link" size="bare" className={link} disabled={blocked || writes.preview.isPending}
                          title={example ? t('Install is off for examples.') : blocked ? t('Fix the errors in Checks first.') : undefined}
                          onClick={() => preview_(project)}>
                          {t('Install')}
                        </Button>
                      )}
                      {inst?.status === 'stale' && (
                        <Button variant="link" size="bare" className={link} disabled={blocked || busy}
                          onClick={() => install(project, t('Updated in {where}', { where: nameOf(project) }))}>{t('Update')}</Button>
                      )}
                      {inst?.status === 'missing' && (
                        <Button variant="link" size="bare" className={link} disabled={blocked || busy}
                          onClick={() => install(project, t('Installed in {where}', { where: nameOf(project) }))}>{t('Install again')}</Button>
                      )}
                      {inst?.status === 'changed' && (
                        <>
                          <Button variant="link" size="bare" className={link} disabled={busy} onClick={() => keep(project)}>{t('Keep this copy')}</Button>
                          <Button variant="link" size="bare" className={link} disabled={busy || !!asked}
                            onClick={() => setAsk({ project, what: 'overwrite' })}>{t('Overwrite')}</Button>
                        </>
                      )}
                      {inst && (
                        <Button variant="danger-text" size="bare" disabled={busy || !!asked}
                          onClick={() => setAsk({ project, what: 'remove' })}>{t('Remove')}</Button>
                      )}
                    </div>
                  </td>
                </tr>
                {(asked || problem?.project === project) && (
                  <tr>
                    <td colSpan={3} className="pb-8">
                      <div className="flex flex-col gap-6">
                        {asked && (
                          <Confirm ask={asked} s={s} changed={inst?.status === 'changed'} busy={busy}
                            onNo={() => setAsk(null)}
                            onYes={() => (asked.what === 'overwrite'
                              ? install(project, t('Overwrote the copy in {where}', { where: nameOf(project) }), true)
                              : remove(project, true))} />
                        )}
                        {problem?.project === project && (
                          <p role="alert" className="text-11 text-status-red whitespace-pre-wrap break-words">{problem.text}</p>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
                {diffOf === project && differs.length > 0 && (
                  <tr>
                    <td colSpan={3} className="pb-10">
                      <ChangedCopy s={s} project={project} />
                    </td>
                  </tr>
                )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      {preview && (
        <div className="rounded-input border border-border-subtle bg-elevated px-12 py-10 flex flex-col gap-6">
          <p className="text-12 text-primary">
            {preview.action === 'changed'
              ? <>{t('The copy in {where} was edited on disk. Install replaces it with', { where: nameOf(preview.project) })} <span className="font-mono">{skillTitle(s)}</span> v{preview.version}:</>
              : <>{t('Install writes')} <span className="font-mono">{skillTitle(s)}</span> {t('v{n} into {where}:', { n: preview.version, where: nameOf(preview.project) })}</>}
          </p>
          <ul className="flex flex-col gap-2">
            {preview.paths.map((p) => <li key={p} className="text-11 font-mono text-secondary break-all">{p}</li>)}
          </ul>
          <div className="flex items-center gap-8">
            <Button size="sm" variant="primary" disabled={writes.install.isPending}
              onClick={() => install(preview.project, t('Installed in {where}', { where: nameOf(preview.project) }), preview.action === 'changed')}>
              {preview.action === 'changed' ? t('Overwrite') : t('Install')}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPreview(null)}>{t('Cancel')}</Button>
          </div>
        </div>
      )}
    </section>
  )
}

const nameOf = (project: string) => (project === ALL_PROJECTS ? t('all projects') : project)

function Used({ s }: { s: Skill }) {
  const u = s.usage
  const [all, setAll] = useState(false)
  const sessions = u?.sessions ?? []
  const list = all ? sessions : sessions.slice(0, 8)
  return (
    <section aria-label={t('Used')} className="flex flex-col gap-8">
      <Heading>{t('Used')}</Heading>
      {!u || u.uses === 0 ? (
        <p className="text-12 text-tertiary">{t('Not used yet.')}</p>
      ) : (
        <>
          <p className="text-12 text-secondary">
            {tn(u.uses, '{n} time', '{n} times')}
            {' · '}{t('{n} in the last {days} days', { n: u.recent, days: u.days })}
            {' · '}{t('last used {date}', { date: stamp(u.last_used) })}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-11 font-mono">
              <thead>
                <tr className={`text-left ${TH}`}>
                  <th className="font-normal py-3 pr-12">{t('When')}</th>
                  <th className="font-normal py-3 pr-12">{t('Project')}</th>
                  <th className="font-normal py-3 pr-12">{t('Agent')}</th>
                  <th className="font-normal py-3 pr-12">{t('Message')}</th>
                  <th className="font-normal py-3">{t('How')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle text-secondary">
                {list.map((x, i) => (
                  <tr key={`${x.at}-${i}`}>
                    <td className="py-3 pr-12 whitespace-nowrap">{stamp(x.at)}</td>
                    <td className="py-3 pr-12">{x.project || '—'}</td>
                    <td className="py-3 pr-12"><AgentName id={x.agent_id} /></td>
                    <td className="py-3 pr-12 tabular">{x.turn || '—'}</td>
                    <td className="py-3">{x.how === 'typed' ? t('typed /{name}', { name: skillTitle(s) }) : t('chosen by the agent')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {sessions.length > 8 && (
            <Button variant="link" size="bare" className="self-start text-11 font-mono" onClick={() => setAll((v) => !v)}>
              {all ? t('Show fewer') : t('Show all {n}', { n: sessions.length })}
            </Button>
          )}
        </>
      )}
    </section>
  )
}

function KeptFrom({ s }: { s: Skill }) {
  const kept = s.kept
  if (!kept?.message) return null
  return (
    <section aria-label={t('Kept from')} className="flex flex-col gap-8">
      <Heading>{t('Kept from')}</Heading>
      <p className="text-10 font-mono text-tertiary">
        {s.row.project || t('No project')} · <AgentName id={s.row.agent_id} /> · {stamp(`${s.row.created_date} ${s.row.created_time}`)}
      </p>
      <blockquote className="border-l-2 border-brand pl-10 text-13 text-primary whitespace-pre-wrap break-words">
        {kept.message}
      </blockquote>
      <ContextFold kept={kept} defaultOpen={awaitingDraft(s)} />
    </section>
  )
}

/** The one line an agent needs to write the draft for a skill still waiting. */
function Waiting({ s }: { s: Skill }) {
  const request = requestLine(s.row.id)
  return (
    <div className="flex flex-col gap-8">
      <p className="text-13 text-secondary">{t('No draft from the agent yet.')}</p>
      <div className="flex items-center gap-8">
        <Button size="sm" variant="secondary" iconLeft={<Copy size={12} aria-hidden />}
          onClick={() => { void copyText(request) }}>
          {t('Copy the request')}
        </Button>
        <span className="text-11 text-tertiary">{t('Paste it into a message to an agent in this project.')}</span>
      </div>
    </div>
  )
}

export function SkillView({ s, writes }: { s: Skill; writes: SkillWrites }) {
  const waiting = awaitingDraft(s)
  return (
    <article className="flex flex-col gap-24 min-w-0">
      <header className="flex items-start gap-12 flex-wrap">
        <div className="flex flex-col gap-4 flex-1 min-w-0">
          <h2 className={`text-20 text-primary leading-tight break-words ${waiting ? '' : 'font-mono'}`}>
            {waiting ? t('New skill from a message') : skillTitle(s)}
          </h2>
          <p className="text-10 font-mono text-tertiary">
            {t(s.row.status ?? 'draft')} · {s.row.id}
            {s.current && ` · ${tn(s.current.n, '{n} version', '{n} versions')}`}
          </p>
        </div>
        {/* A request with no draft can still be archived, which takes it out of "Not written". */}
        <StatusActions s={s} writes={writes} />
      </header>

      {waiting ? (
        <>
          <Waiting s={s} />
          <KeptFrom s={s} />
        </>
      ) : (
        <>
          <Projects s={s} writes={writes} />
          <Checks s={s} />
          <Editor key={`${s.row.id}-${s.current!.hash}`} s={s} writes={writes} />
          <Used s={s} />
          <KeptFrom s={s} />
        </>
      )}
    </article>
  )
}
