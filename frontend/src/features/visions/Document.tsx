import { Lightbulb } from 'lucide-react'

import { KeptBook, KeptSection } from '../kept/Book'
import { useVisions } from './data'
import { VISIONS_GUIDE } from './guides'
import { t } from '../../i18n/scope/shell'

/**
 * Visions — the operator's #vision messages as a book of chapters, each
 * with the interpretation an agent wrote. Sets of visions can be written
 * into a project's AGENTS.md from the Projects panel (features/kept/Book).
 */
export function VisionsDocument({ project }: { project?: string } = {}) {
  const { visions, loading, error, near, complete } = useVisions()
  return (
    <KeptBook kind="vision" title={t('Visions')} icon={Lightbulb} guide={VISIONS_GUIDE}
      entries={visions} loading={loading} error={error} projects near={near} complete={complete}
      empty={t('No visions yet. Add #vision to a message to keep it.')}
      modes={[['tag', t('tag')], ['project', t('project')], ['month', t('month')], ['set', t('sets')]]} defaultMode="tag"
      inProject={project} section={(v, ctx) => <KeptSection v={v} kind="vision" ctx={ctx} />} />
  )
}
