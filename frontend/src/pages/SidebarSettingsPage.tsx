import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  DndContext, DragOverlay, KeyboardSensor, PointerSensor, closestCorners, useDroppable, useSensor, useSensors,
  type CollisionDetection, type DragEndEvent, type DragOverEvent, type DragStartEvent,
} from '@dnd-kit/core'
import { SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  Check, Eye, EyeOff, GripVertical, PanelLeft, Pencil, Plus, RotateCcw, Trash2, Undo2, X,
} from 'lucide-react'
import { toast } from 'sonner'

import { PageHeader } from '../components/PageHeader'
import { Button, IconButton, Input } from '../components/primitives'
import { CATALOG_BY_KEY, type NavEntry } from '../features/sidebar/catalog'
import {
  HIDDEN_GROUP, addGroup, defaultLayout, groupOf, hideItem, isDefault, moveGroup, moveItem, newGroupId,
  removeGroup, renameGroup, showItem, summary, type Group, type Layout,
} from '../features/sidebar/layout'
import { SidebarNav } from '../features/sidebar/SidebarNav'
import { setLayout, undo, update, useSidebarLayout, useUndoDepth } from '../features/sidebar/store'
import { FIELD, LABEL, PillGroup } from '../features/promptlib/taskstyle'
import { t, tn } from '../i18n/scope/pages'

/**
 * /settings/sidebar — the sidebar, arranged.
 *
 * The groups are cards; the pages are rows inside them. Drag a row to
 * reorder it or carry it to another group, drag a card's handle to reorder
 * the groups, click a name to rename it. The eye on a row puts the page in
 * the hidden tray, where the sidebar shows it folded away at the end. On
 * the right, the sidebar itself, redrawn as the layout changes — expanded
 * or as the rail — so the arrangement is judged where it will live.
 *
 * Every change applies at once and can be undone. Drags are staged in a
 * draft while the pointer moves and land as one change when it lets go.
 */
type ActiveDrag = { type: 'item'; key: string } | { type: 'group'; id: string }

const ITEM = 'i:'
const GROUP = 'g:'
const CONTAINER = 'c:'

const itemId = (key: string) => `${ITEM}${key}`
const groupId = (id: string) => `${GROUP}${id}`
const containerId = (id: string) => `${CONTAINER}${id}`

function parse(id: string | number): { kind: 'item' | 'group' | 'container'; id: string } | null {
  const s = String(id)
  if (s.startsWith(ITEM)) return { kind: 'item', id: s.slice(ITEM.length) }
  if (s.startsWith(GROUP)) return { kind: 'group', id: s.slice(GROUP.length) }
  if (s.startsWith(CONTAINER)) return { kind: 'container', id: s.slice(CONTAINER.length) }
  return null
}

function listOf(l: Layout, container: string): string[] {
  return container === HIDDEN_GROUP ? l.hidden : l.groups.find((g) => g.id === container)?.items ?? []
}

/** Group drags only see groups; page drags only see pages and trays. */
const collide: CollisionDetection = (args) => {
  const kind = parse(args.active.id)?.kind
  const wanted = kind === 'group' ? ['group'] : ['item', 'container']
  return closestCorners({
    ...args,
    droppableContainers: args.droppableContainers.filter((c) => wanted.includes(parse(c.id)?.kind ?? '')),
  })
}

export default function SidebarSettingsPage() {
  useEffect(() => { document.title = `${t('Sidebar')} — Slightly Parallel` }, [])
  const stored = useSidebarLayout()
  const undoDepth = useUndoDepth()
  const [draft, setDraft] = useState<Layout | null>(null)
  const layout = draft ?? stored
  const [active, setActive] = useState<ActiveDrag | null>(null)
  const [q, setQ] = useState('')
  const [preview, setPreview] = useState<'expanded' | 'rail'>('expanded')
  const [renaming, setRenaming] = useState<string | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const needle = q.trim().toLowerCase()
  const matches = useCallback((e: NavEntry) =>
    !needle || e.label.toLowerCase().includes(needle) || e.key.includes(needle) || e.blurb.toLowerCase().includes(needle), [needle])
  const found = useMemo(() => {
    if (!needle) return null
    let n = 0
    for (const e of CATALOG_BY_KEY.values()) if (matches(e)) n++
    return n
  }, [needle, matches])

  const s = summary(layout)

  const onDragStart = (e: DragStartEvent) => {
    const p = parse(e.active.id)
    if (!p || p.kind === 'container') return
    setDraft(stored)
    setActive(p.kind === 'item' ? { type: 'item', key: p.id } : { type: 'group', id: p.id })
  }

  // Pages cross into another group while the pointer moves, so the room
  // opens under them; same-group order is settled on drop.
  const onDragOver = (e: DragOverEvent) => {
    const a = parse(e.active.id)
    const o = e.over ? parse(e.over.id) : null
    if (!a || a.kind !== 'item' || !o) return
    setDraft((d) => {
      const cur = d ?? stored
      const from = groupOf(cur, a.id)
      const to = o.kind === 'container' ? o.id : o.kind === 'item' ? groupOf(cur, o.id) : undefined
      if (!to || to === from) return d
      const idx = o.kind === 'item' ? listOf(cur, to).indexOf(o.id) : undefined
      return moveItem(cur, a.id, to, idx)
    })
  }

  const onDragEnd = (e: DragEndEvent) => {
    const a = parse(e.active.id)
    const o = e.over ? parse(e.over.id) : null
    let next = draft ?? stored
    if (a && o) {
      if (a.kind === 'group' && o.kind === 'group' && a.id !== o.id) {
        next = moveGroup(next, a.id, next.groups.findIndex((g) => g.id === o.id))
      } else if (a.kind === 'item' && o.kind === 'item' && a.id !== o.id) {
        const c = groupOf(next, o.id)
        if (c && c === groupOf(next, a.id)) next = moveItem(next, a.id, c, listOf(next, c).indexOf(o.id))
      }
    }
    setLayout(next)
    setDraft(null)
    setActive(null)
  }

  const onDragCancel = () => { setDraft(null); setActive(null) }

  // Reset is one more change: Undo brings the arrangement back.
  const reset = () => {
    setLayout(defaultLayout())
    toast.success(t('Sidebar reset to the default.'))
  }
  const newGroup = () => {
    const id = newGroupId()
    update((l) => addGroup(l, t('New group'), id))
    setRenaming(id)
  }

  const activeEntry = active?.type === 'item' ? CATALOG_BY_KEY.get(active.key) : undefined
  const activeGroup = active?.type === 'group' ? layout.groups.find((g) => g.id === active.id) : undefined

  return (
    <div className="flex flex-col gap-24">
      <PageHeader
        icon={PanelLeft}
        title={t('Sidebar')}
        tagline={t('Drag pages to reorder them, click a name to rename it, click the eye to hide a page. Changes apply at once.')}
        actions={
          <>
            <Button variant="ghost" size="sm" disabled={undoDepth === 0} onClick={() => undo()} iconLeft={<Undo2 size={13} aria-hidden />}>
              {t('Undo')}{undoDepth > 0 ? ` (${undoDepth})` : ''}
            </Button>
            <Button variant="ghost" size="sm" disabled={isDefault(layout)} onClick={reset} iconLeft={<RotateCcw size={13} aria-hidden />}>
              {t('Reset to default')}
            </Button>
          </>
        }
      />

      <div className="grid gap-24 items-start" style={{ gridTemplateColumns: 'minmax(0, 1fr) 300px' }}>
        <div className="flex flex-col gap-16 min-w-0">
          <div className="flex items-center gap-12 flex-wrap">
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t('Find a page')}
              aria-label={t('Find a page')}
              className="w-[220px] h-24 text-12"
            />
            <span className="text-11 font-mono text-tertiary tabular">
              {found !== null ? `${t('{n} found', { n: found })} · ` : ''}{t('{groups} groups · {shown} shown · {hidden} hidden', { groups: s.groups, shown: s.shown, hidden: s.hidden })}
            </span>
            <Button variant="secondary" size="sm" className="ml-auto" onClick={newGroup} iconLeft={<Plus size={13} aria-hidden />}>
              {t('New group')}
            </Button>
          </div>

          <DndContext
            sensors={sensors}
            collisionDetection={collide}
            onDragStart={onDragStart}
            onDragOver={onDragOver}
            onDragEnd={onDragEnd}
            onDragCancel={onDragCancel}
          >
            <SortableContext items={layout.groups.map((g) => groupId(g.id))} strategy={verticalListSortingStrategy}>
              <ol className="flex flex-col gap-12" aria-label={t('Groups')}>
                {layout.groups.map((g) => (
                  <GroupCard
                    key={g.id}
                    group={g}
                    layout={layout}
                   
                    canRemove={layout.groups.length > 1}
                    renaming={renaming === g.id}
                    onRenaming={(on) => setRenaming(on ? g.id : null)}
                    dim={(e) => !matches(e)}
                  />
                ))}
              </ol>
            </SortableContext>

            <HiddenTray layout={layout} dim={(e) => !matches(e)} />

            <DragOverlay dropAnimation={null}>
              {activeEntry && <ItemGhost entry={activeEntry} />}
              {activeGroup && (
                <div className="rounded-card border border-brand bg-surface px-12 h-32 inline-flex items-center gap-8 text-13 font-medium text-primary shadow-lg">
                  <GripVertical size={14} className="text-tertiary" aria-hidden /> {activeGroup.label}
                  <span className="text-11 font-mono text-tertiary tabular">{activeGroup.items.length}</span>
                </div>
              )}
            </DragOverlay>
          </DndContext>
        </div>

        <Preview layout={layout} mode={preview} onMode={setPreview} />
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- groups */

function GroupCard({
  group, layout, canRemove, renaming, onRenaming, dim,
}: {
  group: Group
  layout: Layout
  canRemove: boolean
  renaming: boolean
  onRenaming: (on: boolean) => void
  dim: (e: NavEntry) => boolean
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: groupId(group.id), data: { type: 'group' },
  })
  const { setNodeRef: setDropRef, isOver } = useDroppable({ id: containerId(group.id), data: { type: 'container' } })
  const entries = group.items.map((k) => CATALOG_BY_KEY.get(k)).filter((e): e is NavEntry => !!e)
  const folded = layout.folded.includes(group.id)

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`rounded-card border bg-surface flex flex-col ${isDragging ? 'opacity-40 border-brand' : 'border-border-subtle'}`}
    >
      <div className="flex items-center gap-8 px-8 h-48 border-b border-border-subtle">
        <button
          ref={setActivatorNodeRef}
          type="button"
          {...attributes}
          {...listeners}
          aria-label={t('Move group {name}', { name: group.label })}
          title={t('Drag to reorder the groups')}
          className="inline-flex items-center justify-center w-24 h-24 rounded-input text-tertiary hover:text-primary hover:bg-hover cursor-grab active:cursor-grabbing touch-none"
        >
          <GripVertical size={14} aria-hidden />
        </button>
        <GroupName group={group} editing={renaming} onEditing={onRenaming} />
        <span className="text-11 font-mono text-tertiary tabular">
          {tn(entries.length, '{n} page', '{n} pages')}{folded ? ` · ${t('folded')}` : ''}
        </span>
        <div className="ml-auto flex items-center gap-4">
          <IconButton
            label={t('Hide every page in {name}', { name: group.label })}
            disabled={entries.length === 0}
            onClick={() => update((l) => group.items.reduce((acc, k) => hideItem(acc, k), l))}
          >
            <EyeOff size={13} aria-hidden />
          </IconButton>
          <IconButton
            label={canRemove ? t('Remove group {name}', { name: group.label }) : t('The last group stays')}
            disabled={!canRemove}
            onClick={() => update((l) => removeGroup(l, group.id))}
            danger
          >
            <Trash2 size={13} aria-hidden />
          </IconButton>
        </div>
      </div>

      <SortableContext items={group.items.map(itemId)} strategy={verticalListSortingStrategy}>
        <ol
          ref={setDropRef}
          aria-label={t('Pages in {name}', { name: group.label })}
          className={`flex flex-col p-4 min-h-[44px] rounded-b-card transition-colors duration-fast ${isOver ? 'bg-brand-glow' : ''}`}
        >
          {entries.map((e) => (
            <ItemRow key={e.key} entry={e} layout={layout} container={group.id} dim={dim(e)} />
          ))}
          {entries.length === 0 && (
            <li className="h-32 mx-4 my-2 rounded-input border border-dashed border-border-default flex items-center justify-center text-11 text-tertiary">
              drop pages here
            </li>
          )}
        </ol>
      </SortableContext>
    </li>
  )
}

function GroupName({ group, editing, onEditing }: { group: Group; editing: boolean; onEditing: (on: boolean) => void }) {
  const [value, setValue] = useState(group.label)
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { if (editing) { setValue(group.label); ref.current?.select() } }, [editing, group.label])
  const commit = () => { update((l) => renameGroup(l, group.id, value)); onEditing(false) }
  if (editing) {
    return (
      <form
        className="flex items-center gap-4"
        onSubmit={(e) => { e.preventDefault(); commit() }}
        // Focus leaving the whole form commits; moving to the form's own
        // buttons does not, so Cancel still cancels by mouse or by Tab.
        onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) commit() }}
      >
        <Input
          ref={ref}
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); onEditing(false) } }}
          aria-label={t('Group name')}
          maxLength={32}
          className="h-24 w-[180px] text-13 font-medium"
        />
        <IconButton label={t('Save name')} onClick={commit} onMouseDown={(e) => e.preventDefault()}><Check size={13} aria-hidden /></IconButton>
        <IconButton label={t('Cancel')} onClick={() => onEditing(false)} onMouseDown={(e) => e.preventDefault()}><X size={13} aria-hidden /></IconButton>
      </form>
    )
  }
  return (
    <button
      type="button"
      onClick={() => onEditing(true)}
      title={t('Rename')}
      className="group/name inline-flex items-center gap-6 h-24 px-4 rounded-input text-13 font-medium text-primary hover:bg-hover"
    >
      {group.label}
      <Pencil size={11} aria-hidden className="text-tertiary opacity-0 group-hover/name:opacity-100 transition-opacity duration-fast" />
    </button>
  )
}

/* ----------------------------------------------------------------- pages */

function ItemRow({
  entry, layout, container, dim,
}: {
  entry: NavEntry
  layout: Layout
  container: string
  dim: boolean
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: itemId(entry.key), data: { type: 'item' },
  })
  const Icon = entry.icon
  const inHidden = container === HIDDEN_GROUP
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`group/row flex items-center gap-8 h-32 px-4 rounded-input transition-colors duration-fast ease-out
        ${isDragging ? 'opacity-30' : 'hover:bg-hover'} ${dim ? 'opacity-30' : ''}`}
    >
      <button
        ref={setActivatorNodeRef}
        type="button"
        {...attributes}
        {...listeners}
        aria-label={t('Move {name}', { name: entry.label })}
        title={t('Drag to reorder or move to another group')}
        className="inline-flex items-center justify-center w-24 h-24 rounded-input text-tertiary hover:text-primary cursor-grab active:cursor-grabbing touch-none shrink-0"
      >
        <GripVertical size={14} aria-hidden />
      </button>
      <Icon size={15} aria-hidden className={`shrink-0 ${inHidden ? 'text-tertiary' : 'text-secondary'}`} />
      <span className={`text-13 ${inHidden ? 'text-secondary' : 'text-primary'} shrink-0`}>{entry.label}</span>
      <span className="text-11 font-mono text-tertiary truncate">{entry.key}</span>
      <span className="text-11 text-tertiary truncate hidden lg:inline">{entry.blurb}</span>
      <div className="ml-auto flex items-center gap-4 shrink-0">
        <MoveTo entry={entry} layout={layout} current={container} />
        {inHidden ? (
          <IconButton label={t('Show {name}', { name: entry.label })} onClick={() => update((l) => showItem(l, entry.key))}>
            <Eye size={13} aria-hidden />
          </IconButton>
        ) : (
          <IconButton label={t('Hide {name}', { name: entry.label })} onClick={() => update((l) => hideItem(l, entry.key))}>
            <EyeOff size={13} aria-hidden />
          </IconButton>
        )}
      </div>
    </li>
  )
}

/** The keyboard's way across groups — a select that moves on choice. */
function MoveTo({ entry, layout, current }: { entry: NavEntry; layout: Layout; current: string }) {
  return (
    <select
      value=""
      onChange={(e) => { const to = e.currentTarget.value; if (to) update((l) => moveItem(l, entry.key, to)) }}
      aria-label={t('Move {name} to a group', { name: entry.label })}
      title={t('Move to…')}
      className={`${FIELD} h-24 py-0 max-w-[96px] text-11 text-tertiary opacity-0 group-hover/row:opacity-100 focus:opacity-100 transition-opacity duration-fast`}
    >
      <option value="">{t('move to…')}</option>
      {layout.groups.filter((g) => g.id !== current).map((g) => (
        <option key={g.id} value={g.id}>{g.label}</option>
      ))}
      {current !== HIDDEN_GROUP && <option value={HIDDEN_GROUP}>{t('Hidden')}</option>}
    </select>
  )
}

function ItemGhost({ entry }: { entry: NavEntry }) {
  const Icon = entry.icon
  return (
    <div className="rounded-input border border-brand bg-surface px-8 h-32 inline-flex items-center gap-8 text-13 text-primary shadow-lg">
      <GripVertical size={14} className="text-tertiary" aria-hidden />
      <Icon size={15} aria-hidden className="text-secondary" />
      {entry.label}
    </div>
  )
}

/* ---------------------------------------------------------------- hidden */

function HiddenTray({ layout, dim }: { layout: Layout; dim: (e: NavEntry) => boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: containerId(HIDDEN_GROUP), data: { type: 'container' } })
  const entries = layout.hidden.map((k) => CATALOG_BY_KEY.get(k)).filter((e): e is NavEntry => !!e)
  return (
    <section className={`rounded-card border border-dashed flex flex-col ${isOver ? 'border-brand bg-brand-glow' : 'border-border-default'}`}>
      <div className="flex items-center gap-8 px-12 h-48">
        <EyeOff size={14} className="text-tertiary" aria-hidden />
        <span className="text-13 font-medium text-primary">{t('Hidden')}</span>
        <span className="text-11 text-tertiary">
          {t('Hidden pages appear as a folded group at the end of the sidebar.')}
        </span>
        <span className="ml-auto text-11 font-mono text-tertiary tabular">{entries.length}</span>
      </div>
      <SortableContext items={layout.hidden.map(itemId)} strategy={verticalListSortingStrategy}>
        <ol ref={setNodeRef} aria-label={t('Hidden pages')} className="flex flex-col p-4 min-h-[44px]">
          {entries.map((e) => (
            <ItemRow key={e.key} entry={e} layout={layout} container={HIDDEN_GROUP} dim={dim(e)} />
          ))}
          {entries.length === 0 && (
            <li className="h-32 mx-4 my-2 flex items-center justify-center text-11 text-tertiary">
              {t('No hidden pages. Click the eye on a row, or drop a page here, to hide it.')}
            </li>
          )}
        </ol>
      </SortableContext>
    </section>
  )
}

/* --------------------------------------------------------------- preview */

function Preview({
  layout, mode, onMode,
}: {
  layout: Layout
  mode: 'expanded' | 'rail'
  onMode: (m: 'expanded' | 'rail') => void
}) {
  const rail = mode === 'rail'
  return (
    <aside className="flex flex-col gap-12 sticky top-0">
      <div className="flex items-center justify-between gap-8">
        <span className={LABEL}>{t('preview')}</span>
        <PillGroup label="" value={mode} onChange={(v) => onMode(v as 'expanded' | 'rail')} options={[['expanded', t('expanded')], ['rail', t('rail')]]} />
      </div>
      <div
        className="rounded-card border border-border-subtle bg-surface overflow-hidden transition-[width] duration-fast ease-out"
        style={{ width: rail ? 56 : 240 }}
      >
        <div className={`h-topbar flex items-center gap-8 border-b border-border-subtle ${rail ? 'justify-center' : 'px-16'}`}>
          <span aria-hidden className="inline-block w-16 h-16 rounded-input" style={{ background: 'var(--brand)' }} />
          {!rail && <span className="font-semibold tracking-tight text-13">Slightly Parallel</span>}
        </div>
        <div className="max-h-[70vh] overflow-y-auto">
          <SidebarNav collapsed={rail} inert layout={layout} />
        </div>
      </div>
      <p className="text-11 text-tertiary leading-relaxed">
        {t("Folds are remembered as well: click a group's name in the real sidebar to fold it shut, and the rail shows a folded group as one chevron.")}
      </p>
    </aside>
  )
}

/* ------------------------------------------------------------------ bits */
