import { Suspense, lazy } from 'react'
import { Drawer } from './features/terminal/Dock'
import { useDockShortcut } from './lib/terminal'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ErrorBoundary, PanelBoundary } from './components/ErrorBoundary'
import { LoadingSkeleton } from './components/states'
import { useFreshness } from './lib/settings'
import { WaitingNotice } from './features/terminal/waiting'
import { SmartTimer } from './features/time/SmartTimer'
import { useApplyAppearance } from './lib/appearance'
import { useSidebarCollapsed } from './hooks/useSidebarCollapsed'
import { Sidebar } from './features/shell/Sidebar'
import { Topbar } from './features/shell/Topbar'

// The tour player loads only when the address asks for a tour (?tour=).
const LiveTour = lazy(() => import('./features/tour/LiveTour').then((m) => ({ default: m.LiveTour })))

const Overview = lazy(() => import('./pages/Overview'))
const ProjectPage = lazy(() => import('./pages/Project'))
const AgentPage = lazy(() =>
  import('./pages/AgentPage').then((m) => ({ default: m.AgentPage })),
)
const AgentsIndexPage = lazy(() => import('./pages/AgentsIndexPage'))
const SearchPage = lazy(() => import('./pages/Search'))
const GuidePage = lazy(() => import('./pages/GuidePage'))
const AboutPage = lazy(() => import('./pages/AboutPage'))
const InternalsPage = lazy(() => import('./pages/InternalsPage'))
const HealthPage = lazy(() => import('./pages/HealthPage'))
const ImportantPage = lazy(() => import('./pages/ImportantPage'))
const MonitorPage = lazy(() => import('./pages/MonitorPage'))
const TerminalPageRoute = lazy(() => import('./pages/TerminalPage'))
const StatsPage = lazy(() => import('./pages/StatsPage'))
const TimePage = lazy(() => import('./pages/TimePage'))
const PromptLibraryPage = lazy(() => import('./pages/PromptLibraryPage'))
const PromptPage = lazy(() => import('./pages/PromptPage'))
const SessionsPage = lazy(() => import('./pages/SessionsPage'))
const BackupsPage = lazy(() => import('./pages/BackupsPage'))
const KanbanPage = lazy(() => import('./pages/KanbanPage'))
const SetupPage = lazy(() => import('./pages/SetupPage'))
const SidebarSettingsPage = lazy(() => import('./pages/SidebarSettingsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const AppearancePage = lazy(() => import('./pages/AppearancePage'))
const SprintsPage = lazy(() => import('./pages/SprintsPage'))
const FilesPage = lazy(() => import('./pages/FilesPage'))
const ArchitecturePage = lazy(() => import('./pages/ArchitecturePage'))

const TourPage = lazy(() => import('./pages/TourPage'))
const TourCustomPage = lazy(() => import('./pages/TourCustomPage'))
const TimelapsePage = lazy(() => import('./pages/TimelapsePage'))
const AgentPromptsPage = lazy(() => import('./pages/AgentPromptsPage'))
const CalendarPage = lazy(() => import('./pages/CalendarPage'))
const VisionsPage = lazy(() => import('./pages/VisionsPage'))
const RulesPage = lazy(() => import('./pages/RulesPage'))
const ProblemsPage = lazy(() => import('./pages/ProblemsPage'))
const SkillsPage = lazy(() => import('./pages/SkillsPage'))
const ArtifactsPage = lazy(() => import('./pages/ArtifactsPage'))
const ScansPage = lazy(() => import('./pages/ScansPage'))
const StandupsPage = lazy(() => import('./pages/StandupsPage'))
const DecisionsPage = lazy(() => import('./pages/DecisionsPage'))
const NotFoundPage = lazy(() =>
  import('./pages/NotFoundPage').then((m) => ({ default: m.NotFoundPage })),
)

/**
 * App — the root shell.
 *
 *   ┌────────────┬──────────────────────────────────────────────┐
 *   │  Sidebar   │  Topbar (48px)                               │
 *   │  (240px,   ├──────────────────────────────────────────────┤
 *   │   or 56px  │                                              │
 *   │   as icons)│                                              │
 *   │            │                                              │
 *   │  brand     │            main content (max-w 1200)         │
 *   │  nav       │                                              │
 *   │  projects  │                                              │
 *   └────────────┴──────────────────────────────────────────────┘
 *
 * Routes:
 *   /               Overview
 *   /project/:code  Per-project drill
 *   /agent/:id      Agent detail
 *   /<lens>         One route per registered lens (see lenses/config)
 *   /kanban /sprints /files /search /guide /internals /setup /settings
 */
/** The freshness poll in a leaf of its own: a moving stamp must not re-render the app shell. */
function Freshness() {
  useFreshness(5_000)
  return null
}

export function App() {
  const appLocation = useLocation()
  // Skin, accent and interface scale — the operator's appearance choices.
  useApplyAppearance()
  const [collapsed, toggleSidebar] = useSidebarCollapsed()
  useDockShortcut()
  return (
    // `h-screen` and not `min-h-screen`: with a minimum, a long page makes
    // the whole row taller than the window, the sidebar grows with it, and
    // the projects at its foot can only be reached by scrolling the page —
    // which takes the board with it. Fixed height gives the nav and the
    // content a scroller each, which is what every one of them already
    // declared it wanted.
    <div className="h-screen overflow-hidden flex bg-base text-primary">
      {/* Only when the URL carries ?tour= — it walks across routes, so it
          has to live above them; without one, none of its code loads. */}
      {new URLSearchParams(appLocation.search).has('tour') && (
        <Suspense fallback={null}><LiveTour /></Suspense>
      )}
      {/* Outside the page's guard: a crash here would blank the whole app. */}
      <Freshness />
      {/* An agent that turns to you: the tab title, a live region, and — if
          you switched it on — a desktop notification. */}
      <WaitingNotice />
      {/* The smart timer: beats while you work, away notices, the reminder. */}
      <SmartTimer />
      <PanelBoundary name="Sidebar" quiet>
        <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
      </PanelBoundary>
      <div className="flex-1 min-w-0 flex flex-col">
        <PanelBoundary name="Top bar" quiet><Topbar /></PanelBoundary>
        <main id="main" role="main" className="flex-1 min-w-0 min-h-0 overflow-auto">
          {/* Collapsing the sidebar is a request for room: the reading cap
              goes with it, so tables and boards take the width they were
              given instead of re-centring inside the same 1200px. */}
          <div className={`${collapsed ? 'max-w-none' : 'max-w-content'} mx-auto px-24 py-24`}>
            <Suspense fallback={<LoadingSkeleton variant="card" count={3} />}>
              <ErrorBoundary resetKey={appLocation.pathname}>
              <Routes>
                {/* ------------------------------- the product ---------- */}
                <Route path="/" element={<Overview />} />
                <Route path="/project/:code" element={<ProjectPage />} />
                <Route path="/agent" element={<AgentsIndexPage />} />
                <Route path="/agent/:id" element={<AgentPage />} />
                <Route path="/architecture" element={<ArchitecturePage />} />
                <Route path="/tour" element={<TourPage />} />
                {/* The studio that writes tours; /tour is the list of them. */}
                <Route path="/tour/custom" element={<TourCustomPage />} />
                {/* The timelapse studio: the project's history as a film. */}
                <Route path="/timelapse" element={<TimelapsePage />} />
                {/* Chats are read, not scanned: the workbench, not the lens list.
                    The page is /chats since 2026-09-24; /sessions is the address
                    it was published at and keeps answering. */}
                <Route path="/chats" element={<SessionsPage />} />
                <Route path="/sessions" element={<SessionsPage />} />
                <Route path="/calendar" element={<CalendarPage />} />
                <Route path="/visions" element={<VisionsPage />} />
                <Route path="/problems" element={<ProblemsPage />} />
                <Route path="/rules" element={<RulesPage />} />
                <Route path="/skills" element={<SkillsPage />} />
                <Route path="/artifacts" element={<ArtifactsPage />} />
                <Route path="/scans" element={<ScansPage />} />
                <Route path="/standups" element={<StandupsPage />} />
                <Route path="/decisions" element={<DecisionsPage />} />
                <Route path="/kanban" element={<KanbanPage />} />
                <Route path="/sprints" element={<SprintsPage />} />
                <Route path="/files" element={<FilesPage />} />
                <Route path="/guide" element={<GuidePage />} />
                <Route path="/about" element={<AboutPage />} />
                <Route path="/prompts" element={<PromptLibraryPage />} />
                <Route path="/prompts/:id" element={<PromptPage />} />
                <Route path="/internals" element={<InternalsPage />} />
                <Route path="/health" element={<HealthPage />} />
                <Route path="/important" element={<ImportantPage />} />
                <Route path="/monitor" element={<MonitorPage />} />
                <Route path="/terminal" element={<TerminalPageRoute />} />
                <Route path="/stats" element={<StatsPage />} />
                <Route path="/time" element={<TimePage />} />
                <Route path="/backups" element={<BackupsPage />} />
                <Route path="/setup" element={<SetupPage />} />
                <Route path="/settings" element={<SettingsPage />} />
                <Route path="/settings/prompts" element={<AgentPromptsPage />} />
                <Route path="/settings/appearance" element={<AppearancePage />} />
                <Route path="/settings/sidebar" element={<SidebarSettingsPage />} />
                <Route path="/search" element={<SearchPage />} />
                {/* Pre-redesign bookmarks: Activity became Chats. */}
                <Route path="/activity" element={<Navigate to="/chats" replace />} />

                <Route path="*" element={<NotFoundPage />} />
              </Routes>
              </ErrorBoundary>
            </Suspense>
          </div>
        </main>
        {/* The terminal drawer: on every page, under it (` shows it). */}
        <PanelBoundary name="Terminal" quiet><Drawer /></PanelBoundary>
      </div>
    </div>
  )
}
