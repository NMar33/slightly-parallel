/*
 * The task window's "then" rows (new tasks only): the steps typed after
 * the first one, created with it as a stack. Moved out of TaskEditor.tsx;
 * the window owns the steps and creates them on save.
 */

import { useRef, type Dispatch, type SetStateAction } from 'react'
import { Layers } from 'lucide-react'
import { Button } from '../../../../components/primitives'
import { stepClash } from '../parts'
import { t } from '../../../../i18n/scope/project'

/** The stack: what comes after this one, created with it. */
export function ThenSteps({ title, thenSteps, setThenSteps }: {
  title: string
  thenSteps: string[]
  setThenSteps: Dispatch<SetStateAction<string[]>>
}) {
  // A key a row, kept beside the steps (which stay plain strings for the
  // window): keyed by position, taking a middle step out left the keyboard
  // in a field that now showed the next step's text. Rows are added at the
  // end and removed here; the window only ever empties the list.
  const keys = useRef<number[]>([])
  const nextKey = useRef(0)
  while (keys.current.length < thenSteps.length) keys.current.push(nextKey.current++)
  keys.current.length = thenSteps.length
  const fields = useRef(new Map<number, HTMLInputElement>())
  const removeAt = (i: number, focusBefore = false) => {
    const before = keys.current[i - 1]
    keys.current.splice(i, 1)
    setThenSteps((cur) => cur.filter((_, j) => j !== i))
    // Backspace on an empty step goes back to the one above it.
    if (focusBefore && before !== undefined) fields.current.get(before)?.focus()
  }
  return (
    <div className="flex flex-col gap-4">
      {thenSteps.map((step, i) => (
        <div key={keys.current[i]} className="flex items-center gap-6">
          <span className="text-11 font-mono text-tertiary w-[52px] text-right">{t('then')}</span>
          <input
            ref={(el) => { const k = keys.current[i]!; if (el) fields.current.set(k, el); else fields.current.delete(k) }}
            value={step}
            onChange={(e) => setThenSteps((cur) => cur.map((x, j) => (j === i ? e.target.value : x)))}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); setThenSteps((cur) => [...cur, '']) }
              if (e.key === 'Backspace' && !step && thenSteps.length > 0) {
                e.preventDefault(); removeAt(i, true)
              }
            }}
            placeholder={`step ${i + 2}…`}
            aria-label={`Step ${i + 2} of the stack`}
            className="flex-1 bg-elevated border border-border-default rounded-input px-8 py-4 text-12 text-primary outline-none focus:border-brand"
          />
          <Button variant="danger-text" size="bare" onClick={() => removeAt(i)}
            aria-label={`Remove step ${i + 2}`} className="px-2">×</Button>
        </div>
      ))}
      <div className="flex items-center gap-6">
        <span className="w-[52px]" aria-hidden />
        <Button
          variant="text"
          size="bare"
          onClick={() => setThenSteps((cur) => [...cur, ''])}
          title={t('Add a task to follow this one. Both are created with the same settings, and the board shows one at a time.')}
        >
          <Layers size={10} aria-hidden />
          {thenSteps.length ? t('Add another step') : t('Add a next step')}
        </Button>
        {thenSteps.filter((x) => x.trim()).length > 0 && (
          <span className="text-10 font-mono text-tertiary">
            {thenSteps.filter((x) => x.trim()).length + 1} {t('steps. The board shows one step at a time.')}
          </span>
        )}
        {stepClash(title, thenSteps) && (
          <span role="alert" className="text-10 font-mono text-status-red">
            {t('Two steps are named “{name}”. They would become one task. Change one.', { name: stepClash(title, thenSteps) ?? '' })}
          </span>
        )}
      </div>
    </div>
  )
}
