import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Cog } from 'lucide-react'

import { Badge } from '../components/primitives'
import { useTabFromHash } from '../hooks/useTabFromHash'
import { formatStamp } from '../utils/dateUtils'
import { PageHeader } from '../components/PageHeader'
import { getJson } from '../lib/getJson'
import { t, tn } from '../i18n/scope/pages'
import { rich } from '../i18n/rich'

/**
 * InternalsPage — how the machine works, concisely, with honesty badges.
 *
 * Three subpages (hash tabs): turn capture, the auto-trigger signals, and
 * the known failure modes. Every subpage leads with a five-second summary
 * card; depth follows for whoever wants it. Evidence badges state what is
 * tested/verified and when — live flags where the data can prove it.
 */

const TAB_IDS = ['capture', 'signals', 'breakage', 'doctor'] as const
type TabId = (typeof TAB_IDS)[number]
const isTab = (raw: string): raw is TabId =>
  (TAB_IDS as readonly string[]).includes(raw)

interface AdapterFlags {
  claude_verified: boolean
  opencode_verified: boolean
  codex_verified: boolean
  cursor_verified: boolean
}

export default function InternalsPage() {
  useEffect(() => {
    document.title = `${t('Internals')} — Slightly Parallel`
  }, [])
  const [tab, setTab] = useTabFromHash<TabId>(isTab, 'capture')

  const info = useQuery({
    queryKey: ['setup', 'info'],
    queryFn: ({ signal }) => getJson<{ adapters: AdapterFlags }>('/api/setup/info', signal),
  })
  const adapters = info.data?.adapters

  return (
    <div className="flex flex-col gap-24 min-w-0">
      <PageHeader
        icon={Cog}
        title={t('Internals')}
        tagline={t('How capture works, what triggers entries, what can break, and a check of the data files.')}
      />

      <div
        role="tablist"
        aria-label={t('Internals tabs')}
        className="flex gap-4 border-b border-border-subtle"
      >
        {(
          [
            ['capture', t('Capture')],
            ['signals', t('Auto-triggers')],
            ['breakage', t('What can break')],
            ['doctor', t('Data check')],
          ] as Array<[TabId, string]>
        ).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`px-12 py-8 text-13 border-b-2 -mb-px transition-colors duration-fast ${
              tab === id
                ? 'border-brand text-primary font-medium'
                : 'border-transparent text-secondary hover:text-primary'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'capture' && <CaptureTab adapters={adapters} />}
      {tab === 'signals' && <SignalsTab />}
      {tab === 'breakage' && <BreakageTab />}
      {tab === 'doctor' && <DoctorTab />}
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * Shared building blocks
 * ------------------------------------------------------------------------- */

function ShortCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-card border-l-2 border-brand bg-surface px-16 py-12 flex flex-col gap-6">
      <div className="text-11 uppercase tracking-wider text-tertiary font-medium">
        {t('In short')}</div>
      {children}
    </div>
  )
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-baseline gap-8 text-13 text-secondary leading-relaxed max-w-reading">
      <span aria-hidden className="text-brand">
        ·
      </span>
      <span>{children}</span>
    </li>
  )
}

function Deep({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="rounded-card border border-border-subtle bg-surface open:pb-12">
      <summary className="cursor-pointer select-none px-16 py-10 text-13 font-medium text-primary hover:bg-hover rounded-card">
        {title}
      </summary>
      <div className="px-16 flex flex-col gap-8 text-13 text-secondary leading-relaxed max-w-reading">
        {children}
      </div>
    </details>
  )
}

function EvidenceRow({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-6">{children}</div>
}

/* ---------------------------------------------------------------------------
 * 1 — Turn capture
 * ------------------------------------------------------------------------- */

function CaptureTab({ adapters }: { adapters?: AdapterFlags }) {
  return (
    <div className="flex flex-col gap-16">
      <EvidenceRow>
        <Badge tone="done">{t('capture is covered by tests')}</Badge>
        {adapters?.claude_verified ? (
          <Badge tone="done">{t('Claude Code · verified live since 14 Aug 2026')}</Badge>
        ) : (
          <Badge tone="warning">{t('Claude Code · waiting for a first captured agent')}</Badge>
        )}
        <Badge tone={adapters?.opencode_verified ? 'done' : 'warning'}>
          {adapters?.opencode_verified
            ? t('OpenCode · verified live')
            : t('OpenCode · experimental')}
        </Badge>
        <Badge tone={adapters?.codex_verified ? 'done' : 'warning'}>
          {adapters?.codex_verified ? t('Codex · verified live') : t('Codex · experimental')}
        </Badge>
        <Badge tone={adapters?.cursor_verified ? 'done' : 'warning'}>
          {adapters?.cursor_verified ? t('Cursor · verified live') : t('Cursor · experimental')}
        </Badge>
      </EvidenceRow>

      <ShortCard>
        <ul className="flex flex-col gap-4">
          <Bullet>
            {t('A hook in your coding tool runs twice a turn: when you send a message, and when the agent finishes its answer.')}</Bullet>
          <Bullet>
            {rich(t('Both are written **verbatim** to `chat.md` in your data root. The model never logs anything and spends no tokens on it.'))}</Bullet>
          <Bullet>
            {t('Timestamps group turns into chats. Lanes, hours and heatmaps are counted from them.')}</Bullet>
        </ul>
      </ShortCard>

      <Deep title={t('The mechanics, one level deeper')}>
        <p>
          {rich(t('One writer, four adapters. The capture core (`scripts/hooks/capture.py`, stdlib-only) is the only code that writes turns. Claude Code reaches it through two hooks in `.claude/settings.local.json` (prompt-submit opens the turn, response-end completes it from the transcript); Codex through the same two hooks in `.codex/hooks.json`; Cursor through three hooks in `.cursor/hooks.json` (the prompt, the response, the end of the loop); OpenCode through a project plugin.'))}</p>
        <p>
          {t('An error inside capture is caught and logged, and the coding session goes on. Capture writes the files itself, without the server, so turns are recorded while the dashboard is down.')}</p>
        <p>
          {t('Lines that look like turn headers inside a message (a pasted chat page, for example) are escaped when written, so they stay text. A message resent while the previous turn is still unanswered is deduplicated into one turn.')}</p>
      </Deep>

      <Deep title={t('File format on disk')}>
        <p>
          {rich(t("`projects/<code>/chats/<agent>/chat.md` is a plain markdown log: `## Turn N · timestamp`, then `**User**:` and `**Agent**:` blocks, multiline and as written. Next to it, `meta.json` holds the agent's identity, display name and turn counter. Deleting the folder deletes that history, and it is the only place it is held."))}</p>
      </Deep>

      <Deep title={t('What a project needs')}>
        <ul className="flex flex-col gap-6 list-disc pl-16">
          <li>
            {rich(t('**A plain folder.** Capture, chats, hours and every entry the agent posts work in a folder with no repository in it. A turn notes the files it changed, git or no git, and with git the commits it made too.'))}</li>
          <li>
            {rich(t('**Commits are optional.** With git, a scan lists the chat\'s own commits and what is not committed, and file entries get their line counts and diffs from the working tree, so uncommitted work counts. A first entry diffs since HEAD, and a repository still waiting for its first commit counts every listed file as new.'))}</li>
          <li>
            {rich(t("**What a repo adds:** per-path `+/−` lines, created, modified and deleted, and the `--stat` as the evidence, all filled by the server, so the agent writes only its judgement. Without a repository the agent's own numbers stand and the entry says no repo · agent counts."))}</li>
          <li>
            {rich(t('**Hooks are per folder.** Claude Code loads `.claude/settings.local.json` from the directory it is started in, and from that directory only. Start the agent in the integrated folder; the first-turn `[slightly-parallel] … your agent_id is …` line is the proof.'))}</li>
        </ul>
      </Deep>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * 2 — Auto-triggers
 * ------------------------------------------------------------------------- */

function SignalsTab() {
  return (
    <div className="flex flex-col gap-16">
      <EvidenceRow>
        <Badge tone="done">{t('unit-tested (thresholds honor Settings)')}</Badge>
        <Badge tone="done">{t('decision hint · observed live 14 Aug 2026')}</Badge>
        <Badge tone="warning">{t('standup via hooks · unit-tested')}</Badge>
        <Badge tone="warning">{t('file-entry reminder · unit-tested')}</Badge>
      </EvidenceRow>

      <ShortCard>
        <ul className="flex flex-col gap-4">
          <Bullet>
            {rich(t("When a turn is recorded, the hook checks five conditions. When one is met, it adds a short `[slightly-parallel]` notice to the agent's context."))}</Bullet>
          <Bullet>
            {t('The agent then follows the contract. Nothing else runs in the background.')}</Bullet>
        </ul>
      </ShortCard>

      <Deep title={t('The five triggers')}>
        <ul className="flex flex-col gap-6 list-disc pl-16">
          <li>
            {rich(t("**Standup due.** On the first captured turn of a new calendar day, the notice tells the agent that yesterday has no standup. The agent asks you: write it now, with or without the map of the program, or postpone."))}</li>
          <li>
            {rich(t('**Decision hint.** When your message matches a decision phrase ("decided to", "chose X over"), the notice asks the agent to offer to log the decision.'))}</li>
          <li>
            {rich(t('**Contract refresh.** Every N captured turns (default 25) the agent re-reads SLIGHTLY-PARALLEL.md and the rules in AGENTS.md, so the contract is current again after a long chat or a context compaction.'))}</li>
          <li>
            {rich(t("**File entry due.** When the project's latest scan (today or yesterday) still has no file entry behind it, the agent is told once, per scan, to post the per-path judgement. This is the third of three reminders: the contract makes it part of `#scan`, the scan response returns `files_entry: null` with a warning, and this notice catches a skipped entry on the next turn."))}</li>
          <li>
            {rich(t("**Architecture due.** When the project's latest scan (today or yesterday) still has no architecture form behind it, the agent is told once, per scan, to post the eight-group form."))}</li>
        </ul>
        <p>
          {rich(t('The thresholds are set in Settings → Agent signals and saved in `settings.json` in the data folder, where the capture core reads them.'))}</p>
      </Deep>

      <Deep title={t('Which tools get them')}>
        <p>
          {t("Only Claude Code can receive notices during a chat: the output of its prompt hook is added to the model's context. Codex and Cursor read a hook's output as control JSON, and OpenCode has no such channel, so the three follow the contract in AGENTS.md only.")}</p>
      </Deep>
    </div>
  )
}

/* ---------------------------------------------------------------------------
 * 3 — What can break
 * ------------------------------------------------------------------------- */

function BreakItem({
  status,
  date,
  title,
  children,
}: {
  status: 'fixed' | 'by-design' | 'theoretical'
  date?: string
  title: string
  children: React.ReactNode
}) {
  const badge =
    status === 'fixed' ? (
      <Badge tone="done">{t('fixed')}{date ? ` · ${date}` : ''}</Badge>
    ) : status === 'by-design' ? (
      <Badge tone="neutral">{t('by design')}</Badge>
    ) : (
      <Badge tone="warning">{t('theoretical')}</Badge>
    )
  return (
    <div className="rounded-card border border-border-subtle bg-surface px-16 py-12 flex flex-col gap-4">
      <div className="flex items-center gap-8 flex-wrap">
        <span className="text-13 font-medium text-primary">{t(title)}</span>
        {badge}
      </div>
      <p className="text-13 text-secondary leading-relaxed">{children}</p>
    </div>
  )
}

function BreakageTab() {
  return (
    <div className="flex flex-col gap-16">
      <ShortCard>
        <ul className="flex flex-col gap-4">
          <Bullet>
            {t('When capture fails, a turn is missing. The coding tool and the data on disk are not affected.')}</Bullet>
          <Bullet>
            {t('Each case below was found while using Slightly Parallel on its own code, and is marked with its state.')}</Bullet>
        </ul>
      </ShortCard>

      <BreakItem status="fixed" date="14 Aug 2026" title="Hooks install mid-chat">
        {t("Coding tools read the hook settings when a chat starts, so capture begins with the next chat after the hooks are installed. Step 3 of Setup says so.")}
      </BreakItem>

      <BreakItem status="fixed" date="14 Aug 2026" title="Quoted turns parsed as turns">
        {t("A pasted chat page contained turn headers, and the parser counted them as turns. Such lines are now escaped when written; a test checks it.")}
      </BreakItem>

      <BreakItem status="fixed" date="14 Aug 2026" title="Resent message captured twice">
        {t("Interrupting and resending the same message produced two turns. The same text sent again before an answer is now recorded once.")}
      </BreakItem>

      <BreakItem status="fixed" date="14 Aug 2026" title="System notifications became turns">
        {t("Background-task notifications arrive through the same event as messages and were recorded as turns. They are now skipped.")}
      </BreakItem>

      <BreakItem status="fixed" date="19 Aug 2026" title="Started in a subfolder, with nothing captured">
        {rich(t("The hooks were installed at the registered path, and the chat was started in a subfolder, where Claude Code does not look for them. No turns were recorded and nothing said so. The AGENTS.md section now tells the agent to report a missing first-turn `[slightly-parallel]` line, and Setup shows per project whether the hooks are in that folder."))}
      </BreakItem>

      <BreakItem status="by-design" title="File entries work without git">
        {t("Git is optional. Without a repository, a scan lists the files each turn changed instead of commits, and file entries carry the agent's own counts and say so.")}
      </BreakItem>

      <BreakItem status="theoretical" title="Codex, OpenCode and Cursor payload drift">
        {t("The three adapters read event formats that change between tool versions. When a format changes, no turns are recorded and no error is shown; the agent's lane stays empty. The experimental badge on Setup turns to verified after the first recorded turn.")}
      </BreakItem>

      <BreakItem status="theoretical" title="Stale paths after moving things">
        {t("Hook commands contain absolute paths (the Slightly Parallel folder and the data folder). After moving either, nothing is recorded until the project is integrated again. Setup marks such integrations as stale.")}
      </BreakItem>

      <BreakItem status="by-design" title="Backend edits need a restart">
        {rich(t("The server loads backend code changes only on a restart: `./sp.sh restart`. In dev mode the UI reloads by itself."))}
      </BreakItem>

      <BreakItem status="by-design" title="One chat is one agent lane">
        {t("Each chat has its own agent identity, so parallel chats stay apart. A new chat starts a new lane. Rename lanes to keep them clear; the oldest drop off the end of the list.")}
      </BreakItem>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Data doctor: a structure check over a database made of files
// ---------------------------------------------------------------------------

type DoctorIssue = {
  severity: 'error' | 'warning'
  kind: string
  file: string
  detail: string
  id?: string
  line?: number
}

type DoctorReport = {
  ok: boolean
  generated_at: string
  checked: { files: number; rows: number }
  errors: number
  warnings: number
  truncated: boolean
  issues: DoctorIssue[]
}

function DoctorTab() {
  const report = useQuery({
    queryKey: ['doctor'],
    queryFn: ({ signal }) => getJson<DoctorReport>('/api/doctor', signal),
  })
  const d = report.data
  return (
    <section className="flex flex-col gap-16" aria-label={t('Data check')}>
      <ShortCard>
        {t('The data is plain text files, which can be edited by hand, restored from backups or written by other tools. The check reads every file the dashboard reads and lists each damaged row. It does not change anything.')}
      </ShortCard>

      {report.isLoading && !report.data && (
        <p className="text-13 text-tertiary">{t('Checking every file…')}</p>
      )}
      {report.isError && (
        <p className="text-13 text-status-red">
          {t('The check could not run: {error}', { error: String((report.error as Error)?.message) })}
        </p>
      )}

      {d && (
        <div className="flex flex-col gap-12">
          <div className="flex items-baseline gap-12 flex-wrap">
            <span
              className="text-16 font-semibold"
              style={{ color: d.ok ? 'var(--status-green)' : d.errors > 0 ? 'var(--status-red)' : 'var(--status-amber)' }}
            >
              {d.ok
                ? t('Everything readable')
                : `${tn(d.errors, '{n} error', '{n} errors')} · ${tn(d.warnings, '{n} warning', '{n} warnings')}`}
            </span>
            <span className="text-11 font-mono text-tertiary">
              {t('{files} files · {rows} rows checked', { files: d.checked.files, rows: d.checked.rows })} · {formatStamp(d.generated_at)}
            </span>
            <button
              type="button"
              onClick={() => void report.refetch()}
              className="ml-auto h-24 px-10 rounded-pill border border-border-default text-11 font-mono text-secondary hover:border-brand hover:text-brand"
            >
              {t('run again')}
            </button>
          </div>

          {d.issues.length > 0 && (
            <ul className="flex flex-col gap-6">
              {d.issues.map((issue, i) => (
                <li
                  key={i}
                  className="rounded-input border bg-surface px-12 py-8 flex flex-col gap-2"
                  style={{ borderColor: issue.severity === 'error' ? 'var(--status-red)' : 'var(--status-amber)' }}
                >
                  <span className="flex items-baseline gap-8 flex-wrap">
                    <span className="text-11 font-mono font-semibold" style={{ color: issue.severity === 'error' ? 'var(--status-red)' : 'var(--status-amber)' }}>
                      {issue.kind}
                    </span>
                    <span className="text-11 font-mono text-tertiary">
                      {issue.file}
                      {issue.line != null && `:${issue.line}`}
                      {issue.id && ` · ${issue.id}`}
                    </span>
                  </span>
                  <span className="text-12 text-secondary leading-snug">{issue.detail}</span>
                </li>
              ))}
            </ul>
          )}
          {d.truncated && (
            <p className="text-11 font-mono text-status-amber">
              {t('Only the first problems are listed. Fix them and run again.')}</p>
          )}
          {d.ok && (
            <p className="text-12 text-tertiary leading-relaxed">
              {rich(t("Checked: every CSV's structure (ragged rows, blank and duplicate ids), every row against the code that reads it, every detail reference, and every vocabulary the filters use. A source that failed to load is listed here as `load-error`."))}
            </p>
          )}
        </div>
      )}
    </section>
  )
}
