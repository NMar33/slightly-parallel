import { ReactNode } from 'react'

interface TabDef<Id extends string = string> {
  id: Id
  label: ReactNode
}

/**
 * Accessible tab strip: role=tablist, arrow-key navigation, roving tabindex.
 *
 * The active panel the tabs control must render with
 * `id={`tabpanel-${activeId}`}` — `aria-controls` points there.
 */
export function TabBar<Id extends string>({
  tabs,
  active,
  onSelect,
  ariaLabel,
  after,
}: {
  tabs: readonly TabDef<Id>[]
  active: Id
  onSelect: (id: Id) => void
  ariaLabel: string
  /** At the right end of the strip, outside the tab list (a page's tab settings). */
  after?: ReactNode
}) {
  return (
    <div className="flex items-end gap-8 border-b border-border-default">
      <div
        role="tablist"
        aria-label={ariaLabel}
        // Many tabs (a project page with every tab on) wrap to a second row:
        // all of them stay in sight, none behind a scroll.
        className="flex flex-wrap gap-x-4 flex-1 min-w-0"
      >
        {tabs.map((t) => {
          const isActive = t.id === active
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={isActive}
              aria-controls={isActive ? `tabpanel-${t.id}` : undefined}
              id={`tab-${t.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => onSelect(t.id)}
              onKeyDown={(e) => {
                if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                  e.preventDefault()
                  const i = tabs.findIndex((x) => x.id === active)
                  const nextIdx =
                    e.key === 'ArrowRight'
                      ? (i + 1) % tabs.length
                      : (i - 1 + tabs.length) % tabs.length
                  const next = tabs[nextIdx]
                  if (!next) return
                  onSelect(next.id)
                  document.getElementById(`tab-${next.id}`)?.focus()
                }
              }}
              className={[
                'px-16 py-8 text-13 font-medium whitespace-nowrap transition-colors duration-fast ease-out relative',
                isActive ? 'text-primary' : 'text-tertiary hover:text-secondary',
              ].join(' ')}
            >
              {t.label}
              {isActive && (
                <span
                  aria-hidden
                  className="absolute left-0 right-0 -bottom-px h-[2px] bg-brand"
                />
              )}
            </button>
          )
        })}
      </div>
      {after && <div className="shrink-0 pb-4">{after}</div>}
    </div>
  )
}
