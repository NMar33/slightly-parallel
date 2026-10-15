import { useMutation } from '@tanstack/react-query'

import { Badge, Button } from '../../components/primitives'
import { postJson } from '../../lib/getJson'
import type { SetupInfo } from './data'
import { AdapterBadge } from './parts'
import { t } from '../../i18n/scope/system'

import { rich } from '../../i18n/rich'
/**
 * CodexCard — Codex's notify hook is global by design (one entry serves
 * every registered project; the adapter resolves the project from the
 * event's working directory), so it installs once rather than per project.
 */
export function CodexCard({
  status,
  verified,
  onChanged,
}: {
  status: SetupInfo['codex']
  verified: boolean
  onChanged: () => void
}) {
  const act = useMutation({
    mutationFn: (action: 'install' | 'remove') => postJson('/api/setup/codex', { action }),
    onSuccess: onChanged,
  })

  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <div className="flex items-center gap-12">
        <h2 className="text-16 font-semibold text-primary">
          {t('Codex capture')}{' '}
          <span className="text-11 font-normal text-tertiary">
            {t('installed once for every project')}
          </span>
        </h2>
        <span className="ml-auto inline-flex items-center gap-4">
          <AdapterBadge verified={verified} />
          <Badge
            tone={
              status.state === 'installed'
                ? 'done'
                : status.state === 'foreign'
                  ? 'warning'
                  : 'neutral'
            }
          >
            {status.state === 'absent' ? t('not installed') : t(status.state)}
          </Badge>
        </span>
      </div>
      <p className="text-13 text-secondary leading-relaxed max-w-reading">
        {rich(t('Codex reports each finished turn through the {notify} setting in {config}, one entry for every project; the folder the turn ran in decides its project. Codex now calls {notify} legacy: use the Codex hooks box in the integration form instead, and keep this one for an older Codex.'), { notify: <code>notify</code>, config: <code>{status.config}</code> })}
      </p>
      {status.state === 'foreign' && (
        <p className="text-12 text-status-amber">
          {t('Your config already has a notify entry from another program. It is kept as it is; merge the two by hand to run both.')}
        </p>
      )}
      <div className="flex items-center gap-8">
        {status.state === 'installed' ? (
          <Button
            variant="secondary"
            size="sm"
            disabled={act.isPending}
            onClick={() => act.mutate('remove')}
          >
            {t('Remove')}
          </Button>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            disabled={act.isPending || status.state === 'foreign'}
            onClick={() => act.mutate('install')}
          >
            {t('Install')}
          </Button>
        )}
        {act.error && (
          <span className="text-12 text-error">{String((act.error as Error).message)}</span>
        )}
      </div>
    </section>
  )
}
