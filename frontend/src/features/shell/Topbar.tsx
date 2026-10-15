import { useMemo } from 'react'
import { TerminalButton } from '../terminal/Dock'
import { CaptureAlert } from '../capture/CaptureHealth'
import { TopbarMonitor } from '../monitor/TopbarMonitor'
import { TopbarTimer } from '../time/TopbarTimer'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { ChevronRight, Monitor, Moon, Search as SearchIcon, Sun } from 'lucide-react'
import { Button, Input, Row } from '../../components/primitives'
import { PanelBoundary } from '../../components/ErrorBoundary'
import { QuickNote } from '../note/QuickNote'
import { crumbsOf } from './crumbs'
import { useTheme } from '../../providers/ThemeProvider'
import { t } from '../../i18n/scope/shell'

/* ---------------------------------------------------------------------------
 * Topbar
 * ------------------------------------------------------------------------- */

export function Topbar() {
  return (
    <header
      className="h-topbar min-h-topbar border-b border-border-subtle bg-base flex items-center gap-16 px-24"
      role="banner"
    >
      <Breadcrumbs />
      <div className="ml-auto flex items-center gap-8">
        <PanelBoundary name="Capture" quiet><CaptureAlert /></PanelBoundary>
        <PanelBoundary name="Timer" quiet><TopbarTimer /></PanelBoundary>
        <PanelBoundary name="Monitor" quiet><TopbarMonitor /></PanelBoundary>
        <PanelBoundary name="Terminal button" quiet><TerminalButton /></PanelBoundary>
        <TopbarSearch />
        <QuickNote />
        <ThemeToggle />
      </div>
    </header>
  )
}

/**
 * Breadcrumbs — inferred from the route path (features/shell/crumbs).
 * Route params (:code / :id) render verbatim; lens segments render their
 * configured title; a prefix with no page of its own is not a link.
 */
function Breadcrumbs() {
  const location = useLocation()
  const crumbs = useMemo(() => crumbsOf(location.pathname), [location.pathname])

  return (
    <Row gap="8" align="center" className="min-w-0">
      {crumbs.map((c, i) => (
        <div key={`${i}:${c.to ?? c.label}`} className="flex items-center gap-8 min-w-0">
          {i > 0 && (
            <ChevronRight
              size={14}
              className="text-tertiary shrink-0"
              aria-hidden="true"
            />
          )}
          {c.to === null ? (
            <span className="text-13 truncate text-secondary">{c.label}</span>
          ) : (
          <NavLink
            to={c.to}
            end={i === crumbs.length - 1}
            className={({ isActive }) =>
              `text-13 truncate transition-colors duration-fast ease-out
               ${isActive || i === crumbs.length - 1 ? 'text-primary font-medium' : 'text-secondary hover:text-primary'}`
            }
          >
            {c.label}
          </NavLink>
          )}
        </div>
      ))}
    </Row>
  )
}

/** Topbar search — submits to /search?q=… via the router. */
function TopbarSearch() {
  const navigate = useNavigate()
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault()
        const fd = new FormData(e.currentTarget)
        const q = String(fd.get('q') ?? '').trim()
        navigate(q ? `/search?q=${encodeURIComponent(q)}` : '/search')
      }}
      // Narrower below a wide window: the timer and the monitor sit beside it,
      // and the breadcrumbs must stay readable.
      className="w-[220px] 2xl:w-[320px] max-w-[40vw]"
    >
      <Input
        type="search"
        name="q"
        placeholder={t('Search everything…')}
        aria-label={t('Search')}
        icon={<SearchIcon size={14} />}
        shortcut="⌘/"
        bindShortcut
        // Escape leaves the field; page keys (the search page's own) skip a focused field.
        onKeyDown={(e) => { if (e.key === 'Escape') e.currentTarget.blur() }}
      />
    </form>
  )
}

function ThemeToggle() {
  const { theme, mode, setMode } = useTheme()

  // Cycle: system → light → dark → system.
  const nextMode = mode === 'system' ? 'light' : mode === 'light' ? 'dark' : 'system'
  const label =
    mode === 'system' ? t('System ({theme})', { theme: theme === 'dark' ? t('dark') : t('light') }) : mode === 'light' ? t('Light') : t('Dark')
  const Icon = mode === 'system' ? Monitor : mode === 'light' ? Sun : Moon

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setMode(nextMode)}
      aria-label={t('Theme: {label}. Click to switch.', { label })}
      title={t('Theme: {label}', { label })}
      iconLeft={<Icon size={14} aria-hidden="true" />}
    >
      <span className="sr-only">{label}</span>
    </Button>
  )
}
