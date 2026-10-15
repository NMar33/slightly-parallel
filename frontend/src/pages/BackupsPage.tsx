import { bytes } from '../utils/format'
import { useEffect, useState } from 'react'
import { getJson, postJson } from '../lib/getJson'
import { writeClipboard } from '../lib/useCopy'
import { BackupProof, PROOF_KEY } from '../features/capture/BackupProof'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Check,
  DatabaseBackup,
  Download,
  FolderOpen,
  Loader2,
  Pin,
  RotateCcw,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react'
import { toast } from 'sonner'

import { Badge, Button, Input } from '../components/primitives'
import { Confirm } from '../components/Confirm'
import { ErrorBanner, LoadingSkeleton } from '../components/states'
import { PageHeader } from '../components/PageHeader'
import { t, tn } from '../i18n/scope/pages'

/**
 * BackupsPage: the ladder, what is on it, and the way back.
 *
 * The page is built around one claim the operator has to be able to check
 * at a glance: *there is a restore point at each of these ages.* So the
 * rungs are the first thing on the page, each either filled by a named
 * archive or visibly empty — not a list of files the reader has to date
 * arithmetic in their head.
 *
 * Restore is the one control here that destroys data, so it is the only one
 * that costs a typed confirmation, and it says what it is about to replace
 * before it asks.
 */

const QUERY_KEY = ['backup', 'state']

interface Archive {
  name: string
  at: string
  kind: 'auto' | 'manual'
  bytes: number
  label: string
  files: number
  sha256: string
  pinned: boolean
  reasons: string[]
  expiring?: boolean
}

interface Rung {
  name: string
  days: number
}

interface BackupState {
  data_root: string
  backup_root: string
  enabled: boolean
  every_hours: number
  keep: { horizon_days: number; manual: number }
  excluded: string[]
  rungs: Rung[]
  source: { files: number; bytes: number; mtime: number }
  due: boolean
  due_reason: string
  archives: Archive[]
  expiring: string[]
  total_bytes: number
  count: number
}


function ageOf(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const min = Math.max(0, Math.round(ms / 60000))
  if (min < 60) return t('{n}m ago', { n: min })
  const h = Math.round(min / 60)
  if (h < 48) return t('{n}h ago', { n: h })
  return t('{n}d ago', { n: Math.round(h / 24) })
}

/** What the backup writes answer with. */
interface RunAnswer { archive: { bytes: number; files: number } }
interface TrialAnswer { name: string; ok: boolean; counts?: Record<string, number>; problems: string[] }
interface RevealAnswer { opened: boolean; path: string; detail: string }
interface RestoreAnswer { restored: { files: number }; safety: { name: string } }

export default function BackupsPage() {
  useEffect(() => {
    document.title = `${t('Backups')} — Slightly Parallel`
  }, [])

  const qc = useQueryClient()
  const [label, setLabel] = useState('')
  const [confirming, setConfirming] = useState<string | null>(null)
  const [typed, setTyped] = useState('')
  const [checked, setChecked] = useState<Record<string, string>>({})

  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: ({ signal }) => getJson<BackupState>('/api/backup', signal),
    refetchInterval: 30_000,
  })
  const state = query.data
  const refresh = () => void qc.invalidateQueries({ queryKey: QUERY_KEY })

  const run = useMutation({
    mutationFn: () => postJson<RunAnswer>('/api/backup/run', { label }),
    onSuccess: (d) => {
      setLabel('')
      refresh()
      toast.success(t('Backed up. {size}, {n} files.', { size: bytes(d.archive.bytes), n: d.archive.files }))
    },
    onError: (e: Error) => toast.error(e.message),
  })

  // Verify is a trial restore: the checksum, then the archive unpacked into
  // a temporary folder and read as the dashboard would (backup.trial).
  const verify = useMutation({
    mutationFn: (name: string) => postJson<TrialAnswer>(`/api/backup/${name}/trial`),
    onSuccess: (d) => {
      setChecked((c) => ({
        ...c,
        [d.name]: d.ok
          ? t('Test restore passed: {tasks} tasks, {decisions} decisions, no errors', { tasks: d.counts?.task ?? 0, decisions: d.counts?.decision ?? 0 })
          : d.problems.join('; '),
      }))
      void qc.invalidateQueries({ queryKey: PROOF_KEY })
      if (d.ok) toast.success(t('{name} passed the test restore.', { name: d.name }))
      else toast.error(d.problems.join('; '))
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const pin = useMutation({
    mutationFn: (v: { name: string; pinned: boolean }) =>
      postJson(`/api/backup/${v.name}/pin`, { pinned: v.pinned }),
    onSuccess: () => refresh(),
    onError: (e: Error) => toast.error(e.message),
  })

  /** A web page cannot open a local directory, so the server does it. */
  const reveal = useMutation({
    mutationFn: (name?: string) => postJson<RevealAnswer>('/api/backup/reveal', name ? { name } : {}),
    onSuccess: async (d) => {
      if (d.opened) return
      // Say "copied" only when it was: the browser may refuse the clipboard.
      const copied = await writeClipboard(d.path)
      // The server's own sentence, then ours.
      toast([`${d.detail}.`, copied ? t('Path copied.') : ''].filter(Boolean).join(' '), { description: d.path })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const remove = useMutation({
    mutationFn: (name: string) => postJson(`/api/backup/${name}/delete`),
    onSuccess: () => {
      refresh()
      toast.success(t('Backup deleted.'))
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const restore = useMutation({
    mutationFn: (name: string) => postJson<RestoreAnswer>(`/api/backup/${name}/restore`, { confirm: name }),
    onSuccess: (d) => {
      setConfirming(null)
      setTyped('')
      void qc.invalidateQueries()
      toast.success(
        t('Restored {n} files. The state you replaced is saved as {name}.', { n: d.restored.files, name: d.safety.name }),
      )
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const busy = run.isPending || restore.isPending
  const filled = new Map<string, Archive>()
  for (const a of state?.archives ?? []) {
    if (a.expiring) continue
    for (const r of a.reasons) if (!filled.has(r)) filled.set(r, a)
  }

  return (
    <div className="flex flex-col gap-24 min-w-0">
      <PageHeader
        icon={DatabaseBackup}
        title={t('Backups')}
        tagline={t('Copies of the data folder, saved beside it as .tar.gz files. Restore replaces the current data with a copy. Download saves the file.')}
      />

      {query.isLoading && !query.data && <LoadingSkeleton variant="card" count={2} />}
      {query.isError && (
        <ErrorBanner
          title={t('Could not read the backup folder')}
          onRetry={() => void query.refetch()}
          hideDismiss
        />
      )}

      {state && (
        <>
          {/* ------------------------------------------------ take one --- */}
          <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-16">
            <div className="flex items-baseline gap-12 flex-wrap">
              <h2 className="text-16 font-semibold text-primary">{t('Back up now')}</h2>
              <span className="text-12 text-tertiary tabular">
                {t('{n} files · {size} in the data folder', { n: state.source.files, size: bytes(state.source.bytes) })}
              </span>
              <span className="ml-auto text-12 text-tertiary">
                {state.enabled ? (
                  <>
                    {t('automatic, every {n}h', { n: state.every_hours })} ·{' '}
                    <span className={state.due ? 'text-brand' : ''}>{state.due_reason}</span>
                  </>
                ) : (
                  t('automatic backups are off')
                )}
              </span>
            </div>
            <div className="flex gap-8 items-center flex-wrap">
              <Input
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder={t('Label (optional)')}
                className="flex-1 min-w-[240px]"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !busy) run.mutate()
                }}
              />
              <Button onClick={() => run.mutate()} disabled={busy}>
                {run.isPending ? (
                  <Loader2 size={14} className="animate-spin" aria-hidden />
                ) : (
                  <DatabaseBackup size={14} aria-hidden />
                )}
                {t('Back up now')}
              </Button>
            </div>
            <BackupProof />
            <p className="text-12 text-tertiary max-w-reading">
              {t('Archives are written to')}{' '}
              <code className="font-mono text-11 text-secondary">{state.backup_root}</code>
              {': '}
              {t('{n} on disk, {size}. Everything in the data folder goes in except {excluded}.', { n: state.count, size: bytes(state.total_bytes), excluded: state.excluded.join(', ') })}
            </p>
          </section>

          {/* --------------------------------------------------- ladder --- */}
          <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
            <div className="flex items-baseline gap-12 flex-wrap">
              <h2 className="text-16 font-semibold text-primary">{t('Restore points')}</h2>
              <span className="text-12 text-tertiary">
                {t('one backup kept per period, up to {n} days', { n: state.keep.horizon_days })}
              </span>
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto"
                disabled={state.count === 0}
                onClick={() => reveal.mutate(undefined)}
                title={state.backup_root}
              >
                <FolderOpen size={13} aria-hidden />
                {t('Show in folder')}
              </Button>
            </div>
            <div className="flex flex-col gap-4">
              <Rungs rungs={state.rungs} filled={filled} />
            </div>
          </section>

          {/* ------------------------------------------------- archives --- */}
          <section className="flex flex-col gap-8">
            <h2 className="text-16 font-semibold text-primary">
              {t('On disk')}{' '}
              <span className="text-12 font-normal text-tertiary tabular">
                {state.archives.length}
              </span>
            </h2>
            {state.archives.length === 0 && (
              <p className="text-13 text-tertiary max-w-reading">
                {t('No backups yet. Back up now, or wait for the automatic backup.')}
              </p>
            )}
            {state.archives.map((a) => (
              <ArchiveRow
                key={a.name}
                archive={a}
                checked={checked[a.name]}
                confirming={confirming === a.name}
                typed={typed}
                busy={busy}
                onTyped={setTyped}
                onVerify={() => verify.mutate(a.name)}
                onReveal={() => reveal.mutate(a.name)}
                onPin={() => pin.mutate({ name: a.name, pinned: !a.pinned })}
                onDelete={() => remove.mutate(a.name)}
                onAskRestore={() => {
                  setConfirming(confirming === a.name ? null : a.name)
                  setTyped('')
                }}
                onRestore={() => restore.mutate(a.name)}
              />
            ))}
            {state.expiring.length > 0 && (
              <p className="text-12 text-tertiary mt-4 max-w-reading">
                {tn(state.expiring.length, '{n} archive is outside every restore period and will be deleted at the next rotation.', '{n} archives are outside every restore period and will be deleted at the next rotation.')}{' '}
                {t('Pin a backup to keep it.')}
              </p>
            )}
          </section>
        </>
      )}
    </div>
  )
}

/**
 * The ladder itself. An empty rung is the point of the whole component: a
 * backup list that only shows what exists cannot show what is missing.
 */
function Rungs({ rungs, filled }: { rungs: Rung[]; filled: Map<string, Archive> }) {
  return (
    <>
      {rungs.map((r) => {
        const a = filled.get(r.name)
        return (
          <div key={r.name} className="flex items-center gap-12 text-13">
            <span className="w-[84px] shrink-0 text-secondary">{t(r.name)}</span>
            <span
              className={`h-8 w-8 rounded-pill shrink-0 ${
                a ? 'bg-brand' : 'border border-border-subtle'
              }`}
              aria-hidden
            />
            {a ? (
              <>
                <span className="font-mono text-11 text-secondary">{a.name}</span>
                <span className="text-12 text-tertiary tabular">{ageOf(a.at)}</span>
                <span className="text-12 text-tertiary tabular ml-auto">
                  {bytes(a.bytes)}
                </span>
              </>
            ) : (
              <span className="text-12 text-tertiary italic">
                {t('no backup this old yet')}
              </span>
            )}
          </div>
        )
      })}
    </>
  )
}

function ArchiveRow({
  archive: a,
  checked,
  confirming,
  typed,
  busy,
  onTyped,
  onVerify,
  onReveal,
  onPin,
  onDelete,
  onAskRestore,
  onRestore,
}: {
  archive: Archive
  checked?: string
  confirming: boolean
  typed: string
  busy: boolean
  onTyped: (v: string) => void
  onVerify: () => void
  onReveal: () => void
  onPin: () => void
  onDelete: () => void
  onAskRestore: () => void
  onRestore: () => void
}) {
  /** The delete asked inline (components/Confirm) before the archive goes. */
  const [askingDelete, setAskingDelete] = useState(false)
  return (
    <div
      role="group"
      aria-label={a.name}
      className={`rounded-card border bg-surface p-16 flex flex-col gap-8 ${
        a.expiring ? 'border-dashed border-border-strong' : 'border-border-subtle'
      }`}
    >
      <div className="flex items-center gap-8 flex-wrap">
        <span className="font-mono text-12 text-primary">{a.name}</span>
        <Badge tone={a.kind === 'manual' ? 'explicit' : 'auto'}>{a.kind === 'manual' ? t('manual') : t('auto')}</Badge>
        {a.pinned && <Badge tone="info">{t('pinned')}</Badge>}
        {a.expiring && <Badge tone="warning">{t('expiring')}</Badge>}
        {a.reasons
          .filter((r) => r !== 'manual' && r !== 'pinned')
          .map((r) => (
            <Badge key={r} tone="neutral">
              {t(r)}
            </Badge>
          ))}
        <span className="text-12 text-tertiary tabular ml-auto">
          {ageOf(a.at)} · {bytes(a.bytes)} · {tn(a.files, '{n} file', '{n} files')}
        </span>
      </div>

      {a.label && <p className="text-13 text-secondary">{a.label}</p>}
      {checked && (
        <p className="text-12 text-tertiary flex items-center gap-4">
          <ShieldCheck size={12} aria-hidden /> {checked}
        </p>
      )}

      <div className="flex gap-8 flex-wrap">
        <Button size="sm" variant="ghost" onClick={onVerify}>
          <ShieldCheck size={13} aria-hidden />
          {t('Verify')}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => {
          window.location.href = `/api/backup/${a.name}/download`
        }}>
          <Download size={13} aria-hidden />
          {t('Download')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onReveal}>
          <FolderOpen size={13} aria-hidden />
          {t('Show')}
        </Button>
        <Button size="sm" variant="ghost" onClick={onPin}>
          <Pin size={13} aria-hidden />
          {a.pinned ? t('Unpin') : t('Pin')}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setAskingDelete(true)}
          disabled={a.pinned || askingDelete}
          title={a.pinned ? t('Unpin to delete') : undefined}
        >
          <Trash2 size={13} aria-hidden />
          {t('Delete')}
        </Button>
        <Button
          size="sm"
          variant={confirming ? 'secondary' : 'ghost'}
          className="ml-auto"
          onClick={onAskRestore}
        >
          {confirming ? <X size={13} aria-hidden /> : <RotateCcw size={13} aria-hidden />}
          {confirming ? t('Cancel') : t('Restore')}
        </Button>
      </div>

      {askingDelete && (
        <Confirm
          text={t('This deletes the backup permanently.')}
          action={t('Delete')}
          onYes={() => { setAskingDelete(false); onDelete() }}
          onNo={() => setAskingDelete(false)}
        />
      )}

      {confirming && (
        <div className="rounded-card border border-border-subtle bg-base p-16 flex flex-col gap-8">
          <p className="text-13 text-primary">
            {t('This replaces all data in the data folder with this backup.')}
          </p>
          <p className="text-12 text-tertiary">
            {t('The current data is backed up first, so you can restore it. All pages reload afterwards.')}
          </p>
          <div className="flex gap-8 items-center flex-wrap">
            <Input
              value={typed}
              onChange={(e) => onTyped(e.target.value)}
              placeholder={a.name}
              aria-label={t('Type the backup name to confirm')}
              className="flex-1 min-w-[240px] font-mono"
              autoFocus
            />
            <Button
              variant="danger"
              disabled={typed !== a.name || busy}
              onClick={onRestore}
            >
              <Check size={14} aria-hidden />
              {t('Restore this backup')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
