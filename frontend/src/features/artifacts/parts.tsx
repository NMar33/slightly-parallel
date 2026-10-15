import { useState } from 'react'
import { FolderOpen } from 'lucide-react'
import { toast } from 'sonner'

import { Confirm } from '../../components/Confirm'
import { CopyButton } from '../../components/CopyButton'
import { Markdown } from '../../components/Markdown'
import { Button } from '../../components/primitives'
import { LABEL } from '../promptlib/taskstyle'
import { stamp } from '../visions/time'
import {
  type Artifact, type Preview, type TablePreview, type TreeEntry,
  artifactTitle, fileRoute, kindTitle, kindOf, previewShape, sizeLabel,
} from './data'
import { AgentName } from '../../components/AgentName'
import { NotWritten as SharedNotWritten } from '../../components/NotWritten'
import { t as tt, tn } from '../../i18n/scope/system'

/**
 * Artifacts — the parts of the page, on the real record.
 *
 * The preview draws what the folder holds for its kind: a dataset's fields
 * and a sample of rows, a document's text, a page in a frame that cannot
 * reach the dashboard, an app's tree and the line that runs it. A folder
 * that is gone says so, with the path.
 */

function DatasetTable({ t }: { t: TablePreview }) {
  return (
    <div className="flex flex-col gap-4 min-w-0">
      <div className="flex items-baseline gap-8 flex-wrap">
        <span className="text-12 font-mono text-primary">{t.file}</span>
        <span className="text-10 font-mono text-tertiary tabular">
          {tn(t.rows, '{n} row', '{n} rows')} · {tn(t.fields.length, '{n} field', '{n} fields')}
        </span>
        {t.error && <span className="text-10 font-mono text-status-amber">{tt('Read stopped at {where}', { where: t.error })}</span>}
      </div>
      {t.fields.length > 0 && (
        <div className="overflow-x-auto rounded-input border border-border-subtle">
          <table className="w-full text-11 font-mono">
            <thead>
              <tr className="bg-elevated">
                {t.fields.map((f) => <th key={f} className="text-left px-8 py-4 text-tertiary font-normal whitespace-nowrap">{f}</th>)}
              </tr>
            </thead>
            <tbody>
              {t.sample.map((r, i) => (
                <tr key={i} className="border-t border-border-subtle align-top">
                  {t.fields.map((f) => {
                    const v = r[f]
                    const text = v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v)
                    return <td key={f} className="px-8 py-4 text-secondary max-w-[260px] truncate" title={text}>{text}</td>
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Tree({ entries }: { entries: TreeEntry[] }) {
  return (
    <ul className="flex flex-col gap-2 text-12 font-mono">
      {entries.map((e) => (
        <li key={e.path} className="flex items-baseline gap-8" style={{ paddingLeft: e.depth * 12 }}>
          <span className={e.dir ? 'text-tertiary' : 'text-primary'}>{e.path.split('/').pop()}{e.dir ? '/' : ''}</span>
          {!e.dir && e.bytes != null && <span className="text-10 text-tertiary tabular shrink-0">{sizeLabel(e.bytes)}</span>}
        </li>
      ))}
    </ul>
  )
}

function PageFrame({ a, entry }: { a: Artifact; entry: string }) {
  const src = fileRoute(a.row.id, entry)
  return (
    <div className="rounded-input border border-border-default bg-base overflow-hidden">
      <div className="flex items-center gap-8 px-8 h-24 bg-elevated border-b border-border-subtle text-10 font-mono text-tertiary">
        <span className="truncate">{entry}</span>
        <a href={src} target="_blank" rel="noreferrer" className="ml-auto text-brand hover:underline shrink-0">{tt('Open in a tab')}</a>
      </div>
      <iframe src={src} title={`${artifactTitle(a)} — ${entry}`} sandbox="" className="w-full border-0 bg-[var(--page-ground)]" style={{ height: 360 }} />
    </div>
  )
}

function FilesOfFolder({ a }: { a: Artifact }) {
  const files = a.folder?.files ?? []
  return (
    <ul className="flex flex-col gap-2 text-12 font-mono">
      {files.map((f) => (
        <li key={f.path} className="flex items-baseline gap-8">
          <span className="text-primary truncate">{f.path}</span>
          <span className="text-10 text-tertiary tabular shrink-0">{sizeLabel(f.bytes)}</span>
        </li>
      ))}
    </ul>
  )
}

export function KindPreview({ a }: { a: Artifact }) {
  const p: Preview | null = a.folder?.preview ?? null
  const shape = previewShape(p)
  if (shape === 'missing') {
    return (
      <p className="text-12 text-status-amber">
        {tt('The folder is gone. It was at {path}.', { path: a.folder?.path || a.row.path || tt('an unknown path') })}
      </p>
    )
  }
  if (shape === 'tables') {
    return (
      <div className="flex flex-col gap-12 min-w-0">
        {p!.tables!.map((t) => <DatasetTable key={t.file} t={t} />)}
      </div>
    )
  }
  if (shape === 'document') {
    return (
      <div className="flex flex-col gap-4 min-w-0">
        {p!.document!.file !== 'ARTIFACT.md' && <span className="text-10 font-mono text-tertiary">{p!.document!.file}</span>}
        <div className="text-13 text-secondary leading-relaxed"><Markdown text={p!.document!.text} /></div>
        {p!.document!.truncated && <span className="text-10 font-mono text-tertiary">{tt('The text is cut here. The file holds the rest.')}</span>}
      </div>
    )
  }
  if (shape === 'page') return <PageFrame a={a} entry={p!.entry!} />
  if (shape === 'app') {
    return (
      <div className="flex flex-col gap-8">
        {p!.run ? (
          <div className="flex items-center gap-8 min-w-0">
            <span className={LABEL}>{tt('Run')}</span>
            <code className="text-12 font-mono text-primary bg-elevated rounded-input px-8 py-4 truncate">{p!.run}</code>
          </div>
        ) : (
          <span className="text-11 text-tertiary">{tt('ARTIFACT.md has no run line.')}</span>
        )}
        {p!.tree && p!.tree.length > 0 ? <Tree entries={p!.tree} /> : <FilesOfFolder a={a} />}
      </div>
    )
  }
  if (shape === 'tree') return <Tree entries={p!.tree!} />
  return <p className="text-12 text-tertiary">{tt('The folder holds ARTIFACT.md and nothing the page shows for a {kind}.', { kind: kindTitle(kindOf(a), true).toLowerCase() })}</p>
}

function FilesFold({ a }: { a: Artifact }) {
  const [open, setOpen] = useState(false)
  const files = a.folder?.files ?? []
  if (!files.length) return null
  const bytes = files.reduce((n, f) => n + f.bytes, 0)
  return (
    <section aria-label={tt('Files')} className="flex flex-col gap-6">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex items-center gap-8 text-left h-20">
        <span className={`text-10 text-tertiary transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden>▶</span>
        <span className={LABEL}>{tt('Files')} ({files.length}) · {sizeLabel(bytes)}</span>
      </button>
      {open && <div className="pl-16"><FilesOfFolder a={a} /></div>}
    </section>
  )
}

function FolderLine({ a }: { a: Artifact }) {
  const path = a.folder?.path || a.row.path || ''
  if (!path) return null
  return (
    <div className="flex items-center gap-8 min-w-0 text-11 font-mono text-tertiary">
      <FolderOpen size={12} aria-hidden className="shrink-0" />
      <span className="truncate" title={path}>{path}</span>
      <CopyButton
        text={path}
        title={tt('Copy path')}
        label={` ${tt('Copy path')}`}
        copiedLabel={` ${tt('Copy path')}`}
        tick={false}
        onCopied={() => toast.success(tt('Path copied'))}
        onFailed={() => toast.error(tt("Couldn't copy"))}
        className="inline-flex items-center gap-4 text-brand hover:underline shrink-0"
      />
    </div>
  )
}

function YourWords({ a }: { a: Artifact }) {
  const message = a.kept?.message?.trim()
  if (!message) return null
  return (
    <section aria-label={tt('Your words')} className="flex flex-col gap-4">
      <span className={LABEL}>{tt('Your words')}</span>
      <p className="text-13 text-secondary leading-relaxed whitespace-pre-wrap">{message}</p>
    </section>
  )
}

function Manifest({ a }: { a: Artifact }) {
  const body = a.folder?.manifest.body?.trim()
  if (!body || kindOf(a) === 'document') return null
  return (
    <div className="flex flex-col gap-4">
      <span className={LABEL}>ARTIFACT.md</span>
      <div className="text-12 text-secondary leading-relaxed"><Markdown text={body} /></div>
    </div>
  )
}



export function Section({ a, busy, onArchive, onRestore, watch }: {
  a: Artifact
  busy: boolean
  onArchive: () => void
  onRestore: () => void
  /** A ref, so the page reads the folder when the section comes on screen (useArtifacts' `near`). */
  watch?: (el: Element | null) => void
}) {
  const [ask, setAsk] = useState(false)
  const archived = a.row.status === 'archived'
  const updated = a.row.updated_at ? stamp(a.row.updated_at) : stamp(`${a.row.created_date} ${a.row.created_time}`)
  return (
    <section ref={watch} id={a.row.id} aria-label={artifactTitle(a)} className="flex flex-col gap-12 py-16 border-t border-border-subtle scroll-mt-16">
      <div className="flex items-center gap-12 flex-wrap">
        <h3 className="text-16 font-mono text-primary">{artifactTitle(a)}</h3>
        <span className="text-11 font-mono text-tertiary">{a.row.project} · <AgentName id={a.row.agent_id} /> · {tt('updated {date}', { date: updated })}</span>
        {(a.row.status ?? 'draft') === 'draft' && <span className="text-10 font-mono text-tertiary">{tt('Draft')}</span>}
        <div className="ml-auto">
          {archived
            ? <Button size="sm" variant="ghost" onClick={onRestore} disabled={busy}>{tt('Restore')}</Button>
            : <Button size="sm" variant="ghost" onClick={() => setAsk(true)} disabled={busy}>{tt('Archive')}</Button>}
        </div>
      </div>
      {ask && (
        <Confirm text={tt('Archive {name}: remove it from this list. The folder stays on disk.', { name: artifactTitle(a) })}
          action={tt('Archive')} busy={busy} onYes={() => { setAsk(false); onArchive() }} onNo={() => setAsk(false)} />
      )}
      {a.row.description && <p className="text-13 text-secondary leading-relaxed max-w-[720px]">{a.row.description}</p>}
      <FolderLine a={a} />
      <div className="grid gap-16 lg:grid-cols-[minmax(0,1fr)_280px]">
        {/* The preview is drawn from the folder as read; nothing stands in for it before. */}
        <div className="min-w-0">{!a.pending && <KindPreview a={a} />}</div>
        <div className="flex flex-col gap-12">
          <YourWords a={a} />
          <FilesFold a={a} />
          <Manifest a={a} />
        </div>
      </div>
    </section>
  )
}

export function NotWritten({ items, busy, onArchive }: { items: Artifact[]; busy: boolean; onArchive: (id: string) => void }) {
  return (
    <SharedNotWritten
      blurb={tt('Kept with #artifact. No folder yet.')}
      rows={items.map((a) => ({
        id: a.row.id,
        stamp: stamp(`${a.row.created_date} ${a.row.created_time}`),
        project: a.row.project,
        text: a.kept?.message || a.row.l1,
        action: (
          <button type="button" disabled={busy} onClick={() => onArchive(a.row.id)}
            className="text-11 font-mono text-tertiary hover:text-primary shrink-0">{tt('Archive')}</button>
        ),
      }))}
    />
  )
}
