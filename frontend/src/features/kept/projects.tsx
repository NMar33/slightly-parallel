import { useEffect, useState } from 'react'
import { usePopover } from '../../hooks/usePopover'
import { createPortal } from 'react-dom'
import { ChevronDown, ChevronRight, Plus, RefreshCw, X } from 'lucide-react'
import { toast } from 'sonner'

import { fail } from '../../lib/getJson'
import { Button } from '../../components/primitives/Button'
import { Confirm } from '../../components/Confirm'
import { LABEL } from '../promptlib/taskstyle'
import { Modal } from '../../components/Modal'
import {
  ALL_RULES, useIntegrate, useIntegrateTargets, useIntegrations, useSets, useSyncAllRules,
  type KeptKind, type KeptSet, type SetIntegration,
} from '../visions/data'
import { SET_DRAG_TYPE } from './sets'
import { t, t as tt } from '../../i18n/scope/system'

/**
 * Integrate by project: the projects set up in Setup, each listing the sets
 * written into its AGENTS.md — visions, rules and problems alike — with the
 * state of each copy. A set is added from the project's menu or by dropping
 * it on the project; either way the exact block is shown before it is written.
 */

const KINDS: KeptKind[] = ['vision', 'rule', 'problem']
const KIND_LABEL: Record<string, string> = { vision: t('Visions'), rule: t('Rules'), problem: t('Problems') }
const KIND_ONE: Record<string, string> = { vision: t('visions'), rule: t('rules'), problem: t('problems') }

const STATUS: Record<SetIntegration['status'], { text: string; cls: string }> = {
  fresh: { text: t('current'), cls: 'text-status-green border-status-green/40 bg-status-green/10' },
  stale: { text: t('older copy'), cls: 'text-status-amber border-status-amber/40 bg-status-amber/10' },
  missing: { text: t('removed from the file'), cls: 'text-status-red border-status-red/40 bg-status-red/10' },
}

/** "/home/me/work/atlas" → "…/work/atlas/AGENTS.md" */
function shortPath(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return `…/${parts.slice(-2).join('/')}/AGENTS.md`
}

function useAllSets(): KeptSet[] {
  const v = useSets('vision').data ?? []
  const r = useSets('rule').data ?? []
  const p = useSets('problem').data ?? []
  return [...v, ...r, ...p]
}

interface Pending {
  setId: string
  project: string
}

/** The sets a project does not hold yet, grouped by kind. */
function AddSetMenu({ sets, written, onPick }: { sets: KeptSet[]; written: string[]; onPick: (setId: string) => void }) {
  const { open, setOpen, rootRef } = usePopover<HTMLDivElement>()
  const free = sets.filter((s) => !written.includes(s.id))

  return (
    <div ref={rootRef} className="relative">
      <Button variant="text" size="bare" onClick={() => setOpen((x) => !x)} aria-haspopup="menu" aria-expanded={open}
        iconLeft={<Plus size={12} aria-hidden />}>
        {t('Add a set')}
      </Button>
      {open && (
        <div role="menu" className="absolute left-0 top-full mt-4 z-30 w-[240px] max-h-[320px] overflow-y-auto rounded-card border border-border-default bg-surface shadow-md py-4 flex flex-col">
          {free.length === 0 && <p className="px-10 py-4 text-12 text-tertiary">{t('All sets are already in this project.')}</p>}
          {KINDS.map((k) => {
            const group = free.filter((s) => s.kind === k)
            if (!group.length) return null
            return (
              <div key={k} className="flex flex-col">
                <span className={`${LABEL} px-10 pt-6 pb-2`}>{KIND_LABEL[k]}</span>
                {group.map((s) => (
                  <button key={s.id} type="button" role="menuitem"
                    onClick={() => { setOpen(false); onPick(s.id) }}
                    className="flex items-center gap-8 px-10 h-[28px] text-left text-12 text-secondary hover:bg-hover hover:text-primary">
                    <span className="flex-1 min-w-0 truncate">{s.name}</span>
                    <span className="text-10 font-mono text-tertiary tabular">{s.items.length}</span>
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

const WHAT_HAPPENS: Record<string, string> = {
  created: t('A new AGENTS.md will be created with this set.'),
  appended: t('The set will be added at the end of AGENTS.md.'),
  updated: t("The set's block in AGENTS.md will be replaced with this text."),
  unchanged: t('AGENTS.md already has this text.'),
}

/** The exact block, and where it goes, before anything is written. */
function PreviewDialog({ pending, set, onClose }: { pending: Pending; set?: KeptSet; onClose: () => void }) {
  const { preview, apply } = useIntegrate()
  const { mutate } = preview
  useEffect(() => { mutate({ setId: pending.setId, project: pending.project }) }, [mutate, pending.setId, pending.project])
  const data = preview.data
  const name = set?.name ?? pending.setId

  const write = () =>
    apply.mutate(
      { setId: pending.setId, project: pending.project },
      { onSuccess: () => { toast.success(t('Written to {project}', { project: pending.project })); onClose() }, onError: fail },
    )

  // Portalled to the body: the panel sits in a sticky column, which would
  // otherwise trap the overlay under the document beside it.
  return createPortal(
    <Modal label={t('Write {name} to {project}', { name, project: pending.project })} onClose={onClose} width="w-[720px]" padding="p-20">
      <div className="flex flex-col gap-12">
        <div className="flex items-start gap-12">
          <div className="flex flex-col gap-2 min-w-0">
            <h2 id="integrate-title" className="text-16 font-semibold text-primary leading-snug">
              {t('Write {name} to {project}', { name, project: pending.project })}
            </h2>
            <span className="text-11 font-mono text-tertiary">
              {set ? `${set.items.length} ${KIND_ONE[set.kind] ?? t('entries')}` : ''}
            </span>
          </div>
          <button type="button" onClick={onClose} aria-label={t('Close')} className="ml-auto text-tertiary hover:text-primary p-2">
            <X size={16} aria-hidden />
          </button>
        </div>

        {preview.isPending && <p className="text-12 font-mono text-tertiary">{t('Reading AGENTS.md…')}</p>}
        {preview.isError && <p className="text-12 text-status-red">{String((preview.error as Error).message)}</p>}

        {data && (
          <>
            <div className="flex flex-col gap-3">
              <span className={LABEL}>{t('file')}</span>
              <span className="text-12 font-mono text-secondary break-all">{data.file}</span>
            </div>
            <p className="text-13 text-primary">{WHAT_HAPPENS[data.action] ?? ''}</p>
            {data.action === 'updated' && data.previous && (
              <details className="rounded-input border border-border-subtle">
                <summary className="cursor-pointer select-none px-10 h-24 flex items-center text-11 font-mono text-tertiary hover:bg-hover">
                  {t('Now in the file')}
                </summary>
                <pre className="px-12 py-8 text-11 font-mono text-tertiary whitespace-pre-wrap break-words max-h-[200px] overflow-y-auto">{data.previous}</pre>
              </details>
            )}
            <div className="flex flex-col gap-3 min-h-0">
              <div className="flex items-baseline gap-8">
                <span className={LABEL}>{t('text to write')}</span>
                <span className="text-10 font-mono text-tertiary tabular">{t('{n} words', { n: data.words })}</span>
              </div>
              <pre aria-label={t('Text to write')} tabIndex={0}
                className="min-h-0 max-h-[46vh] overflow-y-auto rounded-input border border-border-subtle bg-elevated px-12 py-10 text-12 font-mono text-primary whitespace-pre-wrap break-words">
                {data.content}
              </pre>
            </div>
          </>
        )}

        <div className="flex items-center justify-end gap-8">
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('Cancel')}
          </Button>
          <Button variant="primary" size="sm" onClick={write}
            disabled={!data || data.action === 'unchanged' || apply.isPending}>
            {t('Write to AGENTS.md')}
          </Button>
        </div>
      </div>
    </Modal>,
    document.body,
  )
}

/** Every project set up in Setup, with the sets written into its AGENTS.md. */
export function ProjectsPanel() {
  const targets = useIntegrateTargets().data ?? []
  const integrations = useIntegrations().data ?? []
  const sets = useAllSets()
  const byId = new Map(sets.map((s) => [s.id, s]))
  const { apply, remove } = useIntegrate()
  const syncAll = useSyncAllRules()
  const [open, setOpen] = useState(true)
  const [openProject, setOpenProject] = useState<string | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  /** The set whose block is about to be taken out of a project's AGENTS.md — asked first. */
  const [removing, setRemoving] = useState<Pending | null>(null)

  const takeOut = (setId: string, project: string, name: string) =>
    remove.mutate({ setId, project }, {
      onSuccess: () => { toast.success(t('Removed {name} from {project}', { name, project })); setRemoving(null) },
      onError: fail,
    })

  return (
    <aside aria-label={t('Projects')} className="rounded-card border border-border-subtle bg-surface flex flex-col min-w-0">
      <div className="flex items-center gap-6 pl-4 pr-10 h-32">
        <button type="button" onClick={() => setOpen((x) => !x)} aria-expanded={open}
          className="flex items-center gap-6 px-8 h-24 rounded-input hover:bg-hover">
          {open ? <ChevronDown size={12} className="text-tertiary" aria-hidden /> : <ChevronRight size={12} className="text-tertiary" aria-hidden />}
          <span className={LABEL}>{t('Projects')}</span>
          <span className="text-11 font-mono text-tertiary tabular">{targets.length}</span>
        </button>
      </div>

      {open && (
        <>
          {targets.length === 0 && (
            <p className="px-12 pb-12 text-12 text-tertiary leading-relaxed">{t('No projects are set up. Add one in Setup.')}</p>
          )}
          <div className="flex flex-col">
            {targets.map((t) => {
              const here = integrations.filter((i) => i.project === t.project)
              const isOpen = openProject === t.project
              const hot = over === t.project
              const stale = here.filter((i) => i.status !== 'fresh').length
              return (
                <div key={t.project}
                  className={`border-t ${hot ? 'border-brand bg-brand-glow' : 'border-border-subtle'}`}
                  onDragOver={(e) => {
                    if (!e.dataTransfer.types.includes(SET_DRAG_TYPE)) return
                    e.preventDefault()
                    e.dataTransfer.dropEffect = 'copy'
                    setOver(t.project)
                  }}
                  onDragLeave={() => setOver((o) => (o === t.project ? null : o))}
                  onDrop={(e) => {
                    e.preventDefault()
                    setOver(null)
                    const raw = e.dataTransfer.getData(SET_DRAG_TYPE)
                    const id = raw.split(':')[1]
                    if (id) setPending({ setId: id, project: t.project })
                  }}
                >
                  <button type="button" onClick={() => setOpenProject(isOpen ? null : t.project)} aria-expanded={isOpen}
                    title={`${t.path}/AGENTS.md`}
                    className="w-full flex items-center gap-6 px-12 py-6 text-left hover:bg-hover">
                    {isOpen ? <ChevronDown size={12} className="text-tertiary shrink-0" aria-hidden /> : <ChevronRight size={12} className="text-tertiary shrink-0" aria-hidden />}
                    <span className="flex-1 min-w-0 flex flex-col">
                      <span className={`text-13 truncate ${isOpen ? 'text-primary font-medium' : 'text-secondary'}`}>{t.project}</span>
                      <span className="text-10 font-mono text-tertiary truncate">{shortPath(t.path)}</span>
                    </span>
                    {stale > 0 && <span role="img" className="h-6 w-6 rounded-pill bg-status-amber shrink-0" title={tt('{n} to update', { n: stale })} aria-label={tt('{n} to update', { n: stale })} />}
                    <span className="text-11 font-mono text-tertiary tabular">{here.length}</span>
                  </button>

                  {isOpen && (
                    <div className="flex flex-col pb-8">
                      {here.length === 0 && (
                        <p className="px-12 pl-[30px] py-4 text-12 text-tertiary leading-relaxed">{tt('No sets written here.')}</p>
                      )}
                      {here.map((i) => {
                        // The built-in set is written by Slightly Parallel itself and has no row in sets.
                        const builtIn = i.set_id === ALL_RULES
                        const s = byId.get(i.set_id)
                        const name = builtIn ? tt('Rules for all agents') : s?.name ?? tt('Deleted set {id}', { id: i.set_id })
                        const chip = STATUS[i.status]
                        const asked = removing?.setId === i.set_id && removing.project === t.project
                        return (
                          <div key={i.set_id} className="flex flex-col gap-3 pl-[30px] pr-10 py-6 border-t border-border-subtle">
                            <div className="flex items-baseline gap-6 min-w-0">
                              <span className="flex-1 min-w-0 truncate text-12 text-primary">{name}</span>
                              <span className="text-10 font-mono text-tertiary shrink-0">{builtIn ? tt('Rules') : s ? KIND_LABEL[s.kind] : ''}</span>
                            </div>
                            <div className="flex items-center gap-8 flex-wrap">
                              <span className={`inline-flex items-center h-[18px] px-6 rounded-pill border text-10 font-mono ${chip.cls}`}>{chip.text}</span>
                              {builtIn ? (
                                <span className="ml-auto flex items-center gap-10">
                                  {i.status !== 'fresh' ? (
                                    <Button variant="link" size="bare" className="text-11 font-mono" disabled={syncAll.isPending}
                                      onClick={() => syncAll.mutate(undefined, { onSuccess: () => toast.success(tt('Updated in every project')), onError: fail })}
                                      iconLeft={<RefreshCw size={11} aria-hidden />}>
                                      {tt('Update')}
                                    </Button>
                                  ) : (
                                    <span className="text-10 font-mono text-tertiary">{tt('Updated automatically')}</span>
                                  )}
                                </span>
                              ) : (
                              <span className="ml-auto flex items-center gap-10">
                                {i.status !== 'fresh' && s && (
                                  <Button variant="link" size="bare" className="text-11 font-mono" disabled={apply.isPending}
                                    onClick={() => apply.mutate({ setId: i.set_id, project: t.project }, { onSuccess: () => toast.success(tt('Updated {name} in {project}', { name, project: t.project })), onError: fail })}
                                    iconLeft={<RefreshCw size={11} aria-hidden />}>
                                    {tt('Update')}
                                  </Button>
                                )}
                                <Button variant="danger-text" size="bare" disabled={remove.isPending || asked}
                                  onClick={() => setRemoving({ setId: i.set_id, project: t.project })}
                                  aria-label={tt('Remove {name} from {project}', { name, project: t.project })}
                                  iconLeft={<X size={11} aria-hidden />}>
                                  {tt('Remove')}
                                </Button>
                              </span>
                              )}
                            </div>
                            {asked && (
                              <Confirm
                                text={tt('Take {name} out of AGENTS.md in {project}.', { name, project: t.project })}
                                action={tt('Remove')}
                                busy={remove.isPending}
                                onYes={() => takeOut(i.set_id, t.project, name)}
                                onNo={() => setRemoving(null)}
                              />
                            )}
                          </div>
                        )
                      })}
                      <div className="pl-[30px] pr-10 pt-6 border-t border-border-subtle">
                        <AddSetMenu sets={sets} written={here.map((i) => i.set_id)}
                          onPick={(setId) => setPending({ setId, project: t.project })} />
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {targets.length > 0 && (
            <p className="px-12 py-6 border-t border-border-subtle text-10 font-mono text-tertiary">
              {t('Drag a set onto a project to write it to AGENTS.md.')}
            </p>
          )}
        </>
      )}
      {pending && (
        <PreviewDialog pending={pending} set={byId.get(pending.setId)} onClose={() => setPending(null)} />
      )}
    </aside>
  )
}
