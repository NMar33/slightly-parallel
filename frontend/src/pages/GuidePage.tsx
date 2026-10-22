import { useEffect, useState } from 'react'
import { LABEL, TH } from '../components/ui'
import { Link } from 'react-router-dom'
import { BookOpenText } from 'lucide-react'

import { Badge } from '../components/primitives'
import { CopyButton } from '../components/CopyButton'
import { PageHeader } from '../components/PageHeader'
import { LENS_LIST, type LensConfig } from '../lenses/config'
import { tourHref } from '../features/tour/LiveTour'
import { PRESETS } from '../features/tour/script'
import { GUIDE_PAGES, guideAnchor } from '../features/guide/pages'
import { WithContents, type ContentsItem } from '../components/WithContents'
import { t } from '../i18n/scope/pages'
import { rich } from '../i18n/rich'

/**
 * GuidePage — the manual, written from the pages. One section per product
 * page in route order, then the commands, how capture works, where the
 * files live, how a project is integrated, and what each agent is told.
 */
export default function GuidePage() {
  useEffect(() => {
    document.title = `${t('Guide')} — Slightly Parallel`
    const anchor = window.location.hash.replace(/^#/, '')
    if (anchor) {
      // Deep links like /guide#skills — react-router doesn't scroll anchors.
      document.getElementById(anchor)?.scrollIntoView({ block: 'start' })
    }
  }, [])

  return (
    <div className="flex flex-col gap-32 min-w-0">
      <PageHeader
        icon={BookOpenText}
        title={t('How Slightly Parallel works')}
        tagline={t('Agents write entries through the Slightly Parallel MCP tools, which append them to CSV and Markdown files on this machine. Every page here shows those files.')}
      />

      <WithContents label={t('On this page')} items={CONTENTS}>
      <div className="flex flex-wrap items-center gap-10 rounded-card border border-border-subtle bg-surface px-16 py-12 max-w-reading">
        <span className="text-13 text-secondary">
          {t('The tour walks the real dashboard, stop by stop.')}
        </span>
        <Link
          to={tourHref(PRESETS[0], 0)}
          className="rounded-input border border-brand bg-base px-10 py-3 text-12 text-primary hover:bg-hover"
        >
          {t('Take the tour')}
        </Link>
        <Link to="/tour" className="font-mono text-10 uppercase tracking-wide text-tertiary hover:text-primary">
          {t('all tours')}
        </Link>
      </div>

      <Section id="what" title={t('What Slightly Parallel does')}>
        <p>{t('Slightly Parallel records the projects you work on with coding agents. A hook records each message of the chat as it is sent. Agents post what they did through the Slightly Parallel MCP tools: scans, decisions, tasks, standups. Messages you tag in the chat are kept in your own words. The pages below show all of it.')}</p>
      </Section>

      <SectionHeader id="pages" title={t('The pages')} subtitle={t("In the order of the sidebar's routes.")} />
      <nav aria-label={t('Pages')} className="flex flex-wrap gap-6">
        {GUIDE_PAGES.map((p) => (
          <a
            key={p.route}
            href={`#${guideAnchor(p.route)}`}
            className="rounded-pill border border-border-subtle bg-surface px-8 py-2 text-12 text-secondary hover:text-primary"
          >
            {p.title}
          </a>
        ))}
      </nav>
      <div className="grid gap-x-24 gap-y-16 xl:grid-cols-2">
        {GUIDE_PAGES.map((p) => (
          <section
            key={p.route}
            id={guideAnchor(p.route)}
            className="flex flex-col gap-4 scroll-mt-24"
          >
            <div className="flex items-center gap-8 flex-wrap">
              <Link
                to={p.route.includes(':') ? p.route.split('/:')[0] : p.route}
                className="text-16 font-semibold text-primary hover:text-brand transition-colors duration-fast"
              >
                {p.title}
              </Link>
              <span className="text-11 font-mono text-tertiary">{p.route}</span>
              {(p.commands ?? (p.command ? [p.command] : [])).map((c) => (
                <Badge key={c} tone="info">
                  <span className="font-mono">{c}</span>
                </Badge>
              ))}
            </div>
            <p className="text-13 text-secondary leading-relaxed max-w-reading">{p.text}</p>
          </section>
        ))}
      </div>

      <Section id="commands" title={t('Commands')}>
        <p className="mb-8">{rich(t('Commands start with `#`. The older `/` form means the same. The agent acts on the command; the server keeps a tagged message as it is, and the agent adds what it means.'))}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-13">
            <thead>
              <tr className={`text-left ${TH}`}>
                <th className="py-8 pr-16">{t('Command')}</th>
                <th className="py-8 pr-16">{t('Page')}</th>
                <th className="py-8">{t('What happens')}</th>
              </tr>
            </thead>
            <tbody className="text-secondary">
              <CommandRow cmd="#scan" page={t('Scans')} what={t('The agent posts the scan, then the file entry and the architecture form behind it.')} />
              <CommandRow cmd="#architecture" page={t('Architecture')} what={t('The agent brings the architecture up to date: the form for the last scan, the page and the map, each only when it is out of date.')} />
              <CommandRow cmd="#page" page={t('Architecture')} what={t('The agent writes the next version of the architecture page.')} />
              <CommandRow cmd="#map" page={t('Architecture')} what={t('The agent asks first, then a helper agent maps the program.')} />
              <CommandRow cmd="#task <hint>" page={t('Kanban')} what={t('The agent writes the task you point at, from the chat, into From agents.')} />
              <CommandRow cmd="#evidence" page={t('Kanban')} what={t('The agent attaches the proof for the task: what it touched and what it did.')} />
              <CommandRow cmd="#done" page={t('Kanban')} what={t('The task moves to done; its messages up to here count as its work.')} />
              <CommandRow cmd="#decision" page={t('Decisions')} what={t('The agent logs the decision just made.')} />
              <CommandRow cmd="#problem <text>" page={t('Problems')} what={t('The message is kept as a problem. #problem solved closes one.')} />
              <CommandRow cmd="#standup" page={t('Standups')} what={t('The agent posts a standup now. One is also asked for when a new day starts.')} />
              <CommandRow cmd="#rule <text>" page={t('Rules')} what={t('The message is kept as a rule.')} />
              <CommandRow cmd="#vision <text>" page={t('Visions')} what={t('The message is kept as a vision.')} />
              <CommandRow cmd="#entrypoint <topic>" page={t('Entry points')} what={t('The agent writes the way into the topic: what, where, how, where it stopped, what is next.')} />
              <CommandRow cmd="#skill" page={t('Skills')} what={t('The agent writes a skill from what was done in this chat.')} />
              <CommandRow cmd="#artifact <what>" page={t('Artifacts')} what={t('The agent makes the folder you ask for: a dataset, a document, a page or an app.')} />
              <CommandRow cmd="#prompt" page={t('Prompts')} what={t('The message is kept in your prompt library.')} />
              <CommandRow cmd="#important" page={t('Important')} what={t('The message, its agent and the task it names are starred.')} />
              <CommandRow cmd="#undo <what was the mistake>" page="" what={t('Archives entries a tag made by mistake. The agent lists them by number; you answer with the numbers, then confirm with #undo-yes. Nothing is archived without it.')} />
              <CommandRow cmd="#help" page="" what={t('The agent lists these commands.')} />
            </tbody>
          </table>
        </div>
      </Section>

      <Section title={t('How chats are recorded')} id="capture">
        <div className="flex flex-col gap-8">
          <p>{rich(t('Setup installs a small hook into each integrated project (`.claude/settings.local.json` for Claude Code, `.codex/hooks.json` for Codex, `.cursor/hooks.json` for Cursor, a plugin for OpenCode). The hook runs when you send a message and when the agent finishes its answer. Both are recorded word for word, with a timestamp. The model is not involved, so capture costs no tokens.'))}</p>
          <p>{rich(t('Everything is saved as plain files in the data folder: `projects/<code>/chats/<agent>/chat.md` plus a small `meta.json`. Chats, hours and the agent timeline are derived from those timestamps. The grouping gap is a Setting. Deleting an agent’s folder deletes its history.'))}</p>
          <p>{rich(t('Identity: each chat is one agent (`cc-`, `oc-` or `codex-` plus the chat id). Rename an agent from the timeline; the display name lives in its `meta.json`, and the id stays the key. To stop capturing a project, re-integrate with the hook checkbox off, or Disconnect it on Setup.'))}</p>
        </div>
      </Section>

      <Section id="data" title={t('Data folder')}>
        <p>{rich(t('Each kind of entry is one CSV in the data folder (`decisions.csv`, `tasks.csv`, …). A row holds the headline and the fields. A markdown file in the detail folder beside it (`decision_details/*.md`) holds the text, and the row names it in `md_ref`. Per-project files sit under `projects/<code>/`. All of it is plain text you can open in an editor. The same entry written twice is kept once, with one id. Full details: `docs/api.md` and `/docs` on the backend port.'))}</p>
      </Section>

      <Section id="integrating" title={t('Integrating a project')}>
        <p className="mb-8">
          <Link to="/setup" className="text-brand hover:underline">
            {t('Setup')}
          </Link>{': '}
          {rich(t('page does this for you, with a preview and a status for each file. By hand: one contract, `SLIGHTLY-PARALLEL.md` at the root of the Slightly Parallel repo. Projects point at it, so an update to the Slightly Parallel folder reaches every project. In each project you want recorded, add a section to `AGENTS.md`, the file Codex, OpenCode, Cursor and others read:'))}
        </p>
        <pre className="text-12 font-mono text-secondary bg-elevated rounded-input p-12 overflow-x-auto whitespace-pre-wrap select-text">
{`cat >> AGENTS.md <<'EOF'

## Slightly Parallel
This project is observed by Slightly Parallel. Project code: my-app.
At the start of every chat, read /path/to/slightly-parallel/SLIGHTLY-PARALLEL.md and follow
it as your working contract.
EOF`}
        </pre>
        <p className="mt-8 mb-8">
          {rich(t('Claude Code reads `CLAUDE.md`. Add the one-line bridge:'))}
        </p>
        <pre className="text-12 font-mono text-secondary bg-elevated rounded-input p-12 overflow-x-auto whitespace-pre-wrap select-text">
{`echo "@AGENTS.md" >> CLAUDE.md`}
        </pre>
        <p className="mt-8">
          {t('Agents write through the Slightly Parallel MCP server, which Setup wires into the project. Every new chat reads the contract, in any tool and with any model, and follows it.')}
        </p>
      </Section>

      <SectionHeader
        id="agents"
        title={t('What agents are told')}
        subtitle={t('The instruction each page gives to an agent, as the agent receives it.')}
      />
      <div className="grid gap-16 xl:grid-cols-2">
        {LENS_LIST.map((l) => (
          <LensSection key={l.base} lens={l} />
        ))}
      </div>
      </WithContents>
    </div>
  )
}

/** The rail: the sections of this page, in the order they are written. */
const CONTENTS: ContentsItem[] = [
  { id: 'what', text: t('What Slightly Parallel does') },
  { id: 'pages', text: t('The pages'), note: String(GUIDE_PAGES.length) },
  { id: 'commands', text: t('Commands') },
  { id: 'capture', text: t('How chats are recorded') },
  { id: 'data', text: t('Data folder') },
  { id: 'integrating', text: t('Integrating a project') },
  { id: 'agents', text: t('What agents are told'), note: String(LENS_LIST.length) },
]

/* ------------------------------------------------------------------------- */

function Section({
  title,
  id,
  children,
}: {
  title: string
  id?: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="flex flex-col gap-8 scroll-mt-24">
      <h2 className="text-20 font-semibold text-primary">{title}</h2>
      <div className="text-13 text-secondary leading-relaxed max-w-reading">{children}</div>
    </section>
  )
}

function SectionHeader({ id, title, subtitle }: { id?: string; title: string; subtitle: string }) {
  return (
    <div id={id} className="border-t border-border-subtle pt-24 scroll-mt-24">
      <h2 className="text-24 font-semibold text-primary mb-4">{title}</h2>
      <p className="text-13 text-tertiary max-w-reading">{subtitle}</p>
    </div>
  )
}

function CommandRow({ cmd, page, what }: { cmd: string; page: string; what: string }) {
  return (
    <tr className="border-t border-border-subtle">
      <td className="py-8 pr-16 font-mono text-primary whitespace-nowrap">{cmd}</td>
      <td className="py-8 pr-16 whitespace-nowrap">{page}</td>
      <td className="py-8">{what}</td>
    </tr>
  )
}

function LensSection({ lens }: { lens: LensConfig }) {
  const Icon = lens.icon
  return (
    <section
      id={`agent-${lens.base}`}
      className="rounded-card border border-border-subtle bg-surface p-24 flex flex-col gap-16"
    >
      <header className="flex items-start gap-12">
        <Icon size={20} className="text-brand shrink-0 mt-2" aria-hidden />
        <div className="min-w-0">
          <div className="flex items-center gap-8 flex-wrap">
            <Link
              to={`/${lens.base}`}
              className="text-16 font-semibold text-primary hover:text-brand transition-colors duration-fast"
            >
              {lens.title}
            </Link>
            {lens.command && (
              <Badge tone="info">
                <span className="font-mono">{lens.command}</span>
              </Badge>
            )}
          </div>
          <p className="text-13 text-secondary mt-2">{lens.question}</p>
        </div>
      </header>

      <div>
        <h3 className={`${LABEL} mb-4`}>
          {t('How entries are collected')}
        </h3>
        <p className="text-13 text-secondary leading-relaxed max-w-reading">{lens.workflow}</p>
      </div>

      <div>
        <h3 className={`${LABEL} mb-4`}>
          {t('What an entry holds')}
        </h3>
        <dl className="flex flex-col gap-2">
          {lens.holds.map((h) => (
            <div key={h.name} className="flex items-baseline gap-8 text-13">
              <dt className="font-mono text-12 text-primary shrink-0">{h.name}</dt>
              <dd className="text-secondary leading-relaxed">{t(h.line)}</dd>
            </div>
          ))}
        </dl>
      </div>

      <AgentPromptBlock lens={lens} />
    </section>
  )
}

function AgentPromptBlock({ lens }: { lens: LensConfig }) {
  const [open, setOpen] = useState(false)

  return (
    <div>
      <div className="flex items-center gap-8">
        <h3 className={LABEL}>
          {t('Agent prompt')}
        </h3>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="text-12 text-brand hover:underline"
        >
          {open ? t('hide') : t('show')}
        </button>
        <CopyButton
          text={lens.agentPrompt}
          title={t('Copy the {page} agent prompt', { page: lens.title })}
          label={<> {t('Copy')}</>}
          copiedLabel={<> {t('Copied')}</>}
          size={14}
          className="ml-auto inline-flex items-center gap-6 h-24 px-10 rounded-input text-12 text-secondary hover:text-primary hover:bg-hover"
        />
      </div>
      {open && (
        <pre className="mt-8 text-12 font-mono text-secondary bg-elevated rounded-input p-12 overflow-x-auto whitespace-pre-wrap select-text">
          {lens.agentPrompt}
        </pre>
      )}
    </div>
  )
}
