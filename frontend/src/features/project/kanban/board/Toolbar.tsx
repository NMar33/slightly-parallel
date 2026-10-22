/**
 * The board's toolbar: the task count, the view switches (descriptions,
 * copy, links, today only, important only), the film, the column picker
 * and the board view. The switches' state is `useBoardSwitches`.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Clapperboard, Settings2 } from 'lucide-react'
import { Segmented } from '../../../../components/Segmented'
import { persistPref, readPref } from '../../../../lib/uiPrefs'
import type { KanbanView } from '../model'
import { SwitchChip } from './controls'
import { KanbanInfo } from './dialogs'
import { t } from '../../../../i18n/scope/project'

/** Two remembered switches (descriptions, copy) and two momentary lenses. */
export function useBoardSwitches() {
  // Remembered per browser: descriptions on cards, and per-task copy
  // affordances (which also unlock column copy and bulk move). Off by
  // default — they cost vertical space.
  const [showDesc, setShowDesc] = useState(() => readPref('sp-kanban-desc') === '1')
  const [copyMode, setCopyMode] = useState(() => readPref('sp-kanban-copy') === '1')
  const toggleDesc = () => {
    setShowDesc(!showDesc)
    persistPref('sp-kanban-desc', showDesc ? '0' : '1')
  }
  const toggleCopy = () => {
    setCopyMode(!copyMode)
    persistPref('sp-kanban-copy', copyMode ? '0' : '1')
  }
  // A momentary lens: only the starred tasks, or only today's. Not remembered across loads.
  const [onlyRemembered, setOnlyRemembered] = useState(false)
  const [onlyToday, setOnlyToday] = useState(false)
  return {
    showDesc, toggleDesc, copyMode, toggleCopy,
    onlyToday, toggleOnlyToday: () => setOnlyToday((v) => !v),
    onlyRemembered, toggleOnlyRemembered: () => setOnlyRemembered((v) => !v),
  }
}

export function BoardToolbar({ sw, linksMode, toggleLinks, tasksN, todayN, projectCode, view, onView, onColumns }: {
  sw: ReturnType<typeof useBoardSwitches>
  linksMode: boolean
  toggleLinks: (on: boolean) => void
  tasksN: number
  todayN: number
  projectCode: string
  view: KanbanView
  onView: (v: KanbanView) => void
  onColumns: () => void
}) {
  return (
    <div className="flex items-center gap-8 flex-wrap">
      <span className="text-11 uppercase tracking-wide text-tertiary font-mono">{t('Kanban')}</span>
      <KanbanInfo />
      <span className="text-11 text-tertiary font-mono">{tasksN} {t('tasks')}</span>

      <div className="ml-auto flex items-center gap-4">
        <SwitchChip
          on={sw.showDesc}
          onToggle={sw.toggleDesc}
          label={t('desc')}
          title={t('Show each task\'s description on its card')}
        />
        <SwitchChip
          on={sw.copyMode}
          onToggle={sw.toggleCopy}
          label={t('copy')}
          title={t('Show copy buttons and the handle that moves a whole column')}
        />
        <SwitchChip
          on={linksMode}
          onToggle={() => toggleLinks(!linksMode)}
          label={t('links')}
          title={t('Show lines between linked tasks. To link, click a card\'s link button, then another card.')}
        />
        <SwitchChip
          on={sw.onlyToday}
          onToggle={sw.toggleOnlyToday}
          label={`☀${todayN ? ` ${todayN}` : ''}`}
          title={t('Ctrl-click a card to add it to Today')}
        />
        <SwitchChip
          on={sw.onlyRemembered}
          onToggle={sw.toggleOnlyRemembered}
          label="★"
          title={t('Show only important tasks (★)')}
        />
      </div>
      {/* The film is a page, not a lightbox. Opening it over the board
          replaced the whole app — no sidebar, no breadcrumb, a second set
          of chrome — for a view that has an address of its own. */}
      <Link
        to={`/timelapse#project=${encodeURIComponent(projectCode)}`}
        aria-label={t('Timelapse')}
        title={`Replay ${projectCode} as a film`}
        className="h-20 w-20 inline-flex items-center justify-center rounded-pill text-tertiary hover:text-primary hover:bg-hover transition-colors"
      >
        <Clapperboard size={13} aria-hidden />
      </Link>
      <button
        type="button"
        onClick={onColumns}
        aria-label={t('Board columns')}
        title={t('Choose which columns this board shows')}
        className="h-20 w-20 inline-flex items-center justify-center rounded-pill text-tertiary hover:text-primary hover:bg-hover transition-colors"
      >
        <Settings2 size={13} aria-hidden />
      </button>
      <Segmented label={t('Board view')} shape="pill" value={view} onChange={onView}
        options={(['classic', 'workflow', 'lanes'] as KanbanView[]).map((v) =>
          [v, v === 'classic' ? t('3-col') : v === 'workflow' ? t('5-col') : t('swim lanes')] as const)} />
    </div>
  )
}
