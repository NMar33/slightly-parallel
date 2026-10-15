import { FIELD, LABEL } from '../promptlib/taskstyle'
import { MAX_DESCRIPTION, descriptionProblem, nameProblem, type SkillFields } from './frontmatter'
import { t } from '../../i18n/scope/system'

/**
 * The three fields of a skill — name, description, steps — as the task
 * window draws them: labelled mono fields, the reason under a field that the
 * server would refuse. The opened skill and New skill both use this form.
 */

export function SkillFieldsForm({
  id, fields, onChange,
}: {
  id: string
  fields: SkillFields
  onChange: (next: SkillFields) => void
}) {
  const set = (patch: Partial<SkillFields>) => onChange({ ...fields, ...patch })
  const nameWrong = nameProblem(fields.name)
  const descWrong = descriptionProblem(fields.description)
  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-col gap-3">
        <label className={LABEL} htmlFor={`skill-name-${id}`}>{t('name · the folder agents see')}</label>
        <input id={`skill-name-${id}`} value={fields.name} spellCheck={false}
          aria-invalid={nameWrong ? true : undefined}
          onChange={(e) => set({ name: e.target.value })} className={FIELD} />
        {nameWrong && <span className="text-11 text-status-red">{nameWrong}</span>}
      </div>
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline gap-8">
          <label className={LABEL} htmlFor={`skill-desc-${id}`}>{t('description · agents read this to choose the skill')}</label>
          <span className={`ml-auto text-10 font-mono tabular ${descWrong ? 'text-status-red' : 'text-tertiary'}`}>
            {fields.description.length} / {MAX_DESCRIPTION}
          </span>
        </div>
        <textarea id={`skill-desc-${id}`} value={fields.description} spellCheck={false} rows={3}
          aria-invalid={descWrong ? true : undefined}
          onChange={(e) => set({ description: e.target.value })}
          className={`${FIELD} leading-relaxed resize-y`} />
        {descWrong && <span className="text-11 text-status-red">{descWrong}</span>}
      </div>
      <div className="flex flex-col gap-3">
        <label className={LABEL} htmlFor={`skill-body-${id}`}>{t('steps')}</label>
        <textarea id={`skill-body-${id}`} value={fields.body} spellCheck={false}
          onChange={(e) => set({ body: e.target.value })}
          rows={Math.min(28, Math.max(10, fields.body.split('\n').length + 1))}
          className={`${FIELD} leading-relaxed resize-y`} />
      </div>
    </div>
  )
}

/** Whether the server would take these fields. */
export const fieldsOk = (f: SkillFields) => !nameProblem(f.name) && !descriptionProblem(f.description)
