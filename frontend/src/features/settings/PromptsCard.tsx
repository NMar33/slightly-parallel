import { FileText } from 'lucide-react'
import { Link } from 'react-router-dom'

import { ErrorBanner, LoadingSkeleton } from '../../components/states'
import { formatStamp } from '../../utils/dateUtils'
import { t, tn } from '../../i18n/scope/system'
import { usePromptFiles } from '../prompts/parts'

/**
 * Agent prompts — the files that tell agents how to act. This card shows
 * their state and opens the editor (Settings → Agent prompts), where the
 * file is read as a document and edited block by block, with history,
 * diffs and restore.
 */

export function PromptsCard() {
  const list = usePromptFiles()
  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <div className="flex items-baseline gap-10 flex-wrap">
        <h2 className="text-16 font-semibold text-primary inline-flex items-center gap-6">
          <FileText size={16} className="text-brand" aria-hidden /> {t('Agent prompts')}
        </h2>
        <span className="text-11 text-tertiary">{t('Edit the files agents read. Earlier versions are kept.')}</span>
      </div>
      {list.isError && <ErrorBanner title={t('Could not load the prompt files')} hideDismiss />}
      {list.isLoading && <LoadingSkeleton variant="row" count={2} />}
      {list.data && (
        <ul className="flex flex-col divide-y divide-border-subtle rounded-input border border-border-subtle bg-elevated">
          {list.data.map((f) => (

            <li key={f.key} className="flex items-center gap-10 px-12 py-8 text-12 flex-wrap">
              <Link to={`/settings/prompts?file=${f.key}`} className="text-primary font-medium hover:underline decoration-border-subtle">{t(f.label)}</Link>
              <span className="font-mono text-10 text-tertiary">{tn(f.lines, '{n} line', '{n} lines')}</span>
              {f.modified && <span className="font-mono text-10 text-tertiary">{t('modified {date}', { date: formatStamp(f.modified) })}</span>}
              <span className="font-mono text-10" style={{ color: f.is_original ? undefined : 'var(--status-amber)' }}>
                {f.is_original ? t('matches the original') : t('edited')}
              </span>
              {f.versions_n > 0 && <span className="font-mono text-10 text-tertiary">{tn(f.versions_n, '{n} version', '{n} versions')}</span>}
              <Link to={`/settings/prompts?file=${f.key}`} className="ml-auto text-11 font-mono text-brand hover:underline">{t('open editor →')}</Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
