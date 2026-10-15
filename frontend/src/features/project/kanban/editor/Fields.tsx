/*
 * The task window's field rows: priority, assignee, due, milestone and
 * tags; the project ticks of a combined board; and the value axes
 * (impact, effort, tokens, novelty). Moved out of TaskEditor.tsx; the
 * window owns every value, these rows draw and change them.
 */

import { Segmented } from '../../../../components/Segmented'
import { PillGroup, ValueInfo } from '../parts'
import type { ModalPrefs } from '../model'
import { FIELD, LABEL } from '../../../promptlib/taskstyle'
import type { MilestoneOption } from './types'
import { t } from '../../../../i18n/scope/project'

/** Metadata row: priority + assignee + due + milestone + tags. */
export function MetaFields({
  priority, setPriority, assignee, setAssignee, dueDate, setDueDate, milestones, milestoneId, setMilestoneId, tags, setTags,
}: {
  priority: string
  setPriority: (v: string) => void
  assignee: string
  setAssignee: (v: string) => void
  dueDate: string
  setDueDate: (v: string) => void
  milestones: MilestoneOption[]
  milestoneId: string
  setMilestoneId: (v: string) => void
  tags: string
  setTags: (v: string) => void
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
      <div className="flex flex-col gap-3">
        <label htmlFor="task-priority" className={LABEL}>{t('Priority')}</label>
        <select
          id="task-priority"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          className={FIELD}
        >
          <option value="high">{t('high')}</option>
          <option value="med">{t('med')}</option>
          <option value="low">{t('low')}</option>
        </select>
      </div>
      <div className="flex flex-col gap-3">
        <label htmlFor="task-assignee" className={LABEL}>{t('Assignee')}</label>
        <input
          id="task-assignee"
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
          placeholder={t('operator / agent-id / …')}
          className={FIELD}
        />
      </div>
      <div className="flex flex-col gap-3">
        <label htmlFor="task-due" className={LABEL}>{t('Due')}</label>
        <input
          id="task-due"
          value={dueDate}
          onChange={(e) => setDueDate(e.target.value)}
          placeholder={t('YYMM-DD')}
          maxLength={7}
          className={FIELD}
        />
      </div>
      {milestones.length > 0 && milestones.length <= 5 && (
        // A row of its own: a milestone's name is a sentence, not a word.
        <div className="col-span-full flex flex-col gap-3 min-w-0">
          <span className={LABEL} title={t('The milestone this task is for')}>{t('Milestone')}</span>
          <div className="overflow-x-auto">
            <Segmented label={t('Milestone')} value={milestoneId} onChange={setMilestoneId} clearable
              options={milestones.map((m) => [m.id, `${m.title}${m.status === 'reached' ? ' · reached' : ''}`] as const)} />
          </div>
        </div>
      )}
      {milestones.length > 5 && (
        <div className="flex flex-col gap-3">
          <label className={LABEL} title={t('The milestone this task is for')}>{t('Milestone')}</label>
          <select
            value={milestoneId}
            onChange={(e) => setMilestoneId(e.target.value)}
            aria-label={t('Milestone')}
            className={`${FIELD} max-w-[220px]`}
          >
            <option value="">{t('none')}</option>
            {Array.from(new Set(milestones.map((m) => m.project))).map((code) => (
              <optgroup key={code} label={code}>
                {milestones.filter((m) => m.project === code).map((m) => (
                  <option key={m.id} value={m.id}>{m.title}{m.status === 'reached' ? t(' · reached') : ''}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      )}
      <div className="flex flex-col gap-3">
        <label htmlFor="task-tags" className={LABEL}>{t('Tags')}</label>
        <input
          id="task-tags"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder={t('comma,separated')}
          className={FIELD}
        />
      </div>
    </div>
  )
}

/** Projects — only when the board spans several; home = the first tick. */
export function ProjectTicks({ members, projects, homeProject, toggleProject }: {
  members: string[]
  projects: string[]
  homeProject: string
  toggleProject: (code: string) => void
}) {
  return (
    <div className="flex items-center gap-8 flex-wrap">
      <span className={LABEL}>{t('Projects')}</span>
      {[...new Set([...members, ...projects])].map((code) => {
        const on = projects.includes(code)
        const home = code === homeProject
        return (
          <button
            key={code}
            type="button"
            role="checkbox"
            aria-checked={on}
            onClick={() => toggleProject(code)}
            className={`inline-flex items-center gap-4 px-8 h-24 rounded-input border text-11 font-mono transition-colors ${
              on ? 'border-brand text-brand bg-brand/8' : 'border-border-default text-tertiary hover:text-primary'
            }`}
            title={home ? t('Home project, where the task is stored') : on ? 'Member — click to remove' : t('Click to add')}
          >
            <span className={`inline-block w-8 h-8 rounded-bar ${on ? 'bg-brand' : 'border border-border-default'}`} aria-hidden />
            {code}
            {home && <span className="text-tertiary">{t('· home')}</span>}
          </button>
        )
      })}
    </div>
  )
}

/** Value rows: the axes the operator chose to see (gear → Axes). */
export function ValueAxes({ axes, impact, setImpact, effort, setEffort, tokens, setTokens, novelty, setNovelty }: {
  axes: ModalPrefs['axes']
  impact: string
  setImpact: (v: string) => void
  effort: string
  setEffort: (v: string) => void
  tokens: string
  setTokens: (v: string) => void
  novelty: string
  setNovelty: (v: string) => void
}) {
  return (
    <div className="flex items-center gap-16 flex-wrap">
      {axes.impact && (
        <PillGroup label={t('Impact')} value={impact} onChange={setImpact}
          options={[['low', 'low'], ['med', 'med'], ['high', 'high']]} />
      )}
      {axes.effort && (
        <PillGroup label={t('Effort')} value={effort} onChange={setEffort}
          options={[['S', 'S'], ['M', 'M'], ['L', 'L']]} />
      )}
      {axes.tokens && (
        <PillGroup label={t('Tokens')} value={tokens} onChange={setTokens}
          options={[['low', 'low'], ['med', 'med'], ['high', 'high']]} />
      )}
      {axes.novelty && (
        <PillGroup label={t('Novelty')} value={novelty} onChange={setNovelty}
          options={[['routine', 'routine'], ['fresh', 'fresh'], ['killer', 'killer']]} />
      )}
      <ValueInfo />
    </div>
  )
}
