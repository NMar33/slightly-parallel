import { bytes } from '../../utils/format'
import { useState } from 'react'
import { toast } from 'sonner'

import { CopyButton } from '../../components/CopyButton'
import { LABEL } from '../promptlib/taskstyle'
import { t, tn } from '../../i18n/scope/system'

/**
 * The files beside SKILL.md.
 *
 * A skill folder can hold scripts, reference text and templates, so the files
 * are folded away and opened one at a time, read only. Editing a file happens
 * in the folder; the page keeps what is in Slightly Parallel.
 *
 * A file SKILL.md does not link to is marked: agents read SKILL.md, so an
 * unlinked file is usually left over.
 */

interface FileRow {
  path: string
  lines: number
  bytes: number
  linked: boolean
}

const BYTES = new TextEncoder()

/** "6 files" — what a skill carries besides SKILL.md. Empty when it has none. */
export function filesLabel(n: number): string {
  return n === 0 ? '' : tn(n, '{n} file', '{n} files')
}



/** Every file of the skill, folders first, with whether SKILL.md links to it. */
function fileRows(files: Record<string, string>, skillMd: string): FileRow[] {
  const dir = (p: string) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '')
  return Object.entries(files)
    .map(([path, text]) => ({
      path,
      lines: text ? text.replace(/\n$/, '').split('\n').length : 0,
      bytes: BYTES.encode(text).length,
      linked: skillMd.includes(path),
    }))
    .sort((a, b) => dir(a.path).localeCompare(dir(b.path)) || a.path.localeCompare(b.path))
}

export function FilesFold({ files, skillMd }: { files: Record<string, string>; skillMd: string }) {
  const rows = fileRows(files, skillMd)
  const [open, setOpen] = useState(false)
  const [shown, setShown] = useState('')
  if (!rows.length) return null

  return (
    <section aria-label={t('Files')} className="flex flex-col gap-6">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex items-center gap-8 text-left h-20">
        <span className={`text-10 text-tertiary transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden>▶</span>
        <span className={LABEL}>{t('Files')} ({rows.length})</span>
      </button>
      {open && (
        <div className="flex flex-col divide-y divide-border-subtle border-t border-border-subtle">
          {rows.map((r) => (
            <div key={r.path} className="flex flex-col">
              <button type="button" onClick={() => setShown((c) => (c === r.path ? '' : r.path))}
                aria-expanded={shown === r.path}
                className="flex items-baseline gap-8 py-6 text-left hover:bg-hover px-4 min-w-0">
                <span className="text-12 font-mono text-primary truncate flex-1 min-w-0">{r.path}</span>
                <span className="text-10 font-mono text-tertiary tabular shrink-0">
                  {tn(r.lines, '{n} line', '{n} lines')} · {bytes(r.bytes)}
                </span>
                <span className={`text-10 font-mono shrink-0 ${r.linked ? 'text-tertiary' : 'text-status-amber'}`}>
                  {r.linked ? t('linked') : t('not linked')}
                </span>
              </button>
              {shown === r.path && (
                <div className="flex flex-col gap-4 pb-8 px-4">
                  <CopyButton
                    text={() => files[r.path] ?? ''}
                    title={t('Copy {path}', { path: r.path })}
                    label={<> {t('Copy {path}', { path: r.path })}</>}
                    copiedLabel={<> {t('Copy {path}', { path: r.path })}</>}
                    size={12}
                    tick={false}
                    onCopied={() => toast.success(t('Copied {path}', { path: r.path }))}
                    className="self-start inline-flex items-center gap-4 text-11 font-mono text-brand hover:underline"
                  />
                  <pre className="max-h-[360px] overflow-auto rounded-input border border-border-subtle bg-base px-12 py-10 text-12 font-mono text-secondary whitespace-pre-wrap break-words">
                    {files[r.path] || t('The file is empty.')}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
