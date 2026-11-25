/*
 * What the Setup page reads and writes: the server's setup facts
 * (/api/setup/info) and the integration of a project folder.
 */
import { useQuery } from '@tanstack/react-query'

import { getJson, postJson } from '../../lib/getJson'
import type { ExampleState } from '../example/example'

/** The tools Setup can wire a project to. */
export type ToolKey = 'claude' | 'codex' | 'opencode' | 'cursor'
export const TOOL_KEYS: ToolKey[] = ['claude', 'codex', 'opencode', 'cursor']
export const TOOL_NAMES: Record<ToolKey, string> = { claude: 'Claude Code', codex: 'Codex', opencode: 'OpenCode', cursor: 'Cursor' }

export interface ComputerState {
  autostart: { on: boolean; paths: string[] }
  shortcut: { on: boolean; paths: string[] }
  system: 'linux' | 'mac' | 'windows'
  /** A test server: it does not change this computer. */
  sandbox: boolean
}

/** An agent whose chat folder a project holds while it is a member of other projects. */
export interface HeldChat {
  agent_id: string
  also_in: string[]
}

export interface SetupInfo {
  app_root: string
  contract_path: string
  contract_exists: boolean
  data_root: string
  /** The example project (backend/example.py): on, there, being played. */
  example: ExampleState
  api_url: string
  integrations: Integration[]
  /** Every project Slightly Parallel holds data for, registered or not. */
  data_projects: Array<{
    code: string
    chats: number
    rows: number
    /** The agents whose chat holds the project back from a delete: each is a
     *  member elsewhere, and its chat can move to one of `also_in`. */
    held?: HeldChat[]
  }>
  codex: { state: 'installed' | 'foreign' | 'absent'; config: string }
  /** Which tools this computer has (the command, or its settings folder). */
  tools_installed?: Record<ToolKey, boolean>
  /** Start at login and the shortcut (backend/autostart.py). */
  computer?: ComputerState
  adapters: {
    claude_verified: boolean
    opencode_verified: boolean
    codex_verified: boolean
    cursor_verified: boolean
  }
}

export interface Integration {
  project: string
  path: string
  created_date: string
  status: 'fresh' | 'stale' | 'missing'
  hooks: boolean
  /** Which tools record their chats in this project. */
  tools?: Record<ToolKey, boolean>
  /** Sessions of the last week a tool ran here and nothing recorded. */
  lost?: Partial<Record<ToolKey, number>>
  /** Sessions nothing recorded that can be imported from the tool's own log. */
  importable?: Partial<Record<ToolKey, number>>
  /** Tools the operator said need no recording here. */
  ignored?: ToolKey[]
  git: boolean
}

export interface IntegrateResult {
  dry_run: boolean
  project_code: string
  project_dir: string
  results: Array<{ file: string; action: string; content: string }>
}

export const SETUP_INFO_KEY = ['setup', 'info'] as const

/** The operator says a tool needs no recording in a project (or takes it back). */
export const postIgnore = (project: string, tool: ToolKey, ignored = true) =>
  postJson<{ ignored: string[] }>('/api/capture/ignore', { project, tool, ignored })

export function useSetupInfo() {
  return useQuery({
    queryKey: SETUP_INFO_KEY,
    queryFn: ({ signal }) => getJson<SetupInfo>('/api/setup/info', signal),
  })
}

export const postIntegrate = (body: Record<string, unknown>) =>
  postJson<IntegrateResult>('/api/setup/integrate', body)
