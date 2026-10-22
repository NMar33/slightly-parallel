/**
 * The head of every lens: its route, its title, its icon and the question
 * it answers — what the sidebar and the breadcrumbs need on every page.
 *
 * The rest of a lens (how its entries are written, what they hold, the
 * agent's prompt: `config.tsx`) is several times larger and only the lens
 * pages and the Guide read it, so the app shell loads this file alone.
 * `config.tsx` builds each lens on its head: the two cannot drift apart.
 */

import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  BookOpen,
  Clock,
  FolderGit2,
  Gavel,
  Landmark,
  Lightbulb,
  Package,
  Puzzle,
  Rocket,
  Sunrise,
  Telescope,
  DoorOpen,
} from 'lucide-react'

import { t } from '../i18n/scope/shell'

interface LensHead {
  /** Route segment and API base: `/decisions` ↔ `/api/decisions`. */
  base: string
  title: string
  icon: LucideIcon
  /** The question this lens answers about the project. */
  question: string
}

/** In the order the sidebar and the Guide list them. */
export const LENS_HEAD = {
  scans: { base: 'scans', title: t('Scans'), icon: Telescope, question: t('What each agent changed since its last scan.') },
  standups: { base: 'standups', title: t('Standups'), icon: Sunrise, question: t('What changed yesterday, what went wrong, and what needs your answer.') },
  decisions: { base: 'decisions', title: t('Decisions'), icon: Gavel, question: t('What was chosen, why, and what was rejected.') },
  entrypoints: { base: 'entrypoints', title: t('Entry points'), icon: DoorOpen, question: t('The way into each topic: where it lives, how to run it, where the work stopped.') },
  sprints: { base: 'sprints', title: t('Sprints'), icon: Rocket, question: t('What a block of work covers, and how much of its budget is spent.') },
  sessions: { base: 'sessions', title: t('Chats'), icon: Clock, question: t('Every chat with an agent, when and for how long.') },
  visions: { base: 'visions', title: t('Visions'), icon: Lightbulb, question: t('Ideas about where the product should go.') },
  skills: { base: 'skills', title: t('Skills'), icon: Puzzle, question: t('Instructions agents load for a repeated task.') },
  artifacts: { base: 'artifacts', title: t('Artifacts'), icon: Package, question: t('What the agents produced that you can keep and open.') },
  problems: { base: 'problems', title: t('Problems'), icon: AlertTriangle, question: t('What is blocked and what was tried.') },
  rules: { base: 'rules', title: t('Rules'), icon: BookOpen, question: t('Rules agents follow, written after something went wrong.') },
  files: { base: 'files', title: t('Files'), icon: FolderGit2, question: t('Which files changed, and how much each matters.') },
  architecture: { base: 'architecture', title: t('Architecture'), icon: Landmark, question: t('What the project is now, what it is made of, and what each scan changed in it.') },
} satisfies Record<string, LensHead>

/** The same heads, by any route segment (undefined for one that is not a lens). */
export const LENS_HEADS: Record<string, LensHead | undefined> = LENS_HEAD

export const LENS_HEAD_LIST: LensHead[] = Object.values<LensHead>(LENS_HEAD)
