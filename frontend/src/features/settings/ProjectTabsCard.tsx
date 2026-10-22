import { LayoutList } from 'lucide-react'

import { TabChoices } from '../project/TabsPicker'
import { t } from '../../i18n/scope/system'

/** Project tabs — which tabs a project's page shows. Applies at once. */
export function ProjectTabsCard() {
  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <div className="flex items-baseline gap-10 flex-wrap">
        <h2 className="text-16 font-semibold text-primary inline-flex items-center gap-6">
          <LayoutList size={16} className="text-brand" aria-hidden /> {t('Project tabs')}
        </h2>
        <span className="text-11 text-tertiary">{t('which tabs a project page shows, in every project')}</span>
      </div>
      <TabChoices className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-16 gap-y-8" />
      <p className="text-11 text-tertiary leading-relaxed max-w-reading">
        {t('Overview always shows. A link to a tab that is off opens the tab the page opens on, and says how to turn it on.')}
      </p>
    </section>
  )
}
