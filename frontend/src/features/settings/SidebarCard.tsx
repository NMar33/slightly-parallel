import { PanelLeft } from 'lucide-react'
import { Link } from 'react-router-dom'

import { summary } from '../sidebar/layout'
import { useSidebarLayout } from '../sidebar/store'
import { t } from '../../i18n/scope/system'

/** Sidebar — the door on the Settings page: what shows, what is put away. */
export function SidebarCard() {
  const layout = useSidebarLayout()
  const s = summary(layout)
  return (
    <section className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-12">
      <div className="flex items-baseline gap-10 flex-wrap">
        <h2 className="text-16 font-semibold text-primary inline-flex items-center gap-6">
          <PanelLeft size={16} className="text-brand" aria-hidden /> {t('Sidebar')}
        </h2>
        <span className="text-11 text-tertiary">{t('which pages show, in which groups, in what order')}</span>
        <Link to="/settings/sidebar" className="ml-auto text-11 font-mono text-brand hover:underline">
          {t('arrange the sidebar →')}
        </Link>
      </div>
      <div className="flex items-center gap-12 flex-wrap text-12 text-secondary">
        <span><span className="text-tertiary">{t('groups:')} </span>{layout.groups.map((g) => t(g.label)).join(' · ')}</span>
        <span><span className="text-tertiary">{t('shown:')} </span>{s.shown}</span>
        <span><span className="text-tertiary">{t('hidden:')} </span>{s.hidden}</span>
      </div>
    </section>
  )
}
