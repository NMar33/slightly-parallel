import { Settings2 } from 'lucide-react'

import { PrefChip, PrefRow } from '../../components/Prefs'
import type { ChatsPrefs } from './prefs'


import { t } from '../../i18n/scope/views'
/** The gear in the title row. The strip it opens sits under the guide. */
export function SettingsButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={t('Page settings')}
      aria-expanded={open}
      title={t('Page settings — order, text, commits')}
      className={`h-20 w-20 inline-flex items-center justify-center rounded-input transition-colors ${
        open ? 'text-brand bg-brand/12' : 'text-tertiary hover:text-primary hover:bg-hover'
      }`}
    >
      <Settings2 size={13} aria-hidden />
    </button>
  )
}

/**
 * The settings strip: text size for the list and for the chat, how the
 * the order of turns, markdown, and whether a turn shows
 * what it committed. The same strip the task window opens under its gear.
 */
export function ChatSettings({ prefs, onChange }: {
  prefs: ChatsPrefs
  onChange: (p: ChatsPrefs) => void
}) {
  const set = (patch: Partial<ChatsPrefs>) => onChange({ ...prefs, ...patch })
  return (
    <div className="rounded-input border border-border-subtle bg-elevated px-10 py-8 flex flex-wrap items-center gap-x-16 gap-y-6">
      <PrefRow label={t('Order')}>
        <PrefChip on={prefs.order === 'oldest'} onClick={() => set({ order: 'oldest' })}>{t('oldest first')}</PrefChip>
        <PrefChip on={prefs.order === 'newest'} onClick={() => set({ order: 'newest' })}>{t('newest first')}</PrefChip>
      </PrefRow>
      <PrefRow label={t('Text')}>
        <PrefChip on={prefs.md} onClick={() => set({ md: true })} title={t('Render markdown')}>{t('markdown')}</PrefChip>
        <PrefChip on={!prefs.md} onClick={() => set({ md: false })} title={t('Show the text as it was sent')}>{t('raw')}</PrefChip>
      </PrefRow>
      <PrefRow label={t('Commits on a turn')}>
        <PrefChip on={prefs.work} onClick={() => set({ work: true })}>{t('show')}</PrefChip>
        <PrefChip on={!prefs.work} onClick={() => set({ work: false })}>{t('hide')}</PrefChip>
      </PrefRow>
    </div>
  )
}
