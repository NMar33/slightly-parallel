import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { toast } from 'sonner'

import { postJson } from '../../lib/getJson'
import { AgentName } from '../../components/AgentName'
import { CopyButton } from '../../components/CopyButton'
import { Markdown } from '../../components/Markdown'
import { Modal } from '../../components/Modal'
import { Segmented } from '../../components/Segmented'
import { Button } from '../../components/primitives'
import { formatStamp } from '../../utils/dateUtils'
import { Changes } from '../visions/chapters'
import { FIELD, LABEL } from '../promptlib/taskstyle'
import { clearDraft, readDraft, writeDraft } from './TasksKanban'
import { t, tn } from '../../i18n/scope/project'

/**
 * A Storyboard document's versions: the finished text that comes back from
 * the pack. An agent posts one with the MCP tool doc_version; the operator
 * pastes one here for an agent without the tool. Newest first, numbered
 * from the first; each opens to be read, copied, and compared with the one
 * before it.
 */

export type Version = { id: string; created_at: string; agent_id: string; body: string; note?: string }
export type Mention = { agent_id: string; session_id: string; turn: number; at: string; role: string; excerpt: string }

/** Who wrote it: you for a pasted version, else the agent, linked to its page. */
function Who({ id, className = '' }: { id: string; className?: string }) {
  if (!id || id === 'operator') return <span className={className}>{t('you')}</span>
  return (
    <Link to={`/agent/${encodeURIComponent(id)}`} className={`${className} hover:text-brand`}>
      <AgentName id={id} />
    </Link>
  )
}

export function DocVersions({ docId, versions, mentions, onSession, onChanged }: {
  docId: string
  /** Newest first, as the server answers. */
  versions: Version[]
  mentions: Mention[]
  onSession: (sessionId: string) => void
  onChanged: () => void
}) {
  const draftKey = `sp-doc-version-draft:${docId}`
  const [open, setOpen] = useState<string | null>(null)
  const [pasting, setPasting] = useState<{ body: string; note: string } | null>(
    () => readDraft<{ body: string; note: string }>(draftKey),
  )
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (pasting && (pasting.body.trim() || pasting.note.trim())) writeDraft(draftKey, pasting)
  }, [pasting, draftKey])

  const n = versions.length
  const numberOf = (i: number) => n - i
  const openIndex = versions.findIndex((v) => v.id === open)

  const save = async () => {
    if (!pasting?.body.trim()) return
    setSaving(true)
    try {
      await postJson(`/api/docs/${encodeURIComponent(docId)}/versions`,
        { body: pasting.body, note: pasting.note, agent_id: 'operator' })
      clearDraft(draftKey)
      setPasting(null)
      toast.success(t('Version {n} saved.', { n: n + 1 }))
      onChanged()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label={t('Versions')} className="border-t border-border-subtle pt-8 flex flex-col gap-6">
      <div className="flex items-center gap-8">
        <span className={LABEL}>
          {t('Versions')} <span className="text-tertiary/70">— {n}</span>
          {mentions.length > 0 && <span className="text-tertiary/70"> {t('· mentioned in {messages}', { messages: tn(mentions.length, '{n} chat message', '{n} chat messages') })}</span>}
        </span>
        {pasting === null && (
          <Button variant="text" size="bare" className="ml-auto" onClick={() => setPasting({ body: '', note: '' })}>{t('+ paste a version')}</Button>
        )}
      </div>

      {pasting !== null && (
        <form onSubmit={(e) => { e.preventDefault(); void save() }} className="rounded-input border border-brand px-8 py-6 flex flex-col gap-6">
          <label className="flex flex-col gap-2">
            <span className={LABEL}>{t('Text')}</span>
            <textarea autoFocus value={pasting.body} rows={8} placeholder={t('The finished document, in markdown')}
              onChange={(e) => setPasting({ ...pasting, body: e.target.value })}
              className="bg-elevated text-primary border border-border-default rounded-input px-8 py-4 text-12 leading-relaxed w-full" />
          </label>
          <label className="flex flex-col gap-2">
            <span className={LABEL}>{t('Note')}</span>
            <input value={pasting.note} placeholder={t('one line: what this version changed')} maxLength={400}
              onChange={(e) => setPasting({ ...pasting, note: e.target.value })} className={FIELD} />
          </label>
          <div className="flex gap-8 items-center text-11 font-mono">
            <span className="mr-auto text-tertiary">{t('Draft saved')}</span>
            <Button variant="text" size="bare" onClick={() => { clearDraft(draftKey); setPasting(null) }}>{t('cancel')}</Button>
            <button type="submit" disabled={!pasting.body.trim() || saving} className="text-brand hover:text-brand-hover disabled:opacity-40">{t('save version')}</button>
          </div>
        </form>
      )}

      {n === 0 && pasting === null && (
        <p className="text-11 text-tertiary leading-relaxed">
          {t('No versions yet. Copy the pack and paste it into an agent\'s chat: the agent posts its text back here with doc_version. Or paste a version yourself.')}
        </p>
      )}
      <ol className="flex flex-col gap-2">
        {versions.map((v, i) => (
          <li key={v.id} className="flex items-center gap-8 px-6 py-3 rounded-input hover:bg-hover text-11 font-mono">
            <button type="button" onClick={() => setOpen(v.id)} aria-label={t('Open version {n}', { n: numberOf(i) })}
              className="flex-1 min-w-0 text-left flex items-center gap-8">
              <FileText size={11} className="text-brand shrink-0" aria-hidden />
              <span className="text-primary shrink-0">v{numberOf(i)}</span>
              <span className="text-tertiary shrink-0">{formatStamp(v.created_at)}</span>
              <span className="text-secondary truncate">{v.note || v.body.slice(0, 80).replace(/\n/g, ' ')}</span>
            </button>
            <Who id={v.agent_id} className="text-tertiary shrink-0" />
          </li>
        ))}
      </ol>
      {mentions.map((m, i) => (
        <button key={i} type="button" onClick={() => onSession(m.session_id)} className="text-left text-11 font-mono flex items-center gap-8 px-6 py-3 rounded-input hover:bg-hover">
          <span className={m.role === 'user' ? 'text-status-amber' : 'text-brand'}>{m.role === 'user' ? '◆' : '◇'}</span>
          <AgentName id={m.agent_id} className="text-secondary" />
          <span className="text-tertiary">{formatStamp(m.at)} {t('· turn')} {m.turn}</span>
          <span className="text-tertiary truncate">“{m.excerpt}”</span>
        </button>
      ))}

      {openIndex >= 0 && (
        <VersionWindow
          version={versions[openIndex]!}
          n={numberOf(openIndex)}
          previous={versions[openIndex + 1] ?? null}
          onClose={() => setOpen(null)}
        />
      )}
    </section>
  )
}

/** One version, read in a window over the board, or compared with the one before. */
function VersionWindow({ version, n, previous, onClose }: {
  version: Version; n: number; previous: Version | null; onClose: () => void
}) {
  const [view, setView] = useState<'read' | 'changes'>('read')
  return (
    <Modal label={t('Version {n}', { n })} onClose={onClose} width="w-[760px]" top>
      <div className="flex flex-col gap-8">
        <div className="flex items-center gap-8 text-11 font-mono text-tertiary flex-wrap">
          <span className="text-primary">v{n}</span>
          <Who id={version.agent_id} className="text-secondary" />
          <span>· {formatStamp(version.created_at)}</span>
          <span className="ml-auto flex items-center gap-8">
            {previous && (
              <Segmented label={t('Show')} value={view} onChange={setView} height={20}
                options={[['read', t('read')], ['changes', t('changes from v{n}', { n: n - 1 })]]} />
            )}
            <CopyButton text={version.body} title={t('Copy this version')} label={<>{t('copy')}</>} copiedLabel={<>{t('copied')}</>} icon={null} className="text-secondary hover:text-primary" />
            <button type="button" onClick={onClose} className="text-secondary hover:text-primary" aria-label={t('Close')}>×</button>
          </span>
        </div>
        {version.note && <p className="text-12 text-secondary">{version.note}</p>}
        {view === 'changes' && previous
          ? <Changes from={previous.body} to={version.body} a={n - 1} b={n} />
          : <Markdown text={version.body} />}
      </div>
    </Modal>
  )
}
