import { copyText as copy } from '../../lib/useCopy'
import { useEffect, useRef, useState } from 'react'
import { usePopover } from '../../hooks/usePopover'
import { ArrowDown, ArrowUp, Check, ChevronDown, ChevronRight, Copy, ListPlus, Pencil, Plus, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'

import { fail } from '../../lib/getJson'
import { Button } from '../../components/primitives/Button'
import { Confirm } from '../../components/Confirm'
import { FIELD, LABEL } from '../promptlib/taskstyle'
import { cleanTitle, tagsOf, visionText, type KeptSet, type SetWrites, type Vision } from '../visions/data'
import { DRAG_TYPE } from './tags'
import { t, tn } from '../../i18n/scope/system'
import { plural } from '../../utils/format'

/** A count of a kept kind, in the interface language: "3 visions". */
const KIND_N: Record<string, (n: number) => string> = {
  vision: (n) => tn(n, '{n} vision', '{n} visions'),
  rule: (n) => tn(n, '{n} rule', '{n} rules'),
  problem: (n) => tn(n, '{n} problem', '{n} problems'),
}
export const kindN = (n: number, kind: string) => KIND_N[kind]?.(n) ?? plural(n, kind)

/**
 * Saved sets of visions, rules or problems: the panel that makes, renames,
 * orders and deletes them (and, where there is a Projects panel, lets a set
 * be dragged onto a project to be written into its AGENTS.md), and the
 * menu an entry or a chapter uses to join one. Sets are on the server, so
 * they are the same in every browser.
 */

/** The drag payload for a whole set: "kind:id". */
export const SET_DRAG_TYPE = 'application/x-sp-set'

/** What Copy set puts on the clipboard: the set's name, then each vision in order. */
function setText(s: KeptSet, visions: Vision[]): string {
  const byId = new Map(visions.map((v) => [v.row.id, v]))
  const items = s.items.map((id) => byId.get(id)).filter((v): v is Vision => !!v)
  return `# ${s.name}\n\n${items.map(visionText).join('\n')}`
}

/** A set name field: Enter or leaving the field saves, Esc cancels. */
function NameField({
  initial, onSubmit, onCancel,
}: {
  initial: string
  onSubmit: (name: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initial)
  const done = useRef(false)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { input.current?.focus(); input.current?.select() }, [])
  const finish = (save: boolean) => {
    if (done.current) return
    done.current = true
    if (save && name.trim() && name.trim() !== initial) onSubmit(name.trim())
    else onCancel()
  }
  return (
    <input
      ref={input}
      value={name}
      onChange={(e) => setName(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.preventDefault(); finish(true) }
        else if (e.key === 'Escape') { e.preventDefault(); finish(false) }
      }}
      onBlur={() => finish(true)}
      placeholder={t('Set name')}
      aria-label={t('Set name')}
      maxLength={80}
      className={`${FIELD} w-full h-24`}
    />
  )
}

/** "Add to set" for one vision or a whole chapter: tick the sets it belongs to, or make a new one. */
export function AddToSetMenu({
  ids, sets, writes, label = t('Add to set'),
}: {
  ids: string[]
  sets: KeptSet[]
  writes: SetWrites
  label?: string
}) {
  const { open, setOpen, rootRef } = usePopover<HTMLDivElement>()
  // The menu opens on its list, never on a half-typed new name.
  const [naming, setNaming] = useState(false)

  const holds = (s: KeptSet) => ids.length > 0 && ids.every((id) => s.items.includes(id))
  const inSets = ids.length === 1 ? sets.filter(holds).length : 0
  const toggle = (s: KeptSet) => {
    const leaving = holds(s)
    const items = leaving ? s.items.filter((x) => !ids.includes(x)) : [...s.items, ...ids.filter((x) => !s.items.includes(x))]
    writes.update.mutate(
      { id: s.id, items },
      { onSuccess: () => toast.success(leaving ? t('Removed from {name}', { name: s.name }) : t('Added to {name}', { name: s.name })), onError: fail },
    )
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => { if (!open) setNaming(false); setOpen(!open) }}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`inline-flex items-center gap-4 text-11 font-mono ${inSets ? 'text-brand' : 'text-tertiary hover:text-brand'}`}
      >
        {inSets ? <Check size={12} aria-hidden /> : <ListPlus size={12} aria-hidden />}
        {inSets ? tn(inSets, 'In {n} set', 'In {n} sets') : label}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full mt-4 z-30 w-[240px] rounded-card border border-border-default bg-surface shadow-md py-4 flex flex-col">
          {sets.length === 0 && <p className="px-10 py-4 text-12 text-tertiary">{t('No sets yet.')}</p>}
          {sets.map((s) => {
            const on = holds(s)
            return (
              <button
                key={s.id}
                type="button"
                role="menuitemcheckbox"
                aria-checked={on}
                onClick={() => toggle(s)}
                className="flex items-center gap-8 px-10 h-[28px] text-left text-12 text-secondary hover:bg-hover hover:text-primary"
              >
                <span className={`h-12 w-12 shrink-0 rounded-[3px] border flex items-center justify-center ${on ? 'bg-brand border-brand text-on-brand' : 'border-border-default'}`}>
                  {on && <Check size={9} aria-hidden />}
                </span>
                <span className="flex-1 min-w-0 truncate">{s.name}</span>
                <span className="text-10 font-mono text-tertiary tabular">{s.items.length}</span>
              </button>
            )
          })}
          <div className="border-t border-border-subtle mt-4 pt-4 px-10 pb-2">
            {naming ? (
              <NameField
                initial=""
                onSubmit={(name) => {
                  writes.create.mutate({ name, items: ids }, { onSuccess: (s) => toast.success(t('Added to {name}', { name: s.name })), onError: fail })
                  setNaming(false)
                  setOpen(false)
                }}
                onCancel={() => setNaming(false)}
              />
            ) : (
              <button type="button" onClick={() => setNaming(true)}
                className="flex items-center gap-6 h-[26px] text-12 text-secondary hover:text-brand">
                <Plus size={12} aria-hidden /> {t('New set')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/** Every saved set: one open at a time to order, rename, copy or delete. A vision dropped on a set joins it. */
export function SetsPanel({
  sets, visions, writes, active, onActive, noun = 'vision', draggable = false, complete,
}: {
  sets: KeptSet[]
  visions: Vision[]
  writes: SetWrites
  /** The records of entries not read yet, so a copy holds their words. */
  complete?: (vs: Vision[]) => Promise<Vision[]>
  active: string
  onActive: (id: string) => void
  /** What the entries are called: vision, rule, problem. */
  noun?: string
  /** Each set can be dragged onto a project to be written into its AGENTS.md. */
  draggable?: boolean
}) {
  const [open, setOpen] = useState(true)
  const [creating, setCreating] = useState(false)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const byId = new Map(visions.map((v) => [v.row.id, v]))

  const addTo = (s: KeptSet, id: string) => {
    if (s.items.includes(id)) { toast(t('Already in {name}', { name: s.name })); return }
    writes.update.mutate({ id: s.id, items: [...s.items, id] }, { onSuccess: () => toast.success(t('Added to {name}', { name: s.name })), onError: fail })
  }
  const move = (s: KeptSet, id: string, by: -1 | 1) => {
    const i = s.items.indexOf(id)
    const j = i + by
    if (i < 0 || j < 0 || j >= s.items.length) return
    const next = [...s.items]
    ;[next[i], next[j]] = [next[j]!, next[i]!]
    writes.update.mutate({ id: s.id, items: next }, { onError: fail })
  }

  return (
    <aside aria-label={t('Sets')} className="rounded-card border border-border-subtle bg-surface flex flex-col min-w-0">
      <div className="flex items-center gap-6 pl-4 pr-10 h-32">
        <button type="button" onClick={() => setOpen((x) => !x)} aria-expanded={open}
          className="flex items-center gap-6 px-8 h-24 rounded-input hover:bg-hover">
          {open ? <ChevronDown size={12} className="text-tertiary" aria-hidden /> : <ChevronRight size={12} className="text-tertiary" aria-hidden />}
          <span className={LABEL}>{t('Sets')}</span>
          <span className="text-11 font-mono text-tertiary tabular">{sets.length}</span>
        </button>
        <Button variant="text" size="bare" className="ml-auto" iconLeft={<Plus size={12} aria-hidden />}
          onClick={() => { setOpen(true); setCreating(true) }}>
          {t('New set')}
        </Button>
      </div>

      {open && (
        <>
          {creating && (
            <div className="px-12 pb-8">
              <NameField
                initial=""
                onSubmit={(name) => {
                  writes.create.mutate({ name }, { onSuccess: (s) => { onActive(s.id); toast.success(t('Created {name}', { name: s.name })) }, onError: fail })
                  setCreating(false)
                }}
                onCancel={() => setCreating(false)}
              />
            </div>
          )}
          {sets.length === 0 && !creating && (
            <p className="px-12 pb-12 text-12 text-tertiary leading-relaxed">
              {t('No sets yet. Use New set, or Add to set on a {noun}.', { noun: t(noun) })}
            </p>
          )}
          <div className="flex flex-col">
            {sets.map((s) => {
              const on = s.id === active
              const items = s.items.map((id) => byId.get(id)).filter((v): v is Vision => !!v)
              const hot = over === s.id
              return (
                <div
                  key={s.id}
                  className={`border-t ${hot ? 'border-brand bg-brand-glow' : 'border-border-subtle'}`}
                  onDragOver={(e) => {
                    if (!e.dataTransfer.types.includes(DRAG_TYPE)) return
                    e.preventDefault()
                    e.dataTransfer.dropEffect = 'copy'
                    setOver(s.id)
                  }}
                  onDragLeave={() => setOver((o) => (o === s.id ? null : o))}
                  onDrop={(e) => {
                    e.preventDefault()
                    setOver(null)
                    const id = e.dataTransfer.getData(DRAG_TYPE)
                    if (id) addTo(s, id)
                  }}
                >
                  {renaming === s.id ? (
                    <div className="px-12 py-4">
                      <NameField
                        initial={s.name}
                        onSubmit={(name) => {
                          writes.update.mutate({ id: s.id, name }, { onSuccess: () => toast.success(t('Renamed to {name}', { name })), onError: fail })
                          setRenaming(null)
                        }}
                        onCancel={() => setRenaming(null)}
                      />
                    </div>
                  ) : (
                    <button type="button" onClick={() => onActive(on ? '' : s.id)} aria-expanded={on}
                      draggable={draggable}
                      onDragStart={draggable ? (e) => {
                        e.dataTransfer.setData(SET_DRAG_TYPE, `${s.kind}:${s.id}`)
                        e.dataTransfer.effectAllowed = 'copy'
                      } : undefined}
                      title={draggable ? t('Drag onto a project to write it to AGENTS.md') : undefined}
                      className={`w-full flex items-center gap-6 px-12 h-32 text-left hover:bg-hover ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}`}>
                      {on ? <ChevronDown size={12} className="text-tertiary shrink-0" aria-hidden /> : <ChevronRight size={12} className="text-tertiary shrink-0" aria-hidden />}
                      <span className={`flex-1 min-w-0 truncate text-13 ${on ? 'text-primary font-medium' : 'text-secondary'}`}>{s.name}</span>
                      <span className="text-11 font-mono text-tertiary tabular">{items.length}</span>
                    </button>
                  )}

                  {on && (
                    <>
                      {items.length === 0 ? (
                        <p className="px-12 pb-6 text-12 text-tertiary leading-relaxed">
                          {t('Empty. Drag a {noun} here, or use Add to set.', { noun: t(noun) })}
                        </p>
                      ) : (
                        <ol className="flex flex-col">
                          {items.map((v, i) => (
                            <li key={v.row.id} className="flex items-start gap-6 pl-24 pr-10 py-6 border-t border-border-subtle">
                              <span className="text-10 font-mono text-tertiary tabular w-[14px] pt-2 shrink-0">{i + 1}</span>
                              <button type="button" className="flex-1 min-w-0 text-left"
                                onClick={() => document.getElementById(`vision-${v.row.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
                                <span className="block text-12 text-primary leading-snug line-clamp-2 hover:text-brand">{cleanTitle(v.row.l1)}</span>
                                <span className="block text-10 font-mono text-tertiary truncate">{v.row.project} · {tagsOf(v.row).join(', ') || t('no tag')}</span>
                              </button>
                              <span className="flex flex-col shrink-0">
                                <button type="button" aria-label={t('Move {what} up', { what: cleanTitle(v.row.l1) })} title={t('Move up')} disabled={i === 0}
                                  onClick={() => move(s, v.row.id, -1)} className="text-tertiary hover:text-primary disabled:opacity-30 p-1">
                                  <ArrowUp size={11} aria-hidden />
                                </button>
                                <button type="button" aria-label={t('Move {what} down', { what: cleanTitle(v.row.l1) })} title={t('Move down')} disabled={i === items.length - 1}
                                  onClick={() => move(s, v.row.id, 1)} className="text-tertiary hover:text-primary disabled:opacity-30 p-1">
                                  <ArrowDown size={11} aria-hidden />
                                </button>
                              </span>
                              <button type="button" aria-label={t('Remove {what} from {set}', { what: cleanTitle(v.row.l1), set: s.name })} title={t('Remove from set')}
                                onClick={() => writes.update.mutate({ id: s.id, items: s.items.filter((x) => x !== v.row.id) }, { onError: fail })}
                                className="text-tertiary hover:text-status-red p-2 shrink-0">
                                <X size={12} aria-hidden />
                              </button>
                            </li>
                          ))}
                        </ol>
                      )}
                      {deleting === s.id ? (
                        <div className="px-12 py-8 border-t border-border-subtle">
                          <Confirm
                            text={t('Delete {name}', { name: s.name })}
                            action={t('Delete')}
                            onYes={() => {
                              writes.remove.mutate(s.id, { onSuccess: () => toast.success(t('Deleted {name}', { name: s.name })), onError: fail })
                              setDeleting(null)
                              onActive('')
                            }}
                            onNo={() => setDeleting(null)}
                          />
                        </div>
                      ) : (
                        <div className="flex items-center gap-12 px-12 py-8 border-t border-border-subtle flex-wrap">
                          <Button variant="primary" size="sm" disabled={!items.length}
                            iconLeft={<Copy size={12} aria-hidden />}
                            onClick={async () => {
                              // Completing the set reads every entry from the server, and that may fail.
                              try {
                                const full = complete ? await complete(items) : items
                                void copy(setText(s, full), t('Copied {what}', { what: `${s.name} · ${kindN(items.length, noun)}` }))
                              } catch (e) {
                                toast.error(t('The set could not be read: {error}', { error: e instanceof Error ? e.message : String(e) }))
                              }
                            }}>
                            {t('Copy set')}
                          </Button>
                          <Button variant="text" size="bare" iconLeft={<Pencil size={11} aria-hidden />}
                            onClick={() => setRenaming(s.id)}>
                            {t('Rename')}
                          </Button>
                          <Button variant="danger-text" size="bare" iconLeft={<Trash2 size={11} aria-hidden />}
                            onClick={() => setDeleting(s.id)}>
                            {t('Delete')}
                          </Button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </aside>
  )
}
