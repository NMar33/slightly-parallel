/**
 * The cards a click on a record's id opens over the terminal (tk_b3edbd84):
 * a decision, a Publish card, a core, a skill, an entry point, a chat (its
 * agent id) and a commit (its hash). Each shows what its page shows of it,
 * read through that page's route (records.ts), and offers what the page
 * offers the operator; «Открыть …» opens the record on its page. Esc or a
 * click outside closes (MessageLayer).
 */

import { useState, type CSSProperties, type ReactNode } from 'react'
import { Copy, CornerDownRight, Download, ExternalLink, FileDiff, GitBranch, MessageSquarePlus, RotateCcw, SquareTerminal, X } from 'lucide-react'

import { Markdown } from '../../../components/Markdown'
import { writeClipboard } from '../../../lib/useCopy'
import { getJson, postJson } from '../../../lib/getJson'
import { useAquaActions, useSessions } from '../../aqua/app/api'
import { openWindow } from '../../aqua/app/bridge'
import { detachUrl, shownOf } from '../../aqua/app/model'
import { useTabInfo } from '../../aqua/app/tabs/facts'
import { coreColor, useCoreWrites } from '../../architecture/cores/data'
import { chooseCoresMode } from '../../architecture/page/mode'
import { t, tn } from '../../../i18n/scope/msgmenu'
import type { IdKind } from './ids'
import { Action, copyId, DIM, FG, openPage, Part, placeCard, RecordCard } from './pop'
import {
  coreView, pageOf, useAgentCard, useAgentTasks, useCommit, useCommitDiff, useCoreCard, useDecision, useEntryCard,
  usePublishCard, useSkillCard,
} from './records'

export interface CardProps {
  id: string
  x: number
  y: number
  /** The layer's size: the card stays inside it. */
  w: number
  h: number
  /** The terminal's project: a commit is of its repository, a skill installs into it. */
  project: string
  say: (s: string) => void
  close: () => void
  /** Another id named in a card (a task of a core, a commit's Task: line): its own card or menu. */
  onId: (id: string, kind: IdKind) => void
}

const run = (say: (s: string) => void, fn: () => Promise<unknown>) => {
  void fn().catch((e: unknown) => say(t('Could not do it: {error}', { error: e instanceof Error ? e.message : String(e) })))
}

/** "2611-18" → "18.11.2026"; an ISO stamp → its day and minute. */
export function when(day: string, time = ''): string {
  const m = /^(\d{2})(\d{2})-(\d{2})$/.exec(day)
  if (m) return `${m[3]}.${m[2]}.20${m[1]}${time ? ` ${time.slice(0, 5)}` : ''}`
  const iso = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}:\d{2}))?/.exec(day)
  if (iso) return `${iso[3]}.${iso[2]}.${iso[1]}${iso[4] ? ` ${iso[4]}` : ''}`
  return day
}

function Status({ q, missing }: { q: { isLoading: boolean; isError: boolean }; missing: string }) {
  return <p className="m-0 text-12" style={DIM}>{q.isLoading ? t('Reading…') : q.isError ? missing : ''}</p>
}

function Chip({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <span className="aq-chip" style={style}>{children}</span>
}

/** An id inside a card, itself a link. */
function IdLink({ id, kind, onId, title }: { id: string; kind: IdKind; onId: CardProps['onId']; title?: string }) {
  return (
    <button type="button" className="lab-mark task font-mono" title={title} data-id={id} onClick={() => onId(id, kind)}>{id}</button>
  )
}

const copyRow = (id: string, say: CardProps['say'], label = t('Copy the id')) => (
  <Action icon={<Copy size={15} />} label={label} onClick={() => { void copyId(id, say) }} />
)

/* ------------------------------------------------------------ a decision */

export function DecisionCard(p: CardProps) {
  const q = useDecision(p.id)
  const d = q.data
  return (
    <RecordCard label={t('Decision')} id={p.id} style={placeCard(p.x, p.y, 380, p.w, p.h)} close={p.close}
      chips={d?.weight ? <Chip>{d.weight}</Chip> : null}
      actions={<>
        <Action icon={<ExternalLink size={15} />} label={t('Open on the Decisions page')} disabled={!d}
          onClick={() => { p.close(); openPage(pageOf.decision(d!.project, d!.day)) }} />
        {copyRow(p.id, p.say)}
      </>}>
      {!d ? <Status q={q} missing={t('No such decision')} /> : (
        <>
          <b className="text-13 leading-snug" style={FG}>{d.decision}</b>
          {d.why && <Part title={t('Why')}><p className="m-0 text-11 leading-snug whitespace-pre-wrap" style={FG}>{d.why}</p></Part>}
          {d.rejected.length > 0 && (
            <Part title={t('Rejected')}>
              <ul className="m-0 pl-14 text-11 leading-snug flex flex-col gap-2" style={FG}>
                {d.rejected.map((a, i) => <li key={i}>{a.option}{a.reason && <span style={DIM}> — {a.reason}</span>}</li>)}
              </ul>
            </Part>
          )}
          <span className="text-11" style={DIM}>{[when(d.day, d.time), d.project, d.agent].filter(Boolean).join(' · ')}</span>
        </>
      )}
    </RecordCard>
  )
}

/* ------------------------------------------------------------ a Publish card */

export function PublishCard(p: CardProps) {
  const q = usePublishCard(p.id)
  const d = q.data
  return (
    <RecordCard label={t('Publish card')} id={p.id} style={placeCard(p.x, p.y, 380, p.w, p.h)} close={p.close}
      chips={d ? <Chip>{d.project}</Chip> : null}
      actions={<>
        <Action icon={<ExternalLink size={15} />} label={t('Open on the Publish page')} disabled={!d}
          onClick={() => { p.close(); openPage(pageOf.publish(d!.project)) }} />
        {copyRow(p.id, p.say)}
      </>}>
      {!d ? <Status q={q} missing={t('No such Publish card')} /> : (
        <>
          <p className="m-0 text-12 leading-snug whitespace-pre-wrap" style={FG}>{d.text || t('(no text)')}</p>
          {d.context && <Part title={t('Context')}><p className="m-0 text-11 leading-snug whitespace-pre-wrap" style={FG}>{d.context}</p></Part>}
          <span className="text-11" style={DIM}>
            {[when(d.at), tn(d.attachments, '{n} attachment', '{n} attachments'), d.placed ? tn(d.placed, 'in {n} document', 'in {n} documents') : ''].filter(Boolean).join(' · ')}
          </span>
        </>
      )}
    </RecordCard>
  )
}

/* ------------------------------------------------------------ a core */

export function CoreCard(p: CardProps) {
  const q = useCoreCard(p.id)
  const d = q.data ? coreView(q.data) : null
  const writes = useCoreWrites(d?.project ?? '', p.id)
  const [writing, setWriting] = useState(false)
  const [text, setText] = useState('')
  const save = () => {
    const body = text.trim()
    if (!body) return
    writes.note.mutate({ text: body }, {
      onSuccess: () => { setText(''); setWriting(false); p.say(t('Note added to {name}', { name: d?.name ?? p.id })) },
      onError: (e) => p.say(t('Could not do it: {error}', { error: e instanceof Error ? e.message : String(e) })),
    })
  }
  return (
    <RecordCard label={t('Core')} id={p.id} style={placeCard(p.x, p.y, 400, p.w, p.h)} close={p.close}
      chips={d ? <>
        <Chip style={{ color: coreColor(d.type) }}>{d.type}</Chip>
        {d.off && <Chip>{t('out of view')}</Chip>}
      </> : null}
      actions={<>
        {d && !d.off && !writing && <Action icon={<MessageSquarePlus size={15} />} label={t('Add a note')} onClick={() => setWriting(true)} />}
        <Action icon={<ExternalLink size={15} />} label={t('Open in Architecture › cores')} disabled={!d}
          onClick={() => { p.close(); chooseCoresMode(); openPage(pageOf.core(d!.project, p.id)) }} />
        {copyRow(p.id, p.say)}
      </>}>
      {!d ? <Status q={q} missing={t('No such core')} /> : (
        <>
          <b className="text-13 leading-snug" style={FG}>{d.name}</b>
          {d.reason && <p className="m-0 text-11 leading-snug whitespace-pre-wrap" style={FG}>{d.reason}</p>}
          {d.notes.length > 0 && (
            <Part title={`${t('Last notes')} · ${d.notesN}`}>
              {d.notes.map((n) => (
                <div key={n.id} className="text-11 leading-snug">
                  <span style={DIM}>{when(n.at)} · {n.author} </span>
                  <span className="whitespace-pre-wrap line-clamp-3" style={FG}>{n.text}</span>
                </div>
              ))}
            </Part>
          )}
          {d.tasks.length > 0 && (
            <Part title={tn(d.tasks.length, '{n} task', '{n} tasks')}>
              <div className="flex flex-wrap gap-4">{d.tasks.slice(0, 12).map((x) => <IdLink key={x.id} id={x.id} kind="task" onId={p.onId} title={`${x.title} · ${x.status}`} />)}</div>
            </Part>
          )}
          {writing && (
            <div className="flex flex-col gap-4">
              <textarea autoFocus aria-label={t('The note')} rows={3} value={text} onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save() } }}
                className="w-full rounded-input text-12 p-6 resize-y"
                style={{ background: 'color-mix(in srgb, var(--aq-term-fg) 6%, transparent)', color: 'var(--aq-term-fg)', border: '1px solid var(--aq-term-frame)' }} />
              <div className="flex gap-6 justify-end">
                <button type="button" className="lab-pill" onClick={() => { setWriting(false); setText('') }}>{t('Cancel')}</button>
                <button type="button" className="lab-pill" data-on disabled={!text.trim() || writes.note.isPending} onClick={save}>{t('Save')}</button>
              </div>
            </div>
          )}
        </>
      )}
    </RecordCard>
  )
}

/* ------------------------------------------------------------ a skill */

/** A skill reads like a note: SKILL.md rendered in a panel of its own over the terminal, scrolled inside. */
export function SkillCard(p: CardProps) {
  const q = useSkillCard(p.id)
  const d = q.data
  const [installing, setInstalling] = useState(false)
  const canInstall = !!d && !!p.project && d.version > 0 && d.status !== 'archived' && !d.installedIn.includes(p.project)
  const install = () => run(p.say, async () => {
    setInstalling(true)
    try {
      await postJson(`/api/skills/${encodeURIComponent(p.id)}/install`, { project: p.project, actor: 'operator' })
      p.say(t('{name} installed in {project}', { name: d!.name, project: p.project }))
      await q.refetch()
    } finally { setInstalling(false) }
  })
  return (
    <div className="mm-pop absolute inset-0 z-30 flex items-start justify-center p-16" style={{ background: 'color-mix(in srgb, var(--term-ground) 55%, transparent)' }}
      onPointerDown={(e) => { if (e.target === e.currentTarget) p.close() }}>
      <div role="dialog" aria-label={`${t('Skill')} ${p.id}`} data-record={t('Skill')}
        className="relative w-full max-w-[760px] max-h-full flex flex-col rounded-card border border-border-default shadow-lg outline-none"
        style={{ background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
        <div className="shrink-0 flex items-center gap-8 px-14 h-[34px] text-12" style={{ borderBottom: '1px solid var(--border-default)' }}>
          <span className="font-mono text-tertiary">{p.id}</span>
          {d && <b className="truncate">{d.name}</b>}
          {d && <span className="text-11 text-tertiary">{d.status}{d.version ? ` · v${d.version}` : ''}</span>}
          <span className="text-11 text-tertiary">{t('Esc closes')}</span>
          <button type="button" className="ml-auto inline-flex items-center justify-center w-[24px] h-[24px] rounded-input hover:bg-hover" aria-label={t('Close')} onClick={p.close}><X size={13} /></button>
        </div>
        <div className="flex-1 min-h-0 overflow-auto px-20 py-16 flex flex-col gap-10" data-testid="skill-md">
          {!d ? <p className="m-0 text-13 text-tertiary">{q.isLoading ? t('Reading…') : t('No such skill')}</p> : (
            <>
              {d.description && <p className="m-0 text-13 text-secondary leading-relaxed">{d.description}</p>}
              {d.installedIn.length > 0 && <p className="m-0 text-11 text-tertiary">{t('Installed in: {projects}', { projects: d.installedIn.join(', ') })}</p>}
              {d.body ? <Markdown text={d.body} /> : <p className="m-0 text-13 text-tertiary">{t('No SKILL.md yet: a draft.')}</p>}
            </>
          )}
        </div>
        <div className="shrink-0 flex items-center gap-8 px-14 py-6 text-12" style={{ borderTop: '1px solid var(--border-default)' }}>
          <button type="button" className="inline-flex items-center gap-4 px-8 h-[24px] rounded-input hover:bg-hover" disabled={!d}
            onClick={() => { p.close(); openPage(pageOf.skill(p.id)) }}><ExternalLink size={13} />{t('Open on the Skills page')}</button>
          {canInstall && (
            <button type="button" className="inline-flex items-center gap-4 px-8 h-[24px] rounded-input hover:bg-hover" disabled={installing}
              onClick={install}><Download size={13} />{t('Install in {project}', { project: p.project })}</button>
          )}
          <button type="button" className="inline-flex items-center gap-4 px-8 h-[24px] rounded-input hover:bg-hover ml-auto"
            onClick={() => { void copyId(p.id, p.say) }}><Copy size={13} />{t('Copy the id')}</button>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------ an entry point */

export function EntryCard(p: CardProps) {
  const q = useEntryCard(p.id)
  const d = q.data
  return (
    <RecordCard label={t('Entry point')} id={p.id} style={placeCard(p.x, p.y, 400, p.w, p.h)} close={p.close}
      chips={d ? <><Chip>{d.state}</Chip>{d.project && <Chip>{d.project}</Chip>}</> : null}
      actions={<>
        <Action icon={<ExternalLink size={15} />} label={t('Open on the Entry points page')} disabled={!d}
          onClick={() => { p.close(); openPage(pageOf.entrypoint(p.id)) }} />
        {copyRow(p.id, p.say)}
      </>}>
      {!d ? <Status q={q} missing={t('No such entry point')} /> : (
        <>
          <b className="text-13 leading-snug" style={FG}>{d.name}</b>
          {d.question && d.question !== d.name && <p className="m-0 text-11 leading-snug" style={DIM}>{d.question}</p>}
          {d.what && <p className="m-0 text-11 leading-snug whitespace-pre-wrap line-clamp-6" style={FG}>{d.what}</p>}
          {d.stops.length > 0 && (
            <Part title={t('Where it stopped')}>
              {d.stops.map((s, i) => (
                <div key={i} className="text-11 leading-snug">
                  <span style={DIM}>{when(s.at)} · {s.author} </span><span className="whitespace-pre-wrap" style={FG}>{s.text}</span>
                </div>
              ))}
            </Part>
          )}
          {d.shots.length > 0 && (
            <Part title={tn(d.shots.length, '{n} screenshot', '{n} screenshots')}>
              <div className="flex gap-6 flex-wrap">
                {d.shots.map((s) => <img key={s.id} src={s.src} alt={s.caption || s.id} title={s.caption} className="h-[64px] w-auto rounded-input" style={{ border: '1px solid var(--aq-term-frame)' }} />)}
              </div>
            </Part>
          )}
          {d.openTasks > 0 && <span className="text-11" style={DIM}>{tn(d.openTasks, '{n} open task', '{n} open tasks')}</span>}
        </>
      )}
    </RecordCard>
  )
}

/* ------------------------------------------------------------ a chat */

export function AgentCard(p: CardProps & { goTo?: (sid: string) => void }) {
  const q = useAgentCard(p.id)
  const d = q.data
  const tasks = useAgentTasks(p.id, d?.project ?? '')
  const aqua = useAquaActions()
  const { sessions } = useSessions()
  const tabs = useTabInfo()
  const live = sessions.find((s) => s.state !== 'ended' && (tabs?.[s.id]?.agent_id || s.agent_id) === p.id)
  const state = live ? shownOf(live) : ''
  const show = (sid: string) => { if (p.goTo) p.goTo(sid); else openWindow(detachUrl('chat', sid)) }
  const resume = () => run(p.say, async () => {
    p.close()
    const s = await aqua.open({ kind: 'resume', agent: p.id, role: 'chat' })
    if (s) { p.say(t('Resumed: {name}', { name: d?.name ?? p.id })); show(s.id) }
  })
  const branch = () => run(p.say, async () => {
    p.close()
    // The command the window's own «Branch» types (GET /api/terminal/branch/{id}), in a window of its own.
    const b = await getJson<{ command: string; project: string; name: string }>(`/api/terminal/branch/${encodeURIComponent(p.id)}`)
    const s = await aqua.open({ kind: 'shell', project: b.project || p.project, label: `${b.name} ⑂`, command: b.command, role: 'chat' })
    if (!s) { p.say(t('The branch did not start: the terminal did not open')); return }
    openWindow(detachUrl('chat', s.id))
    p.say(t('Branch opened in a new window'))
  })
  return (
    <RecordCard label={t('Chat')} id={p.id} style={placeCard(p.x, p.y, 380, p.w, p.h)} close={p.close}
      chips={d ? <>
        {d.tool && <Chip>{d.tool}</Chip>}
        {state && <Chip style={state === 'waiting' ? { color: 'var(--status-amber)' } : undefined}>{STATE_WORD[state] ?? state}</Chip>}
      </> : null}
      actions={<>
        {live && <Action icon={<CornerDownRight size={15} />} label={t('Go to its tab')} onClick={() => { p.close(); show(live.id) }} />}
        {d?.canResume && !live && <Action icon={<RotateCcw size={15} />} label={t('Resume')} onClick={resume} />}
        {d?.canBranch && <Action icon={<GitBranch size={15} />} label={t('Branch into a new window')} onClick={branch} />}
        <Action icon={<SquareTerminal size={15} />} label={t('Open the chat in Slightly Parallel')} disabled={!d}
          onClick={() => { p.close(); openPage(pageOf.agent(p.id)) }} />
        {copyRow(p.id, p.say)}
      </>}>
      {!d ? <Status q={q} missing={t('No such chat')} /> : (
        <>
          <b className="text-13 leading-snug" style={FG}>{d.name}</b>
          <span className="text-11" style={DIM}>
            {[d.project, d.lastActive ? t('last active {when}', { when: when(d.lastActive) }) : '', d.messages ? tn(d.messages, '{n} message', '{n} messages') : ''].filter(Boolean).join(' · ')}
          </span>
          {!live && <span className="text-11" style={DIM}>{t('No terminal of this chat is open.')}</span>}
          {(tasks.data?.length ?? 0) > 0 && (
            <Part title={tn(tasks.data!.length, '{n} task', '{n} tasks')}>
              <div className="flex flex-wrap gap-4">{tasks.data!.slice(0, 12).map((x) => <IdLink key={x.id} id={x.id} kind="task" onId={p.onId} title={x.title} />)}</div>
            </Part>
          )}
        </>
      )}
    </RecordCard>
  )
}

const STATE_WORD: Record<string, string> = {
  working: t('working'), waiting: t('your turn'), asleep: t('asleep'), idle: t('a prompt'), ended: t('ended'),
}

/* ------------------------------------------------------------ a commit */

/** One line of a diff, coloured as git colours it. */
function diffColor(line: string): string | undefined {
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ') || line.startsWith('index ')) return 'var(--aq-term-dim)'
  if (line.startsWith('@@')) return 'var(--ansi-6, var(--aq-term-link))'
  if (line.startsWith('+')) return 'var(--aq-term-ok, var(--ansi-2))'
  if (line.startsWith('-')) return 'var(--ansi-1, #e06c75)'
  return undefined
}

export function CommitCard(p: CardProps) {
  const q = useCommit(p.project, p.id)
  const [diffOn, setDiffOn] = useState(false)
  const diff = useCommitDiff(p.project, p.id, diffOn)
  const d = q.data
  const lines = diff.data?.diff ? diff.data.diff.split('\n') : []
  return (
    <RecordCard label={t('Commit')} id={d?.short ?? p.id} style={placeCard(p.x, p.y, diffOn ? 720 : 420, p.w, p.h)} close={p.close}
      chips={d ? <Chip>{d.project}</Chip> : null}
      actions={<>
        <Action icon={<FileDiff size={15} />} label={diffOn ? t('Hide the changes') : t('Show the changes')} disabled={!d} onClick={() => setDiffOn((v) => !v)} />
        <Action icon={<Copy size={15} />} label={t('Copy the hash')} disabled={!d} onClick={() => {
          void writeClipboard(d!.sha).then((ok) => p.say(ok ? t('Copied {id}', { id: d!.short }) : t('The browser did not allow copying')))
        }} />
      </>}>
      {!d ? <Status q={q} missing={t('Not a commit of {project}', { project: p.project })} /> : (
        <>
          <b className="text-13 leading-snug" style={FG}>{d.subject}</b>
          <span className="text-11" style={DIM}>{[d.author, when(d.at)].filter(Boolean).join(' · ')}</span>
          {(d.tasks.length > 0 || d.agent) && (
            <div className="flex flex-wrap gap-4 items-center">
              {d.tasks.map((x) => <IdLink key={x} id={x} kind="task" onId={p.onId} />)}
              {d.agent && /^(cc|codex|cursor|oc)-[0-9a-z]{8}$/.test(d.agent) && <IdLink id={d.agent} kind="agent" onId={p.onId} />}
            </div>
          )}
          <Part title={`${tn(d.files_n, '{n} file', '{n} files')} · +${d.add} −${d.del}`}>
            <div className="flex flex-col font-mono text-11 overflow-auto max-h-[140px]" data-testid="commit-files">
              {d.files.map((f) => (
                <div key={f.path} className="flex gap-8 whitespace-nowrap">
                  <span className="truncate" style={FG} title={f.path}>{f.path}</span>
                  <span className="ml-auto" style={{ color: 'var(--aq-term-ok, var(--ansi-2))' }}>+{f.add}</span>
                  <span style={{ color: 'var(--ansi-1, #e06c75)' }}>−{f.del}</span>
                </div>
              ))}
            </div>
          </Part>
          {diffOn && (
            <pre role="region" aria-label={t('Changes')} className="m-0 p-6 font-mono text-11 leading-snug overflow-auto max-h-[50vh] rounded-input"
              style={{ background: 'color-mix(in srgb, var(--aq-term-fg) 5%, transparent)', color: 'var(--aq-term-fg)' }}>
              {diff.isLoading ? t('Reading…') : diff.isError ? t('The changes could not be read.') : lines.map((l, i) => (
                <div key={i} style={{ color: diffColor(l) }}>{l || ' '}</div>
              ))}
              {diff.data?.diff_cut && <div style={DIM}>{t('… cut here: the change is too long to show whole.')}</div>}
            </pre>
          )}
        </>
      )}
    </RecordCard>
  )
}
