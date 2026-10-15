import { useQuery } from '@tanstack/react-query'

import { getJson } from '../../lib/getJson'
import { t, locale } from '../../i18n/scope/system'

/**
 * The last trial restore (backend backup.trial): an archive unpacked into a
 * temporary folder and read as the dashboard would. After every automatic
 * backup, and when Verify is pressed on the Backups page.
 */
interface Proof { name: string; ok: boolean; problems: string[]; counts: Record<string, number>; at: string; seconds: number }

export const PROOF_KEY = ['backup', 'checked'] as const

function useBackupProof() {
  return useQuery({
    queryKey: PROOF_KEY,
    queryFn: ({ signal }) => getJson<{ checked: Proof | null }>('/api/backup/checked', signal),
    refetchInterval: 300_000,
  })
}

export function BackupProof() {
  const p = useBackupProof().data?.checked
  if (!p) {
    return <p className="text-12 text-tertiary">{t('No backup has been test-restored yet. The next automatic backup will be.')}</p>
  }
  const when = new Date(p.at).toLocaleString(locale(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  return p.ok ? (
    <p className="text-12 text-secondary">
      {t('Last test restore:')} <span className="font-mono">{p.name}</span>, {when} — {t('unpacked into a temporary folder and read back:')}
      {' '}{t('{tasks} tasks, {decisions} decisions, no errors ({s} s).', { tasks: p.counts.task ?? 0, decisions: p.counts.decision ?? 0, s: p.seconds })}
    </p>
  ) : (
    <div className="rounded-card border border-status-red/40 bg-surface p-12 flex flex-col gap-2">
      <p className="text-13 text-primary">{t('The last test restore failed:')} <span className="font-mono">{p.name}</span>, {when}.</p>
      {p.problems.map((x) => <p key={x} className="text-12 font-mono text-secondary break-all">{x}</p>)}
      <p className="text-12 text-tertiary">{t('Take a new backup, and keep an older one that passed.')}</p>
    </div>
  )
}
