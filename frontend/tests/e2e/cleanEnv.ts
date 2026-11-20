/**
 * The Playwright suites (this one and desktop/e2e) start a server of their
 * own and spread process.env into it, and their windows and workers inherit
 * it too. A shell inside Slightly Parallel's own terminal, or an agent's,
 * carries variables that change what that server does: SP_ENABLE_TERMINAL,
 * SP_TERMINAL, SP_UI_DEV (every page redirected to the operator's Vite),
 * SP_LOG_DIR (the log into the operator's folder), SP_API, the data root
 * under its former names, the agent's session. CI has none of them, so a
 * laptop run tested something else.
 *
 * Both configs call cleanEnv() first: every SP_* variable goes except the
 * suites' own knobs, and so do the other names the backend reads from a
 * developer's shell (backend/tests/conftest.py clears the same for pytest).
 */

/** The suites' own knobs: how a run is made, never what the product does. */
const KNOB_PREFIXES = ['SP_E2E_', 'SP_DESKTOP_E2E_', 'SP_BENCH_', 'SP_SCHEME_', 'SP_SCROLL_', 'SP_TERMLOG_']

const LEAKED_NAMES = new Set([
  'SCAN_DATA_ROOT', 'DATA_ROOT', 'SCAN_PORT', 'SCAN_CORS_ORIGINS', 'PORT', 'HOST', 'RELOAD', 'VITE_PORT',
  'CLAUDECODE', 'CLAUDE_PID', 'CLAUDE_CONFIG_DIR', 'CODEX_THREAD_ID', 'CODEX_HOME', 'TMUX', 'TMUX_PANE',
])

export function leaked(name: string): boolean {
  if (KNOB_PREFIXES.some((p) => name.startsWith(p))) return false
  return LEAKED_NAMES.has(name) || name.startsWith('SP_') || name.startsWith('CLAUDE_CODE_')
}

/** Remove the developer's shell variables from this process's environment. */
export function cleanEnv(env: NodeJS.ProcessEnv = process.env): string[] {
  const gone = Object.keys(env).filter(leaked)
  for (const name of gone) delete env[name]
  return gone
}
