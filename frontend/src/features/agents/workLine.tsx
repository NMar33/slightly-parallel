/**
 * What a turn changed — the commits and the uncommitted edits git saw in
 * its window, one line that opens into the files and their diffs.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { GitCommit } from 'lucide-react'

import { LoadingSkeleton } from '../../components/states'
import { getJson, postJson, fail } from '../../lib/getJson'
import type { TurnWork } from '../../lib/api'

import { t, tn } from '../../i18n/scope/views'
/**
 * What the turn changed — the commits attributed to it, as one line that
 * opens into the files. The chat says what was asked and answered; this is
 * the third column, what git recorded, sitting under the reply it belongs
 * to. Commits only: a turn that changed files without committing shows
 * nothing here, and says nothing rather than guessing.
 */
export function WorkLine({ work, sessionId }: { work: TurnWork; sessionId: string }) {
  const [open, setOpen] = useState(false)
  const [diff, setDiff] = useState<{ sha?: string; path?: string; label: string } | null>(null)
  const one = work.commits.length === 1 ? work.commits[0] : undefined
  const u = work.uncommitted
  const committed = work.commits.length > 0
  const openFile = async (path: string) => {
    try {
      const d = await postJson<{ opened?: boolean; path?: string }>(`/api/sessions/${encodeURIComponent(sessionId)}/open`, { path })
      if (!d.opened) throw new Error(d.path || t('could not open'))
    } catch (e) { fail(e) }
  }
  return (
    <div className="ml-16 flex flex-col gap-4">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
        title={work.exact ? t('Exact: recorded when the turn ended') : t('Approximate: commits made during this turn')}
        className="self-start inline-flex items-center gap-6 text-10 font-mono text-tertiary hover:text-primary">
        <GitCommit size={10} aria-hidden className={committed ? 'text-brand' : 'text-status-amber'} />
        {committed && (
          <>
            <span className="text-secondary">{tn(work.files_n, '{n} file', '{n} files')}</span>
            <span className="text-status-green">+{work.add}</span>
            <span className="text-status-red">−{work.del}</span>
            {one ? (
              <span className="truncate max-w-[520px]"><span className="text-brand">{one.sha}</span> {one.subject}</span>
            ) : (
              <span>{work.commits.length} {t('commits')}</span>
            )}
          </>
        )}
        {u && (
          <span className={committed ? 'text-tertiary' : 'text-secondary'}>
            {committed ? '· ' : ''}{u.files_n} {t('edited, not committed')}
            <span className="text-status-green"> +{u.add}</span> <span className="text-status-red">−{u.del}</span>
          </span>
        )}
        {work.exact === false && <span className="text-tertiary/60" title={t('Approximate: matched to this turn by time')}>~</span>}
      </button>
      {open && (
        <div className="flex flex-col gap-6 rounded-input border border-border-subtle bg-elevated px-8 py-6 text-10 font-mono">
          {u && u.paths.length > 0 && (
            <div className="flex flex-col gap-2">
              <div className="text-tertiary">{t('Not committed when the turn ended. The diff shows the file as it is now.')}</div>
              {u.paths.map((f) => (
                <FileRow key={f.path} path={f.path} add={f.add} del={f.del} isNew={f.new}
                  active={diff?.path === f.path && !diff?.sha}
                  onDiff={() => setDiff(diff?.path === f.path && !diff?.sha ? null : { path: f.path, label: `${f.path} · now` })}
                  onOpen={() => void openFile(f.path)} />
              ))}
            </div>
          )}
          {work.commits.map((c) => (
            <div key={c.sha} className="flex flex-col gap-2">
              <div className="flex items-baseline gap-6 text-tertiary">
                <button type="button" onClick={() => setDiff(diff?.sha === c.sha && !diff.path ? null : { sha: c.sha, label: `${c.sha} · ${c.subject}` })}
                  className={`hover:underline ${diff?.sha === c.sha && !diff.path ? 'text-primary' : 'text-brand'}`} title={t('the whole commit')}>
                  {c.sha}
                </button>
                <span className="text-primary truncate">{c.subject}</span>
                <span className="ml-auto tabular shrink-0">{c.at.slice(11, 16)} · +{c.add} −{c.del}</span>
              </div>
              {c.files.map((f) => (
                <FileRow key={f.path} path={f.path} add={f.add} del={f.del}
                  active={diff?.sha === c.sha && diff?.path === f.path}
                  onDiff={() => setDiff(diff?.sha === c.sha && diff?.path === f.path ? null : { sha: c.sha, path: f.path, label: `${f.path} · ${c.sha}` })}
                  onOpen={() => void openFile(f.path)} />
              ))}
            </div>
          ))}
          {diff && <DiffPanel sessionId={sessionId} sha={diff.sha} path={diff.path} label={diff.label} onClose={() => setDiff(null)} />}
        </div>
      )}
    </div>
  )
}

function FileRow({ path, add, del: del_, isNew = false, active, onDiff, onOpen }: {
  path: string; add: number; del: number; isNew?: boolean; active: boolean; onDiff: () => void; onOpen: () => void
}) {
  return (
    <div className={`flex items-baseline gap-6 pl-8 rounded-input ${active ? 'bg-brand-glow' : ''}`}>
      <button type="button" onClick={onDiff} className={`truncate text-left hover:underline ${active ? 'text-primary' : 'text-secondary'}`} title={t('what changed')}>
        {path}
      </button>
      {isNew && <span className="text-status-amber">{t('new')}</span>}
      <button type="button" onClick={onOpen} className="text-tertiary hover:text-primary shrink-0" title={t('Open the file on this computer')}>{t('open')}</button>
      <span className="ml-auto tabular shrink-0"><span className="text-status-green">+{add}</span> <span className="text-status-red">−{del_}</span></span>
    </div>
  )
}

/**
 * The change itself. A commit's diff is exact forever; an uncommitted
 * file's diff is the tree as it is now, and the panel says so.
 */
function DiffPanel({ sessionId, sha, path, label, onClose }: {
  sessionId: string; sha?: string; path?: string; label: string; onClose: () => void
}) {
  const q = useQuery({
    queryKey: ['session-diff', sessionId, sha ?? '', path ?? ''],
    queryFn: async ({ signal }) => {
      const qs = new URLSearchParams()
      if (sha) qs.set('sha', sha)
      if (path) qs.set('path', path)
      return getJson<{ sha: string; path: string; live: boolean; diff: string }>(`/api/sessions/${encodeURIComponent(sessionId)}/diff?${qs}`, signal)
    },
    staleTime: 60_000,
  })
  const lines = (q.data?.diff ?? '').split('\n')
  return (
    <div className="flex flex-col gap-4 rounded-input border border-border-default bg-base mt-4">
      <div className="flex items-center gap-8 px-8 py-4 border-b border-border-subtle text-tertiary">
        <span className="text-primary truncate">{label}</span>
        {q.data?.live && <span className="text-status-amber">{t('current file, not the version from this turn')}</span>}
        <button type="button" onClick={onClose} className="ml-auto hover:text-primary" aria-label={t('Close the diff')}>×</button>
      </div>
      {q.isLoading && <LoadingSkeleton variant="text" count={2} label={t('Loading')} className="px-8 py-4" />}
      {q.isError && <div className="px-8 py-4 text-status-red">{(q.error as Error).message}</div>}
      {q.data && (
        <pre className="px-8 py-4 overflow-x-auto max-h-[480px] overflow-y-auto leading-snug">
          {lines.map((ln, i) => {
            const tone = ln.startsWith('+++') || ln.startsWith('---') ? 'text-tertiary'
              : ln.startsWith('@@') ? 'text-brand'
              : ln.startsWith('+') ? 'text-status-green bg-status-green/8'
              : ln.startsWith('-') ? 'text-status-red bg-status-red/8'
              : ln.startsWith('diff ') || ln.startsWith('index ') ? 'text-tertiary/70'
              : 'text-secondary'
            return <div key={i} className={tone}>{ln || ' '}</div>
          })}
          {!q.data.diff.trim() && <div className="text-tertiary italic">{t('no difference')}</div>}
        </pre>
      )}
    </div>
  )
}
