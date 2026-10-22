import type { LucideIcon } from 'lucide-react'
import {
  CalendarDays,
  BookOpenText, Clapperboard, Cog, DatabaseBackup, KanbanSquare,
  LayoutDashboard, MessagesSquare, PlugZap, Search, SlidersHorizontal, Users, Star, Activity, SquareTerminal, BarChart3, Timer,
} from 'lucide-react'

import { LENS_HEAD_LIST } from '../../lenses/heads'
import { t } from '../../i18n/scope/shell'

/**
 * The catalogue — every page the sidebar can show, with the group it
 * belongs to when nothing has been arranged. The layout (layout.ts) only
 * holds keys; this is where a key becomes an icon, a label and a route.
 * A page added here appears in its home group for everyone, arranged or
 * not, the next time the layout is read.
 */
export interface NavEntry {
  /** The stable key the layout stores; also the route, unless `to` says otherwise. */
  key: string
  /** The route, when the page has moved and the key must not. */
  to?: string
  label: string
  icon: LucideIcon
  /** NavLink `end` — match this path exactly, not its children. */
  end?: boolean
  /** Group id when the operator has not arranged it. */
  home: string
  /** One line for the settings page. */
  blurb: string
}

export const DEFAULT_GROUPS: ReadonlyArray<{ id: string; label: string }> = [
  { id: 'views', label: 'Views' },
  { id: 'lenses', label: 'Entries' },
  { id: 'system', label: 'System' },
]

export const CATALOG: NavEntry[] = [
  { key: '/', label: t('Overview'), icon: LayoutDashboard, end: true, home: 'views', blurb: t('all projects on one page') },
  { key: '/kanban', label: t('Kanban'), icon: KanbanSquare, home: 'views', blurb: t('the task boards of all projects') },
  { key: '/calendar', label: t('Calendar'), icon: CalendarDays, home: 'views', blurb: t('due dates, plans, meetings and milestones') },
  { key: '/agent', label: t('Agents'), icon: Users, end: true, home: 'views', blurb: t('every agent and when it worked') },
  { key: '/important', label: t('Important'), icon: Star, home: 'views', blurb: t('the messages, agents and tasks you starred') },
  { key: '/stats', label: t('Statistics'), icon: BarChart3, home: 'views', blurb: t('what each finished task took') },
  { key: '/time', label: t('Timer'), icon: Timer, home: 'views', blurb: t('project timers and time spent') },
  // The chats page moved to /chats on 2026-09-24. The key is what saved
  // layouts hold, so it stays /sessions and only the link changes.
  ...LENS_HEAD_LIST.map((l) => ({
    key: `/${l.base}`,
    ...(l.base === 'sessions' ? { to: '/chats' } : {}),
    label: l.title, icon: l.icon, home: 'lenses', blurb: l.question,
  })),
  { key: '/search', label: t('Search'), icon: Search, home: 'system', blurb: t('search tasks, entries and chats') },
  { key: '/prompts', label: t('Prompts'), icon: MessagesSquare, home: 'system', blurb: t('your saved prompts') },
  { key: '/guide', label: t('Guide'), icon: BookOpenText, home: 'system', blurb: t('how Slightly Parallel is used') },
  { key: '/tour', label: t('Tour'), icon: Clapperboard, home: 'system', blurb: t('walkthroughs of the pages') },
  { key: '/internals', label: t('Internals'), icon: Cog, home: 'system', blurb: t('how chats are recorded') },
  { key: '/terminal', label: t('Terminal'), icon: SquareTerminal, home: 'system', blurb: t('shells and agents, on this computer') },
  { key: '/monitor', label: t('Monitor'), icon: Activity, home: 'system', blurb: t('this computer\'s load, the server\'s state and log') },
  { key: '/backups', label: t('Backups'), icon: DatabaseBackup, home: 'system', blurb: t('copies of the data folder') },
  { key: '/setup', label: t('Setup'), icon: PlugZap, home: 'system', blurb: t('connect projects') },
  { key: '/settings', label: t('Settings'), icon: SlidersHorizontal, home: 'system', blurb: t('all settings') },
]

export const CATALOG_BY_KEY: ReadonlyMap<string, NavEntry> = new Map(CATALOG.map((e) => [e.key, e]))
