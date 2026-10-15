import { NavLink } from 'react-router-dom'
import { ChevronDown, EyeOff, Settings2 } from 'lucide-react'

import { CATALOG_BY_KEY, type NavEntry } from './catalog'
import { HIDDEN_GROUP, toggleFold, type Layout } from './layout'
import { update, useSidebarLayout } from './store'
import { t, tn } from '../../i18n/scope/shell'

/**
 * SidebarNav — the pages, from the layout. Used twice: live in the app's
 * sidebar, and inert as the preview on the settings page (`inert` makes it
 * a picture: no navigation, no folding, hidden from assistive tech).
 *
 * Groups fold on their label and stay folded across visits. Hidden pages
 * are one more group at the end, "Hidden", folded by default — the
 * operator put them away, so the sidebar keeps them out of the way, but
 * a click still reaches them.
 */
interface Section {
  id: string
  label: string
  entries: NavEntry[]
  hidden: boolean
}

function sectionsOf(layout: Layout): Section[] {
  const visible = (keys: string[]) =>
    keys.map((k) => CATALOG_BY_KEY.get(k)).filter((e): e is NavEntry => !!e)
  const out: Section[] = layout.groups.map((g) => ({ id: g.id, label: t(g.label), entries: visible(g.items), hidden: false }))
  if (layout.hidden.length) out.push({ id: HIDDEN_GROUP, label: t('Hidden'), entries: visible(layout.hidden), hidden: true })
  return out.filter((s) => s.entries.length > 0)
}

export function SidebarNav({
  collapsed, layout: given, inert,
}: {
  collapsed: boolean
  layout?: Layout
  inert?: boolean
}) {
  const live = useSidebarLayout()
  const layout = given ?? live
  const fold = (id: string) => { if (!inert) update((l) => toggleFold(l, id), { history: false }) }
  const sections = sectionsOf(layout)

  return (
    <nav
      aria-label={t('Views')}
      aria-hidden={inert || undefined}
      className={`group/nav p-8 flex flex-col ${collapsed ? 'gap-4' : 'gap-8'} ${inert ? 'pointer-events-none select-none' : ''}`}
    >
      {sections.map((s, si) => {
        const folded = layout.folded.includes(s.id)
        const FoldIcon = s.hidden ? EyeOff : ChevronDown
        return (
          <div key={s.id} className="flex flex-col gap-4">
            {collapsed ? (
              <>
                {si > 0 && <div aria-hidden className="mx-8 my-4 border-t border-border-subtle" />}
                {folded && (
                  <button
                    type="button"
                    onClick={() => fold(s.id)}
                    title={`${s.label} · ${tn(s.entries.length, '{n} hidden', '{n} hidden')}`}
                    aria-label={t('Expand {group}', { group: s.label })}
                    className="w-32 h-24 mx-auto inline-flex items-center justify-center rounded-input text-tertiary hover:text-primary hover:bg-hover"
                  >
                    <FoldIcon size={14} aria-hidden />
                  </button>
                )}
              </>
            ) : (
              <button
                type="button"
                onClick={() => fold(s.id)}
                aria-expanded={!folded}
                className="group/label px-8 pt-8 pb-4 text-11 uppercase tracking-wider text-tertiary font-medium flex items-center justify-between w-full rounded-input hover:text-secondary"
              >
                <span className="inline-flex items-center gap-6 truncate">
                  {s.hidden && <EyeOff size={11} aria-hidden />}
                  {s.label}
                </span>
                <span className="inline-flex items-center gap-4 font-mono normal-case tracking-normal shrink-0">
                  {folded && <span className="tabular">{s.entries.length}</span>}
                  <ChevronDown
                    size={12}
                    aria-hidden
                    className={`transition-transform duration-fast ease-out opacity-50 group-hover/label:opacity-100 ${folded ? '-rotate-90' : ''}`}
                  />
                </span>
              </button>
            )}
            {!folded && s.entries.map((e) => (
              <SidebarLink key={e.key} entry={e} collapsed={collapsed} muted={s.hidden} />
            ))}
          </div>
        )
      })}
      {!collapsed && !inert && (
        <NavLink
          to="/settings/sidebar"
          className={({ isActive }) =>
            `mt-4 flex items-center gap-8 h-24 px-8 rounded-input text-11 transition-opacity duration-fast ease-out focus-visible:opacity-100
             ${isActive ? 'text-primary opacity-100' : 'text-tertiary hover:text-secondary hover:bg-hover opacity-0 group-hover/nav:opacity-100'}`
          }
        >
          <Settings2 size={12} aria-hidden /> {t('Customise sidebar')}
        </NavLink>
      )}
    </nav>
  )
}

function SidebarLink({ entry, collapsed, muted }: { entry: NavEntry; collapsed: boolean; muted: boolean }) {
  const Icon = entry.icon
  const rest = muted ? 'text-tertiary hover:bg-hover hover:text-primary' : 'text-secondary hover:bg-hover hover:text-primary'
  return (
    <NavLink
      to={entry.to ?? entry.key}
      end={entry.end}
      title={collapsed ? entry.label : undefined}
      aria-label={collapsed ? entry.label : undefined}
      className={({ isActive }) =>
        `flex items-center h-32 rounded-input text-13 transition-colors duration-fast ease-out
         ${collapsed ? 'justify-center w-32 mx-auto' : 'gap-8 px-8'}
         ${isActive ? 'bg-hover text-primary' : rest}`
      }
    >
      <Icon size={16} aria-hidden="true" className="shrink-0" />
      {!collapsed && <span className="truncate">{entry.label}</span>}
    </NavLink>
  )
}
