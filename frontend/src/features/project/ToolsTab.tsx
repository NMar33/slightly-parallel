import { TimeTracker } from './TimeTracker'

/**
 * ToolsTab — the project's Timer tab: its time tracker, at the page's
 * full width. (The tab was called Tools; the file and the tab id keep
 * the name, since links and the saved default tab hold it.)
 */
export function ToolsTab({ projectCode }: { projectCode: string }) {
  return <TimeTracker projectCode={projectCode} />
}
