import { locale, t } from '../../../i18n/scope/aqua'
import type { TerminalAgentKind } from '../../../lib/terminalLimit'

export const limitAgents: Record<TerminalAgentKind, string> = {
  claude: t('Claude Code'), codex: t('Codex'), opencode: t('OpenCode'), shell: t('Shell'),
}

export function memoryText(bytes: number | null): string {
  if (bytes == null) return t('Unavailable')
  const n = new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 })
  return bytes >= 1e9
    ? t('{amount} GB', { amount: n.format(bytes / 1e9) })
    : t('{amount} MB', { amount: n.format(bytes / 1e6) })
}
