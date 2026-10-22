import { EmptyState } from '../../components/states'

import { t } from '../../i18n/scope/views'
import { rich } from '../../i18n/rich'
/**
 * What a day book says when the project on show has nothing of its kind:
 * that there is none, when one will appear, and how to write one now.
 *
 * The month band above it already says "No scan this month" when the month
 * is bare but the project has entries elsewhere. This is the other case —
 * the project has none at all — so the two never appear together.
 */
export function NoEntriesYet({ name, project, when, command, verb }: {
  /** The page's name, plural and lower case: scans, standups, decisions. */
  name: string
  /** The project on show. */
  project: string
  /** When one appears: "When an agent makes a scan in this project". */
  when: string
  /** The command that writes one, with its hash: #scan. */
  command: string
  /** What the command does: "make one", "write one". */
  verb: string
}) {
  return (
    <EmptyState
      title={t('There are no {name} in {v}.', { name, v: project || t('this project') })}
      subtitle={<>{rich(t('{when}, you will see it here. To {verb} now, type {command} in a chat in this project.'), { when, verb, command: <code className="font-mono text-12">{command}</code> })}</>}
    />
  )
}
