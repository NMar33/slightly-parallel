/**
 * The guide's page list — one entry per product route, in route order,
 * written from what each page renders. The pages are the source of truth;
 * this file describes them in their own words.
 */

import { t } from '../../i18n/scope/shell'

interface GuidePage {
  /** The route as written in App.tsx (`/agent/:id` stays `/agent/:id`). */
  route: string
  title: string
  /** The `#` command an agent uses for this page, when there is one. */
  command?: string
  /** Every command of the page, when it has more than one. */
  commands?: string[]
  /** Two to five plain sentences: what the page is for, what is on it, what you can do. */
  text: string
}

export const GUIDE_PAGES: GuidePage[] = [
  {
    route: '/',
    title: t('Overview'),
    text:
      t('The home page. It shows the agents\' time today against a usual working day, the chats working now, the latest standups, what waits for your decision, and every day of the year that had agent time. A box at the top starts an agent on a new task. Each line links to the page where you act on it.'),
  },
  {
    route: '/project/:code',
    title: t('Project'),
    text:
      t('One project. Its tabs show an overview, its agents, tasks, sprints, calendar, terminals, decisions, chats, files, architecture and timer: the same as the pages for all projects, filtered to this one.'),
  },
  {
    route: '/agent',
    title: t('Agents'),
    text:
      t('Every agent, grouped by project: the agents you starred first, then the most recently active. Totals are at the top, with a search over names, ids and headlines; the group chips show one group. Click a card to open the agent.'),
  },
  {
    route: '/agent/:id',
    title: t('Agent'),
    text:
      t('One agent. Its name and project are at the top; the sections are listed on the left: overview, chats, files, decisions, tasks, features & fixes, links and subagents. The arrows open the previous and next agent of the same project. The open section is kept in the URL.'),
  },
  {
    route: '/architecture',
    title: t('Architecture'),
    commands: ['#page', '#map', '#architecture'],
    text:
      t("Three views per project, switched next to the picker. Page: what the project is and what is owed, each claim with its evidence; written at the end of a scan, or with #page. Map: every part of the program and how the parts connect; a helper agent writes it with #map. Changes: what each scan changed, in eight groups; written at the end of a scan, or with #architecture. Every path in all three is checked against the folder."),
  },
  {
    route: '/tour',
    title: t('Tour'),
    text:
      t('All tours: tours across the product, and one each for Visions, Rules, Problems and Skills. A tour runs on the real pages of the example project and points at examples on them. Write your own tours in the studio at /tour/custom.'),
  },
  {
    route: '/timelapse',
    title: t('Timelapse'),
    text:
      t("A project's history as a film. The rows of chips above the film set the colours, the frame shape and the chart under the board. The three tabs beside the film hold the rest: Film (scope, timing, what is on screen), Brand and Export. Every setting is in the URL, so a film can be shared as a link."),
  },
  {
    route: '/chats',
    title: t('Chats'),
    text:
      t('Every chat with an agent: when it ran, for how long, each message, and what came out of it. A long pause starts a new chat. Click a day in the month at the top to go to it. The agents and the chips beside it filter the list. The bar above the panes sets their widths and text sizes. Focus, or F, shows one chat full screen. Search covers every message.'),
  },
  {
    route: '/calendar',
    title: t('Calendar'),
    text:
      t('Month, week and milestone views for all projects, with a project picker. A milestone names a result, with a done-when check and its proof. Drag tasks onto milestones and days.'),
  },
  {
    route: '/visions',
    title: t('Visions'),
    command: '#vision',
    text:
      t("Ideas about where the project should go, kept from the chat. Type #vision in a message and it is kept as written. The agent's interpretation is at the top, your words below it, and the messages around it under Context. Chapters are listed on the left. Drag a vision onto a tag or a set. Drag a set onto a project under Projects to write it into that project's AGENTS.md."),
  },
  {
    route: '/entrypoints',
    title: t('Entry points'),
    command: '#entrypoint',
    text:
      t('The way into each topic, kept from the chat with #entrypoint. The agent writes what the topic is, where its files and links are, how to run it, where the work stopped and what is next. Open topics are at the top with their State line. Close a topic when it is done.'),
  },
  {
    route: '/problems',
    title: t('Problems'),
    command: '#problem',
    text:
      t('Problems kept from the chat with #problem. Open problems are at the top, each with what was tried. Create rule, under Rules from it, writes a rule linked to the problem. Type #problem solved to close one.'),
  },
  {
    route: '/rules',
    title: t('Rules'),
    command: '#rule',
    text:
      t('Corrections to how agents work, kept from the chat with #rule. A rule in For all agents is written into AGENTS.md in every project. A set of rules can be written into one project. Archiving a rule removes it from every project.'),
  },
  {
    route: '/skills',
    title: t('Skills'),
    command: '#skill',
    text:
      t('A skill is a folder with a SKILL.md that an agent loads when a task fits. Type #skill and the agent writes the steps from that chat. An open skill shows Projects, where you install it into one project or all; the name and description; Files; SKILL.md; and Used. “Not in Slightly Parallel” lists skill folders already on this computer; Take in adds one. “Not written” lists #skill messages with no draft yet.'),
  },
  {
    route: '/artifacts',
    title: t('Artifacts'),
    command: '#artifact',
    text:
      t('An artifact is a folder an agent made for you: a dataset, a document, a page or an app. Type #artifact and say what you want; the agent writes the folder in the project\'s data folder. Each kind has its own chapter. A dataset shows its fields and a sample, a document its text, a page opens in a frame, an app shows its files and its start command. Your request, Files and ARTIFACT.md are beside each one. Archive hides an artifact and keeps the folder. Add a folder adds one you made by hand.'),
  },
  {
    route: '/scans',
    title: t('Scans'),
    command: '#scan',
    text:
      t('A scan says what one agent changed in a project since its last scan, committed or not. Type #scan when work is shipped; the agent writes the scan, the file entry and the architecture form. At the top: the month as a grid shaded by the number of messages, the month in numbers, and the days that have a scan. Below, each day with its numbers and its scans: why, what changed, the important files, the changes and the proof. Files and Changes are collapsed; the switch in the title row expands them all. The five A\'s beside it set the text size.'),
  },
  {
    route: '/standups',
    title: t('Standups'),
    command: '#standup',
    text:
      t('A standup tells the story of a project\'s day: what was done, what went wrong, what moved, the decisions, and what may be forgotten. One per project per day, from all chats of that day. The first agent of a new day asks to write it; a helper agent on the model set in Settings writes it. Type #standup to write one now. At the top: the month shaded by the number of messages. Below, each day with its numbers and standup. A day with work and no standup is one grey line. The five A\'s set the text size; Focus, or F, shows one day full screen.'),
  },
  {
    route: '/decisions',
    title: t('Decisions'),
    command: '#decision',
    text:
      t('A decision says what was chosen, why, and what was rejected. Agents log decisions when a piece of work is done; type #decision to log one now. At the top: the month shaded by the number of messages, the month in numbers, and the days that have a decision. Below, each day with its numbers and decisions: the decision and its weight, why, the alternatives with the rejected ones struck through, and the chat it was made in. A day with work and no decision is one grey line. The five A\'s in the title row set the text size.'),
  },
  {
    route: '/kanban',
    title: t('Kanban'),
    command: '#task',
    commands: ['#task', '#evidence'],
    text:
      t('All boards: one per project, the saved boards, and + new board. Columns: Unclassified, Backlog, Next, From agents, To do, To do · parked, Doing, Review, Review later, Done, Done archived; the 3-col view hides Backlog, Next and Review. Agents add tasks only to From agents, with #task; you move the cards. A card opens the task window: description, tags, milestone, auto and evidence. #evidence in the chat attaches proof: the files changed and what was done. The evidence box asks for the same with a done report.'),
  },
  {
    route: '/sprints',
    title: t('Sprints'),
    text:
      t('Sprints of all projects, in two views. Running: each running sprint with its tasks and timer, edited in place. Progress: tasks, effort and lead time per day over the range. The top of the page is the same in both.'),
  },
  {
    route: '/files',
    title: t('Files'),
    text:
      t("Every project's file activity, drawn as a project's Files tab draws its own: the grid of files per scan, the ranking, the story cards with the agents' notes, and the weight map; the same orderings. A row of project chips narrows it to one project, and a dot on each file says which project it is from."),
  },
  {
    route: '/guide',
    title: t('Guide'),
    text: t('This page.'),
  },
  {
    route: '/about',
    title: t('About'),
    text: t('The name, the drawing behind it and the version. Opens from the mark at the top of the sidebar.'),
  },
  {
    route: '/prompts',
    title: t('Prompts'),
    command: '#prompt',
    text:
      t('Your prompts as a table. Type #prompt in a message and it is saved as a prompt; the agent writes nothing. Click a row to open the prompt: versions A and B, the rating, the diff, and below them the chats it was sent in and what they changed.'),
  },
  {
    route: '/internals',
    title: t('Internals'),
    text:
      t('How chats are recorded: what is saved per message, the notices agents receive, the known failures, and a check of your data files. Badges show what is tested and what was seen working.'),
  },
  {
    route: '/important',
    title: t('Important'),
    text:
      t('Everything you marked important, in three sections: messages, agents and tasks. Type #important in a message to mark it, its agent and the task it names; #important-agent, #important-task or #important-message marks only one. You can also click ★ on the board, on agent cards and in the chat reader. A task\'s ★ is the same star as on the board.'),
  },
  {
    route: '/stats',
    title: t('Statistics'),
    text:
      t('What each finished task took: messages and time in the chat, commits and files, the time from creation and from the first message to done, and whether it was closed with #done in the chat or on the board. For a task closed with #done the chat stretch is exact; for others it is estimated from where the task was named. Click a task to open it.'),
  },
  {
    route: '/time',
    title: t('Timer'),
    text:
      t('The timers of all projects and where your time went. At the top: the totals, today as a dial and the last 26 weeks, for all projects. Below, a row per block: start, pause and stop its timer, set the project\'s mode, and see its time on each of the last 7 days. Then the entries of those days. Shares, notes and edits are on the project\'s Timer tab.'),
  },
  {
    route: '/terminal',
    title: t('Terminal'),
    text:
      t('A shell on this computer, in the dashboard. The ` key opens it on any page; this page lists the terminals by project. Resume reopens a chat\'s agent; Start an agent opens one on a task. Each terminal shows its state; the top bar is highlighted when an agent waits. To copy, drag or Shift+drag; right-click for Paste, Copy the last output and Select lines (click two lines to copy all between). Ctrl+click a path such as src/app.ts:42 to open it in your editor. Ctrl+Shift+F searches. With tmux, terminals stay open after a reload or restart.'),
  },
  {
    route: '/monitor',
    title: t('Monitor'),
    text:
      t('This computer\'s CPU, memory, disk, network, connection and temperature, read every few seconds. Unusual readings are saved as events with the processes running at that moment; readings are thinned out as they age, events are kept longer. The switch turns monitoring off; Settings set what is read, how often, and what counts as unusual. Under the charts, the server itself: uptime, memory, whether every data file was read, reloads, capture and backups, the request time per path and the log by level. One button copies that section as text for an AI.'),
  },
  {
    route: '/backups',
    title: t('Backups'),
    text:
      t('Copies of the whole data folder, saved next to it as .tar.gz files. Back up now makes one; automatic backups keep one copy per period, and a pinned copy is kept for good. Verify test-restores a copy. Restore replaces the current data with a copy. Download saves the file.'),
  },
  {
    route: '/setup',
    title: t('Setup'),
    text:
      t('Start here. Choose the folder for your data, then connect your projects: Setup writes the hook that records chats, the agent tools and a section of AGENTS.md, and shows their state. Disconnect removes what Setup wrote. Delete data moves a project\'s data to .trash/.'),
  },
  {
    route: '/settings',
    title: t('Settings'),
    text: t("The language first: it applies at once and reloads the page. Then the dashboard's settings, each with its label, limits and default, saved when you click Save. Below them, cards for appearance, the sidebar, agent prompts and the data folder, and what is set in .env."),
  },
  {
    route: '/settings/prompts',
    title: t('Agent prompts'),
    text:
      t('The instructions agents read, block by block, each with an edit button. Every version is kept with its diff; you can restore any version or reset one block.'),
  },
  {
    route: '/settings/appearance',
    title: t('Appearance'),
    text: t('Theme, skin, accent, language and scale. Each choice applies at once and is kept for every browser.'),
  },
  {
    route: '/settings/sidebar',
    title: t('Sidebar'),
    text: t('The groups and pages of the sidebar. Drag to reorder, rename a group, hide a page or bring it back.'),
  },
  {
    route: '/search',
    title: t('Search'),
    text: t('Search tasks, entries and chats. Each result links to its page.'),
  },
]

/** The anchor a page's section uses, so `/guide#skills` opens on Skills. */
export function guideAnchor(route: string): string {
  const slug = route.replace(/^\//, '').replace(/[/:]+/g, '-').replace(/-+$/, '')
  return slug || 'overview'
}
