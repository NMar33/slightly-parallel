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
}: {
  tabs: readonly TabDef<Id>[]
  active: Id
  onSelect: (id: Id) => void
  ariaLabel: string
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="flex gap-4 border-b border-border-default"
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
              'px-16 py-8 text-13 font-medium transition-colors duration-fast ease-out relative',
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
  )
}
