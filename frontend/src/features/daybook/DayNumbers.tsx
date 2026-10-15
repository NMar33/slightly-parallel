import { AgentName } from '../../components/AgentName'
import { minutesLabel, type DayNumbers as Numbers } from './data'

import { t, tn } from '../../i18n/scope/views'
/**
 * The numbers of one day as quiet mono chips: who, how much was said, what
 * moved on the board, what was committed, how long. Zeros are left out.
 */
export function DayNumbersRow({ n, compact = false, agents = true }: {
  n: Numbers; compact?: boolean
  /** The agents' names first; focus mode lists the agents in a section of their own. */
  agents?: boolean
}) {
  const chips: string[] = []
  if (n.messages_n) chips.push(tn(n.messages_n, '{n} message', '{n} messages'))
  if (n.tasks_done_n || n.tasks_moved_n) chips.push(t('{done} done · {moved} moved', { done: n.tasks_done_n, moved: n.tasks_moved_n }))
  if (n.tasks_created_n) chips.push(t('{tasks_created_n} new tasks', { tasks_created_n: n.tasks_created_n }))
  if (n.commits_n) chips.push(`${tn(n.commits_n, '{n} commit', '{n} commits')} · ${tn(n.files_n, '{n} file', '{n} files')}`)
  if (n.lines_add || n.lines_del) chips.push(`+${n.lines_add} −${n.lines_del}`)
  if (n.decisions_n) chips.push(tn(n.decisions_n, '{n} decision', '{n} decisions'))
  if (n.session_minutes) {
    chips.push(n.agent_minutes ? t('agents {minutesLabel} of {minutesLabel2}', { minutesLabel: minutesLabel(n.agent_minutes), minutesLabel2: minutesLabel(n.session_minutes) }) : minutesLabel(n.session_minutes))
  }
  if (n.tracked_minutes) chips.push(t('{time} tracked', { time: minutesLabel(n.tracked_minutes) }))
  const who = agents ? n.agents : []
  if (!chips.length && !who.length) return null
  return (
    <div className={`flex items-center gap-8 flex-wrap ${compact ? 'text-10' : 'text-11'} font-mono text-tertiary tabular`}>
      {who.length > 0 && (
        <span className="text-secondary inline-flex gap-6 flex-wrap">
          {who.map((a) => <AgentName key={a} id={a} />)}
        </span>
      )}
      {chips.map((c) => <span key={c}>{c}</span>)}
    </div>
  )
}
