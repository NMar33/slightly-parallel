
import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '../../components/primitives/Button'
import { FIELD, LABEL } from '../promptlib/taskstyle'
import { normaliseTags, tagsOf, useSetTags, type KeptKind, type Vision } from '../visions/data'
import { t, t as tt } from '../../i18n/scope/system'

/**
 * v01-02's own parts: the tag row every section carries, and the set — a
 * hand-picked, ordered group of visions from any chapter or project, kept in
 * this browser and copied as one piece for an agent.
 */

/** The drag payload: a vision id, dropped on a chapter to add its tag. */
export const DRAG_TYPE = 'application/x-sp-vision'

/** Tags as chips with ×, and "+ tag" opening the task window's comma field. */
export function TagRow({ v, known, kind = 'vision' }: { v: Vision; known: string[]; kind?: KeptKind }) {
  const stored = tagsOf(v.row)
  const write = useSetTags(kind)
  // Shown at once; the server's answer replaces it when the list refetches.
  const [local, setLocal] = useState<string[] | null>(null)
  useEffect(() => { setLocal(null) }, [v.row.tags])
  const tags = local ?? stored
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const input = useRef<HTMLInputElement>(null)

  const save = (next: string[]) => {
    setLocal(next)
    write.mutate(
      { id: v.row.id, tags: next },
      { onError: (e) => { setLocal(null); toast.error(String((e as Error).message)) } },
    )
  }
  const start = () => {
    setDraft(tags.length ? `${tags.join(', ')}, ` : '')
    setOpen(true)
    requestAnimationFrame(() => input.current?.focus())
  }
  const typed = normaliseTags(draft)
  const offers = known.filter((t) => !typed.includes(t))
  const commit = () => {
    if (typed.join(',') !== tags.join(',')) save(typed)
    setOpen(false)
  }

  if (open) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-6">
          <label className={LABEL} htmlFor={`tags-${v.row.id}`}>{t('tags')}</label>
          <input
            id={`tags-${v.row.id}`}
            ref={input}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); commit() }
              else if (e.key === 'Escape') { e.preventDefault(); setOpen(false) }
            }}
            placeholder="ui, backend"
            className={`${FIELD} flex-1 min-w-0 h-24`}
          />
          <Button variant="primary" size="sm" onClick={commit}>{t('Save')}</Button>
          <button type="button" onClick={() => setOpen(false)} className="h-24 px-8 rounded-input text-11 font-mono text-tertiary hover:text-primary hover:bg-hover">{t('Cancel')}</button>
        </div>
        {offers.length > 0 && (
          <div className="flex items-center gap-4 flex-wrap pl-[40px]">
            {offers.map((t) => (
              <button
                key={t}
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { setDraft(`${normaliseTags(`${draft},${t}`).join(', ')}, `); input.current?.focus() }}
                className="h-20 px-8 rounded-pill border border-border-subtle text-11 font-mono text-tertiary hover:text-brand hover:border-brand"
              >
                {t}
              </button>
            ))}
          </div>
        )}
        <span className="pl-[40px] text-10 font-mono text-tertiary">{t('Enter saves · Esc cancels')}</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-6 flex-wrap">
      {tags.map((t) => (
        <span key={t} className="inline-flex items-center gap-2 pl-8 pr-3 h-20 rounded-pill bg-elevated border border-border-subtle text-11 font-mono text-secondary">
          {t}
          <button type="button" aria-label={tt('Remove tag {tag}', { tag: t })} title={tt('Remove tag')} onClick={() => save(tags.filter((x) => x !== t))}
            className="text-tertiary hover:text-status-red p-2 rounded-pill">
            <X size={10} aria-hidden />
          </button>
        </span>
      ))}
      <button type="button" onClick={start}
        className="h-20 px-8 rounded-pill border border-dashed border-border-default text-11 font-mono text-tertiary hover:text-brand hover:border-brand">
        {tt('+ tag')}
      </button>
    </div>
  )
}
