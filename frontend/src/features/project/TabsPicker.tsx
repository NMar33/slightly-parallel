import { SlidersHorizontal } from 'lucide-react'
import { Link } from 'react-router-dom'

import { usePopover } from '../../hooks/usePopover'
import { Checkbox } from '../setup/parts'
import { PROJECT_TABS, setTabShown, tabShown, useTabChoices } from './tabs'
import { t } from '../../i18n/scope/pages'

/** Every project tab with its box: Settings › Project tabs and the strip's own menu. */
export function TabChoices({ className = '' }: { className?: string }) {
  const choices = useTabChoices()
  return (
    <div className={className}>
      {PROJECT_TABS.map((tab) => (
        <Checkbox
          key={tab.id}
          label={tab.label}
          checked={tabShown(tab.id, choices)}
          disabled={'fixed' in tab && tab.fixed}
          onChange={(on) => setTabShown(tab.id, on)}
        />
      ))}
    </div>
  )
}

/** At the right end of the project's tab strip: which tabs show, where the tabs are. */
export function TabsPicker() {
  const { open, setOpen, rootRef } = usePopover<HTMLDivElement>()
  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-haspopup="dialog"
        aria-expanded={open}
        title={t('Which tabs show, in every project')}
        className={`inline-flex items-center gap-6 h-24 px-8 rounded-input text-12 ${open ? 'text-brand bg-hover' : 'text-tertiary hover:text-brand hover:bg-hover'}`}
      >
        <SlidersHorizontal size={12} aria-hidden /> {t('Tabs')}
      </button>
      {open && (
        <div role="dialog" aria-label={t('Project tabs')}
          className="absolute right-0 top-full mt-4 z-30 w-[220px] rounded-card border border-border-default bg-surface shadow-md p-12 flex flex-col gap-10">
          <TabChoices className="flex flex-col gap-6" />
          <p className="text-11 text-tertiary leading-relaxed">
            {t('For every project. Also in')}{' '}
            <Link to="/settings#project-tabs" className="text-brand hover:underline">{t('Settings › Project tabs')}</Link>
          </p>
        </div>
      )}
    </div>
  )
}
