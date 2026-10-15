/**
 * The library of beats and the presets cut from it.
 *
 * Every beat lives here once; a preset is an ordered selection with the
 * rest switched off. Adding a scenario is adding a preset; adding a page
 * to film is adding a beat. The types, the clock and the camera helpers
 * stay in script.ts.
 */

import { t } from '../../i18n/scope/shell'

import type { Beat, Caption, Ending, Opening, Panel, Script } from './script'

/**
 * A beat, on by default. What it shows is also its first written caption,
 * in the plain voice, so the caption editor always has one to go back to;
 * `captions` holds the other voices (sell, story, tech) and follows it.
 */
const B = (b: Omit<Beat, 'on' | 'chapter' | 'captions'> & { chapter: string; on?: boolean; captions?: Caption[] }): Beat =>
  ({ on: true, ...b, captions: [{ voice: 'xp', title: b.title, text: b.text }, ...(b.captions ?? []).filter((c) => c.voice !== 'xp')] })

/** The chapters the studio groups beats by. */
const CH = {
  what: t('What it is'),
  board: t('The board'),
  loop: t('The agent loop'),
  adds: t('What it adds up to'),
  keep: t('What you keep'),
  agents: t('Agents'),
  time: t('Plans and time'),
  find: t('Search and history'),
  setup: t('Setup and settings'),
}

export const LIBRARY: Beat[] = [
  B({
    id: 'overview',
    chapter: CH.what,
    page: '/',
    title: t('The home page'),
    text: t('Claude Code, Codex, OpenCode and Cursor work in your repositories. The home page shows how long they worked yesterday, which chats run now and what waits for you.'),
    captions: [
      { voice: 'sell', title: 'Your agents\' day, at a glance', text: 'See how long Claude Code, Codex, OpenCode and Cursor worked, which chats run now and what waits for you, across every project, on one page.' },
      { voice: 'story', title: 'Open the home page', text: 'You open Slightly Parallel in the morning and click Yesterday. The day card shows the agents\' hours, commits and chats against a usual working day.' },
      { voice: 'tech', title: 'Derived from the chat logs', text: 'The page reads /api/snapshot and /api/sessions. Sessions are derived on read from each chat.md, split where the gap between turns is too long.' },
    ],
    // The example month ends yesterday: today's chart is flat until the
    // first chat. Yesterday is the day the example worked.
    action: { kind: 'click', selector: 'text="Yesterday"', frames: 4, interval: 200 },
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'capture',
    chapter: CH.what,
    page: '/project/{project}#activity',
    title: t('Chat capture'),
    text: t('A hook in the project saves every message and reply as Markdown files on your computer, with the commits of each turn. Any chat can be read later.'),
    captions: [
      { voice: 'sell', title: 'Every chat, kept word for word', text: 'Each conversation with Claude Code, Codex, OpenCode or Cursor is saved on your computer, so the reason behind any change can be found again.' },
      { voice: 'story', title: 'Work with the agent as usual', text: 'You chat with Claude Code in the project folder. Each message and reply appears on the Chats tab, with the commits of that turn.' },
      { voice: 'tech', title: 'Hooks and a chat.md', text: 'The hooks of Claude Code, Codex, OpenCode and Cursor run capture.py. It appends each turn to projects/<code>/chats/<agent_id>/chat.md and the turn\'s commits to work.jsonl.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'setup',
    chapter: CH.what,
    page: '/setup',
    title: t('Setup'),
    text: t('Enter the project\'s code and its folder and press Integrate. Setup writes the hook that records chats and the tools the agents use. Disconnect removes them.'),
    captions: [
      { voice: 'sell', title: 'One form per project', text: 'Connect a repository with one form. Disconnect removes every file Setup wrote, and your data stays.' },
      { voice: 'story', title: 'Add a project', text: 'You enter a project code and its folder, then press Integrate. The project appears under Integrated projects, and the next chat there is recorded.' },
      { voice: 'tech', title: 'Four files in the folder', text: 'POST /api/setup/integrate writes a block in AGENTS.md, the @AGENTS.md line in CLAUDE.md, hooks in .claude/settings.local.json and the MCP server in .mcp.json.' },
    ],
    zoom: 'full',
    hold: 5,
  }),

  B({
    id: 'board',
    chapter: CH.board,
    page: '/project/{project}#tasks',
    title: t('The task board'),
    text: t('Tasks are cards in columns: To do, Doing, Done. The colour on the edge is the priority, the small label is the area of the product.'),
    captions: [
      { voice: 'sell', title: 'All the agents\' work, one board', text: 'Every task your agents work on is on one board, so what is in progress and what is done show at a glance.' },
      { voice: 'story', title: 'Open the Tasks tab', text: 'You open a project\'s Tasks tab. The cards stand in columns by status, and the coloured edge shows each one\'s priority.' },
      { voice: 'tech', title: 'tasks.csv behind the board', text: 'Each card is a row in tasks.csv, with its text in task_details/. The board reads /api/tasks, and an empty status shows as Unclassified.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'drag-card',
    chapter: CH.board,
    page: '/project/{project}#tasks',
    title: t('Moving a card'),
    text: t('Drag a card into another column and the task gets that status. The move goes into the task\'s history with who did it and when.'),
    captions: [
      { voice: 'sell', title: 'Move work with a drag', text: 'Change a task\'s status by dragging its card. Every move is recorded with who made it and when.' },
      { voice: 'story', title: 'Drag the card into Doing', text: 'You drag Nightly Postgres backups into Doing. The card stays there, and the move is added to the task\'s history.' },
      { voice: 'tech', title: 'One event per changed field', text: 'The drop posts the status to /api/tasks/{id}/update. The server rewrites tasks.csv under a lock and appends the change to task_events.csv.' },
    ],
    // Walked live, the card is pointed at and left where it is; the film
    // drags it (the live tour never runs an action).
    selector: '[aria-label^="Edit task: Nightly Postgres backups"]',
    action: {
      kind: 'drag',
      selector: '[aria-label^="Edit task: Nightly Postgres backups"]',
      to: 'text="Doing"',
      focus: 'text="Doing"',
      frames: 8,
      interval: 150,
    },
    zoom: 'full',
    hold: 6.5,
  }),
  B({
    id: 'swim-lanes',
    chapter: CH.board,
    page: '/project/{project}#tasks',
    title: t('Swim lanes'),
    text: t('The same cards in one row per area of the project. The rows with the most cards are where the work is happening.'),
    captions: [
      { voice: 'sell', title: 'See which areas are busy', text: 'One row per area shows which parts of the project have the most work in progress.' },
      { voice: 'story', title: 'Switch to swim lanes', text: 'You click swim lanes in Board view. The same cards regroup into one row per area, with the columns kept.' },
      { voice: 'tech', title: 'Lanes from the assignee field', text: 'A lane is the task\'s assignee field, and an empty one goes to unassigned. The chosen view is kept in localStorage per project.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="Board view"] >> text="swim lanes"',
      // The example board opens in 3-col; put that back for the beats after.
      after: '[aria-label="Board view"] >> text="3-col"',
      frames: 5,
      interval: 170,
    },
    zoom: 'full',
    hold: 5.5,
  }),

  B({
    id: 'copy-task',
    chapter: CH.loop,
    page: '/project/{project}#tasks',
    title: t('The copy button'),
    text: t('Turn on copy and every card gets a copy button. It copies the task as instructions for an agent: the id, the latest text and the proof wanted.'),
    captions: [
      { voice: 'sell', title: 'Hand off a task by pasting', text: 'A card becomes ready instructions for any agent: the id, the latest text and the evidence wanted.' },
      { voice: 'story', title: 'Copy the card, paste it', text: 'You turn on copy and press the copy button on a card. You paste the text into the agent\'s chat, and the agent starts on that task.' },
      { voice: 'tech', title: 'Built from the task row', text: 'The copy holds the task id, its title and the newest round of text. An evidence task adds the prompt saved in evidence_prompts.json.' },
    ],
    selector: 'button[title="Show copy buttons and the handle that moves a whole column"]',
    action: {
      kind: 'click',
      selector: 'button[title="Show copy buttons and the handle that moves a whole column"]',
      frames: 3,
      interval: 200,
      focus: '[aria-label="Copy: task"]',
      after: 'button[title="Show copy buttons and the handle that moves a whole column"]',
    },
    zoom: 'push',
    hold: 6.5,
  }),
  B({
    id: 'agent-column',
    chapter: CH.loop,
    page: '/project/{project}#tasks',
    title: t('The From agents column'),
    text: t('When you type #task in a chat, the agent writes the task into this column. You give it a priority and a sprint, and it joins the plan.'),
    captions: [
      { voice: 'sell', title: 'Agents report the work they find', text: 'Bugs, debts and ideas an agent finds go into one column, and you decide which become planned work.' },
      { voice: 'story', title: 'Type #task in the chat', text: 'You point at a follow-up and type #task. The agent writes the task into From agents, and you unfold the column to plan it.' },
      { voice: 'tech', title: 'Status agent, enforced', text: 'The agent writes through write_entry, which posts to /api/tasks. The server forces status agent, requires one to three ag_ tags and drops priority and sprint.' },
    ],
    selector: '[aria-label="Unfold the From agents column"]',
    action: {
      kind: 'click',
      selector: '[aria-label="Unfold the From agents column"]',
      frames: 5,
      interval: 150,
      // The fold is remembered: left open, every later board is shot with it.
      after: '[aria-label="Fold the From agents column"]',
    },
    zoom: 'full',
    hold: 6,
  }),
  B({
    id: 'evidence',
    chapter: CH.loop,
    page: '/project/{project}#tasks',
    title: t('Evidence'),
    text: t('A task can ask for proof. The agent attaches it to its done report: here the timings and chart of a load test. You move it to Done.'),
    captions: [
      { voice: 'sell', title: 'Proof before you close a task', text: 'A task asks for evidence, and the agent brings timings, charts or screenshots with its report. You close it on what you see.' },
      { voice: 'story', title: 'Open the finished task', text: 'You open the load test task. The Evidence section shows the timings and the chart the agent attached; you move the card to Done.' },
      { voice: 'tech', title: 'task_report and task_evidence', text: 'The agent calls task_report, then task_evidence. Items go to task_evidence.csv and images to task_evidence/<task_id>/. With auto on, the card moves to Review.' },
    ],
    selector: '[aria-label^="Edit task: Load test: 50 checkouts"]',
    action: {
      kind: 'click',
      selector: '[aria-label^="Edit task: Load test: 50 checkouts"]',
      // The evidence itself is the subject, not the whole task form: the
      // dialog is nearly as tall as the window, so cropping to it crops to
      // everything. Aiming at the first item lands the camera on the proof.
      focus: 'text="p95 per step at 50/min"',
      frames: 6,
      interval: 150,
    },
    place: 'below',
    // Push, not focus: the proof is inside the card the click opens, so
    // before the click the focus rect is an empty patch of the board.
    zoom: 'push',
    hold: 7.5,
  }),
  B({
    id: 'contract',
    chapter: CH.loop,
    page: '/settings/prompts',
    // A settings page is reached from Settings in the sidebar.
    nav: 'nav a[href="/settings"], aside a[href="/settings"]',
    title: t('Agent prompts'),
    text: t('Agents write scans, decisions and reports by one instruction file. Edit it here, block by block. The next chats follow the new version.'),
    captions: [
      { voice: 'sell', title: 'You decide what agents are told', text: 'Change the instructions every agent follows from one page, and keep each earlier version.' },
      { voice: 'story', title: 'Edit a block', text: 'You open Agent prompts and press edit on a block. You change the text and save, and the next chats read the new version.' },
      { voice: 'tech', title: 'Composed from contract parts', text: 'SLIGHTLY-PARALLEL.md is composed from the parts in prompts/contract/. Each save recomposes it and keeps the earlier text under prompts/<key>/versions/.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),

  B({
    id: 'skills-install',
    chapter: CH.loop,
    page: '/skills',
    title: t('Skills'),
    text: t('Type #skill after the work and the agent writes a skill from what it did. Install it in one project or for every agent on this machine.'),
    captions: [
      { voice: 'sell', title: 'Reuse what worked', text: 'Turn the steps from a good chat into a skill, and give it to one project or to every agent you run.' },
      { voice: 'story', title: 'Type #skill, then Install', text: 'You type #skill after the work. The agent writes the draft; you open it on Skills and press Install.' },
      { voice: 'tech', title: 'skill_draft, then install', text: 'The agent sends SKILL.md with the MCP tool skill_draft. Install copies it to .claude/skills/ and .agents/skills/ in a project or in your home folder.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),

  B({
    id: 'decision-reasons',
    chapter: CH.adds,
    page: '/decisions',
    title: t('Decisions'),
    text: t('Type #decision after a choice. The choice, the reason and the options you turned down are kept under that day.'),
    captions: [
      { voice: 'sell', title: 'Know why, months later', text: 'Each choice keeps its reason and the options turned down. When someone asks why, the answer is on this page.' },
      { voice: 'story', title: 'Type #decision after a choice', text: 'You pick one option over another and type #decision. The agent logs the choice, its reason and the rejected options under that day.' },
      { voice: 'tech', title: 'decisions.csv through write_entry', text: 'The agent calls write_entry with lens decision. The row goes to decisions.csv and the text to decision_details/. The hook suggests one when a message sounds decided.' },
    ],
    zoom: 'full',
    hold: 6,
  }),
  B({
    id: 'scan-source',
    chapter: CH.loop,
    page: '/scans#project={project}',
    title: t('Scans'),
    text: t('Type #scan when the work is shipped. The agent writes what changed, why and which files. The line under the scan opens the message it was written from.'),
    captions: [
      { voice: 'sell', title: 'See the chat behind a record', text: 'A scan sits one click from the message it was written after, so the reasons behind a change stay readable.' },
      { voice: 'story', title: 'Type #scan, then follow the line', text: 'You type #scan when the work is shipped. The agent writes the scan; you click the line under it, and the chat opens on that turn.' },
      { voice: 'tech', title: 'Matched to a turn in chat.md', text: 'The scan is a row in scans.csv and a file in snapshots/. On the example project, the line asks /api/example/source, which finds the turn in chat.md by time.' },
    ],
    selector: '[data-tour="example-source"]',
    // The line asks the server which message the scan came from: it is
    // drawn a moment after the page.
    wait_for: '[data-tour="example-source"]',
    zoom: 'push',
    hold: 7,
  }),
  B({
    id: 'standup',
    chapter: CH.loop,
    page: '/standups#project={project}',
    title: t('The daily standup'),
    text: t('On the first message of the day the agent offers to write yesterday\'s standup. It reads that day\'s chats and writes what changed and what went wrong.'),
    captions: [
      { voice: 'sell', title: 'Yesterday, ready each morning', text: 'Start the day with one page on what changed, what went wrong and what may be forgotten, written from every chat of yesterday.' },
      { voice: 'story', title: 'Say yes to the standup', text: 'You send the first message of the day. The agent offers yesterday\'s standup; you agree, and a helper agent writes it from that day\'s chats.' },
      { voice: 'tech', title: 'standup_material, then write_entry', text: 'When yesterday has chats and standups.csv lacks that day, the hook prints a notice. A helper agent calls standup_material, then write_entry with lens standup.' },
    ],
    zoom: 'full',
    hold: 6,
  }),
  B({
    id: 'architecture-page',
    chapter: CH.adds,
    page: '/project/{project}#architecture',
    title: t('The architecture page'),
    text: t('An agent writes this page from the code: what the project is, what it does, what it is made of, what it owes. Each claim has its evidence.'),
    captions: [
      { voice: 'sell', title: 'The project, explained on one page', text: 'Anyone joining reads what the project is and what is owed, with the evidence for each claim.' },
      { voice: 'story', title: 'Type #page', text: 'You type #page in a chat. The agent reads the computed facts and writes the next version, and the tab shows it with its number.' },
      { voice: 'tech', title: 'vNNN.md through architecture_page', text: 'The agent calls architecture_material, then architecture_page. Each version is saved as projects/<code>/architecture/vNNN.md, and each path is checked against the folder.' },
    ],
    zoom: 'full',
    hold: 6.5,
  }),
  B({
    id: 'architecture',
    chapter: CH.adds,
    page: '/project/{project}#architecture',
    title: t('Architecture changes'),
    text: t('Beside the page, Changes lists what each scan added, changed or removed: endpoints, services, databases, libraries, debts.'),
    captions: [
      { voice: 'sell', title: 'Every structural change, scan by scan', text: 'See when an endpoint, a table or a debt appeared, changed or was removed, and which scan recorded it.' },
      { voice: 'story', title: 'Switch to changes', text: 'You click changes beside page. The list shows what each scan added, changed or removed, grouped by the part it touched.' },
      { voice: 'tech', title: 'An eight-group form per scan', text: 'After each #scan the agent writes the architecture form with write_entry, linked to the scan by trigger_id. Rows go to architecture.csv with op add, change or remove.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="Architecture mode"] >> text="changes"',
      // The mode is remembered for the whole app.
      after: '[aria-label="Architecture mode"] >> text="page"',
      frames: 4,
      interval: 200,
    },
    zoom: 'full',
    hold: 6.5,
  }),
  B({
    id: 'files',
    chapter: CH.adds,
    page: '/project/{project}#files',
    title: t('The files grid'),
    text: t('Every file the agents changed, day by day, as a grid. Colour it by lines changed or by importance.'),
    captions: [
      { voice: 'sell', title: 'See where the work happens', text: 'One grid shows which files the agents change most, so the busy parts of the code stand out.' },
      { voice: 'story', title: 'Read the grid', text: 'You open the Files tab. Each column is a day and each row a file; you switch color by to importance, and the grid recolours.' },
      { voice: 'tech', title: 'Built from file entries', text: 'Each #scan writes a file entry to files.csv, with per-file lines in file_details/. The grid reads /api/files/heatmap; git diff fills missing line counts.' },
    ],
    selector: '[aria-label="Files changed per scan"]',
    zoom: 'push',
    hold: 6,
  }),
  B({
    id: 'sprints',
    chapter: CH.time,
    page: '/sprints',
    title: t('Sprints'),
    text: t('A sprint is a block of work with a length in days and a budget of your hours. A running sprint shows days left, hours and tasks done.'),
    captions: [
      { voice: 'sell', title: 'Know where each sprint stands', text: 'Every running sprint shows its days left, your hours against the budget and the tasks done.' },
      { voice: 'story', title: 'Check the running sprints', text: 'You open Sprints. Each card shows the day of the sprint, the hours used and the tasks done; Finish asks for a short retro.' },
      { voice: 'tech', title: 'sprints.csv and the deck', text: 'A sprint is a row in sprints.csv with bet_days and time_budget_h. The page reads /api/sprints/deck; its timer posts to /api/time/start and stop.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'search',
    chapter: CH.find,
    page: '/search?q=refund',
    title: t('Search'),
    text: t('Tasks, decisions, scans, chats and map parts in one search. Each result names its kind, its project and its date.'),
    captions: [
      { voice: 'sell', title: 'One box for every record', text: 'Find the task, the decision or the chat turn where a word came up, across every project.' },
      { voice: 'story', title: 'Search for a word', text: 'You type refund. Entries and chat turns that mention it appear, and the rail on the left narrows them by kind, project or month.' },
      { voice: 'tech', title: 'One index, built from the files', text: 'searchlib indexes every CSV row with its Markdown text, map parts and each chat turn. /api/search matches lower-case text, title hits first, newer first.' },
    ],
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'timelapse',
    chapter: CH.find,
    page: '/timelapse?project={project}',
    // Opened from the board's toolbar, not the sidebar: nothing to ring.
    nav: '',
    // The film plays as the page opens. Shot at once it is the first days
    // of the month, an empty board; half way in the board is full.
    settle: 11000,
    title: t('The timelapse'),
    text: t('A month of the project in a few seconds: cards moving across the board, chats starting and ending, commits one by one. Export it as a GIF.'),
    captions: [
      { voice: 'sell', title: 'A month of work in seconds', text: 'Watch the board move, chats start and commits arrive, then export the film as a GIF to share.' },
      { voice: 'story', title: 'Play the month', text: 'You open Timelapse for a project. The film plays the month\'s board moves and chats; you press save GIF to export it.' },
      { voice: 'tech', title: 'Replayed from task_events.csv', text: '/api/timelapse reads status moves from task_events.csv, chats from the sessions table and commits from git log. The browser encodes the GIF with gifenc.' },
    ],
    zoom: 'full',
    hold: 6,
  }),
  // ---- What you keep: one tour per page, reached from the page itself ----
  B({
    id: 'visions-page',
    chapter: CH.keep,
    page: '/visions',
    title: t('Visions'),
    text: t('Type #vision in a chat to keep the message as a vision. The agent writes what it understood, and the page keeps both.'),
    captions: [
      { voice: 'sell', title: 'Your ideas, in your words', text: 'Every direction you give the product is kept as you said it, with the agent\'s reading beside it. One page holds them all.' },
      { voice: 'story', title: 'Type #vision in a message', text: 'You add #vision to a message about where the product should go. The page shows your words, and the agent\'s interpretation appears above them.' },
      { voice: 'tech', title: 'The hook keeps the message', text: 'The capture hook matches #vision and stores the message in visions.csv. The agent answers with the MCP tool interpret, and each version goes to kept_versions/.' },
    ],
    zoom: 'full',
    hold: 4.5,
  }),
  B({
    id: 'visions-context',
    chapter: CH.keep,
    page: '/visions',
    selector: 'details.rounded-input > summary',
    title: t('Context'),
    text: t('A vision keeps three turns of the chat before it and three after. Open context to read them.'),
    captions: [
      { voice: 'sell', title: 'The conversation comes with it', text: 'Each idea keeps the turns around it, so a month later you can read what led to it.' },
      { voice: 'story', title: 'Open the context fold', text: 'You click context under a vision. The turns before and after the message open in place, with the kept one marked.' },
      { voice: 'tech', title: 'Read from chat.md on open', text: 'The server reads up to three turns on each side from the chat\'s chat.md each time the vision opens. Only the message itself is stored.' },
    ],
    // Push, not full: a full view has no spotlight, and the film would show
    // the whole page while the caption talks about one control on it.
    zoom: 'push',
    hold: 4.5,
  }),
  B({
    id: 'visions-group',
    chapter: CH.keep,
    page: '/visions',
    selector: 'div[aria-label="group by"]',
    title: t('Grouping'),
    text: t('Group the visions by tag, project, month or set. The list regroups as you choose.'),
    captions: [
      { voice: 'sell', title: 'Sort ideas the way you think', text: 'Group the same visions by tag, project, month or set, and the page reorders at once.' },
      { voice: 'story', title: 'Pick a grouping', text: 'You click project in group by. The visions regroup into one chapter per project, listed on the left.' },
      { voice: 'tech', title: 'Grouped in the browser', text: 'Grouping runs in the browser over the loaded list, and the choice is kept in the URL hash. Sets come from sets.json in the data folder.' },
    ],
    zoom: 'push',
    hold: 4.5,
  }),
  B({
    id: 'visions-give',
    chapter: CH.keep,
    page: '/visions',
    selector: '[aria-label^="Copy: "]',
    title: t('Giving visions to agents'),
    text: t('Copy the text, or write a set into a project\'s AGENTS.md. Agents read it when a chat starts.'),
    captions: [
      { voice: 'sell', title: 'Ideas that reach your agents', text: 'A set of visions goes into a project\'s AGENTS.md, so each new chat there starts with your direction.' },
      { voice: 'story', title: 'Drag a set onto a project', text: 'You drag a set onto a project under Projects and press Write to AGENTS.md. The next agent started in that folder reads it.' },
      { voice: 'tech', title: 'A fenced block in AGENTS.md', text: 'POST /api/sets/{id}/integrate writes the set between sp:set markers in the project\'s AGENTS.md. Claude Code loads it through the @AGENTS.md line in CLAUDE.md.' },
    ],
    zoom: 'push',
    hold: 5,
  }),
  B({
    id: 'rules-page',
    chapter: CH.keep,
    page: '/rules',
    title: t('Rules'),
    text: t('Type #rule in a chat to add a rule. The agent writes the rule from your message.'),
    captions: [
      { voice: 'sell', title: 'Correct an agent once', text: 'Write the correction in the chat where it happened. It is kept as a rule, in your words, with the agent\'s reading beside it.' },
      { voice: 'story', title: 'Type #rule with the correction', text: 'You tell the agent what to do differently and add #rule. The message appears on Rules, and the agent\'s interpretation appears beside it.' },
      { voice: 'tech', title: 'Kept by the hook', text: 'The capture hook keeps the message in rules.csv with an rl_ id. The agent writes its reading with the MCP tool interpret, versioned in kept_versions/.' },
    ],
    zoom: 'full',
    hold: 4.5,
  }),
  B({
    id: 'rules-all',
    chapter: CH.keep,
    page: '/rules',
    selector: '[role="switch"][aria-label="For all agents"]',
    title: t('For all agents'),
    text: t('Turn on For all agents. Slightly Parallel writes the rule into AGENTS.md of every project and keeps it current.'),
    captions: [
      { voice: 'sell', title: 'One rule, every project', text: 'Switch a rule on once, and the AGENTS.md of every connected project carries it from then on.' },
      { voice: 'story', title: 'Turn on For all agents', text: 'You turn on the switch on a rule card. A toast says Added to every project, and each project\'s AGENTS.md gains the rule.' },
      { voice: 'tech', title: 'Synced into AGENTS.md', text: 'The switch posts auto=yes to /api/rules/{id}/update. sync_all_rules then rewrites the all-rules block in AGENTS.md of every folder in integrations.csv.' },
    ],
    zoom: 'push',
    hold: 5,
  }),
  B({
    id: 'rules-show',
    chapter: CH.keep,
    page: '/rules',
    selector: 'div[aria-label="show"]',
    title: t('Archive and restore'),
    text: t('Archive takes a rule out of every project and keeps the text. Restore puts it back.'),
    captions: [
      { voice: 'sell', title: 'Retire a rule, keep its words', text: 'Archive a rule when it is out of date. Its text stays on the page, and Restore brings it back.' },
      { voice: 'story', title: 'Archive, then restore', text: 'You press Archive on a rule. It moves under archived and is removed from every project; Restore puts it back.' },
      { voice: 'tech', title: 'A status in rules.csv', text: 'Archive sets the rule\'s status in rules.csv. The all-rules block holds active rules only, so the sync after the update removes it from each AGENTS.md.' },
    ],
    zoom: 'push',
    hold: 4.5,
  }),
  B({
    id: 'rules-from-problem',
    chapter: CH.keep,
    page: '/rules',
    selector: '[aria-label^="From problem"]',
    title: t('Rules from problems'),
    text: t('A rule can be written from a problem. The rule names the problem it came from.'),
    captions: [
      { voice: 'sell', title: 'Every rule keeps its reason', text: 'A rule made from a problem names that problem, so the reason for the rule stays beside it.' },
      { voice: 'story', title: 'See where a rule came from', text: 'You look at a rule card. From problem shows the id of the problem the rule was written after.' },
      { voice: 'tech', title: 'Linked by related_incident', text: 'A rule made from a problem stores the problem id in related_incident in rules.csv, with source set to problem. The card reads that link.' },
    ],
    zoom: 'push',
    hold: 4.5,
  }),
  B({
    id: 'problems-page',
    chapter: CH.keep,
    page: '/problems',
    title: t('Problems'),
    text: t('Type #problem in a chat to add a problem. The agent writes what happened and the fix.'),
    captions: [
      { voice: 'sell', title: 'Every failure, kept with its fix', text: 'What broke and what fixed it are kept together, so the next time the answer is already written.' },
      { voice: 'story', title: 'Type #problem in the chat', text: 'You describe what went wrong and add #problem. The message is kept, and the agent writes what happened and what fixed it.' },
      { voice: 'tech', title: 'problems.csv and an interpretation', text: 'The capture hook keeps the message in problems.csv with a pb_ id. The agent\'s reading arrives through the MCP tool interpret.' },
    ],
    zoom: 'full',
    hold: 4.5,
  }),
  B({
    id: 'problems-open',
    chapter: CH.keep,
    page: '/problems',
    selector: 'nav[aria-label="Open now"]',
    title: t('Open problems'),
    text: t('Open problems stay at the top until you resolve them. Resolve marks one as fixed.'),
    captions: [
      { voice: 'sell', title: 'Open problems stay in sight', text: 'Unresolved problems sit in a strip at the top of the page until you close them.' },
      { voice: 'story', title: 'Resolve one', text: 'You press Resolve on a problem card. A toast says Marked as resolved, and the problem leaves the Open now strip.' },
      { voice: 'tech', title: 'status and resolved_date', text: 'Resolve posts status resolved and today\'s date to /api/problems/{id}/update. In a chat, #problem solved does the same through the MCP tool update_entry.' },
    ],
    zoom: 'push',
    hold: 4.5,
  }),
  B({
    id: 'problems-rule',
    chapter: CH.keep,
    page: '/problems',
    // The one problem a rule was made from; the others still show the empty
    // list, and that is not the story.
    selector: 'section[aria-label="Rules from it"]:has-text("rl_")',
    title: t('A rule from a problem'),
    text: t('Create rule opens a form under the problem. Write the rule and save it; the rule and the problem are linked.'),
    captions: [
      { voice: 'sell', title: 'Turn a lesson into a rule', text: 'Write the rule beside the problem it came from. The two stay linked on both pages.' },
      { voice: 'story', title: 'Press Create rule', text: 'You press Create rule under Rules from it and type the rule. After Save, the rule appears on Rules, linked to this problem.' },
      { voice: 'tech', title: 'One request, two linked records', text: 'Create rule posts to /api/problems/{id}/rule as the operator; agents are refused. The rule goes to rules.csv with related_incident set to the problem id.' },
    ],
    zoom: 'push',
    hold: 4.5,
  }),
  B({
    id: 'skills-page',
    chapter: CH.keep,
    page: '/skills',
    title: t('What a skill is'),
    text: t('A skill is a folder with a SKILL.md that an agent loads when the task fits. Type #skill in a chat to make one.'),
    captions: [
      { voice: 'sell', title: 'Do it once, reuse it', text: 'Work done well in one chat becomes a procedure any agent loads when the same task comes up again.' },
      { voice: 'story', title: 'Type #skill after the work', text: 'You finish a piece of work and type #skill. The agent writes the steps as SKILL.md, and the skill appears here as a draft.' },
      { voice: 'tech', title: 'SKILL.md through skill_draft', text: 'The hook keeps the #skill message. The agent sends the whole SKILL.md and its files with the MCP tool skill_draft; each version goes to kept_versions/.' },
    ],
    zoom: 'full',
    hold: 4.5,
  }),
  B({
    id: 'skills-list',
    chapter: CH.keep,
    page: '/skills',
    selector: 'nav[aria-label="Skills"]',
    title: t('Drafts, active, archived'),
    text: t('A new skill starts as a draft. Read it, then make it active. The row shows how often it was used in the last 30 days.'),
    captions: [
      { voice: 'sell', title: 'Read it before agents use it', text: 'A new skill starts as a draft. It reaches agents after you read it and make it active.' },
      { voice: 'story', title: 'Read the draft, make it active', text: 'You open a draft and read SKILL.md. You press Make active, and the skill moves to Active.' },
      { voice: 'tech', title: 'A status per skill', text: 'Make active posts the status to /api/skills/{id}/update. The count on each row comes from /api/skills/usage over the last 30 days.' },
    ],
    zoom: 'push',
    hold: 4.5,
  }),
  B({
    id: 'skills-projects',
    chapter: CH.keep,
    page: '/skills',
    selector: 'section[aria-label="Projects"]',
    // Install into the example project of the tour's own world; never All
    // projects, which writes into the folders of this machine's agents.
    action: {
      kind: 'click',
      selector: 'section[aria-label="Projects"] tr:has-text("shopfront") >> text="Install"',
      focus: 'section[aria-label="Projects"]',
      frames: 5,
      interval: 200,
    },
    title: t('Where a skill is installed'),
    text: t('Install puts the skill in one project. All projects puts it where every agent reads it.'),
    captions: [
      { voice: 'sell', title: 'Install it where you need it', text: 'One project or every agent on this machine: the skill goes where you choose, with a preview first.' },
      { voice: 'story', title: 'Press Install', text: 'You press Install on a project row. The preview names the folders, and after you confirm, the row shows Installed.' },
      { voice: 'tech', title: 'Two folders per install', text: 'Install copies the skill to .claude/skills/ and .agents/skills/ in the project, or in your home folder for All projects. A marker file tags each copy.' },
    ],
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'skills-copies',
    chapter: CH.keep,
    page: '/skills',
    selector: 'section[aria-label="Projects"]',
    // The tour's world has nothing installed: the rows show where each copy
    // stands, and the words name the other states rather than show them.
    title: t('The copies in each project'),
    text: t('Each project row shows the state of its copy. After Install the row says Installed, later Older copy or Changed on disk.'),
    captions: [
      { voice: 'sell', title: 'Know where each copy stands', text: 'Every project row tells you whether its copy is current, older than the latest version, or edited by hand on disk.' },
      { voice: 'story', title: 'Read the project rows', text: 'You open a skill and look under Projects. Each row names the state of its copy, and the button beside it fits: Install, Update or Overwrite.' },
      { voice: 'tech', title: 'Hashes in a marker file', text: 'Each copy carries .sp-skill.json with a hash. A different hash on disk shows Changed on disk; an older version\'s hash shows Older copy.' },
    ],
    zoom: 'push',
    hold: 5,
  }),
  B({
    id: 'skills-used',
    chapter: CH.keep,
    page: '/skills',
    selector: 'section[aria-label="Used"]',
    title: t('Uses'),
    text: t('Slightly Parallel counts each time a Claude Code agent used the skill: when, in which project, by which agent and in which turn.'),
    captions: [
      { voice: 'sell', title: 'See which skills agents use', text: 'Each use is counted and listed, so you keep the skills that are used and archive the rest.' },
      { voice: 'story', title: 'Open Used', text: 'You open a skill and scroll to Used. Each row shows when, the project, the agent, the turn, and whether you typed it or the agent chose it.' },
      { voice: 'tech', title: 'Read from the transcript', text: 'The Claude Code hook finds Skill tool calls and typed slash commands in the transcript. It appends each use to skills.jsonl beside the chat.' },
    ],
    // The list opens on a draft nobody has run; make-a-scan has uses. Picked
    // by a click, not by the hash: the live tour keeps the skill you had open.
    action: {
      kind: 'click',
      selector: 'text="make-a-scan"',
      focus: 'section[aria-label="Used"]',
      frames: 4,
      interval: 200,
    },
    zoom: 'push',
    hold: 4.5,
  }),
  // ---- The home page ----
  B({
    id: 'home-needs-you',
    chapter: CH.what,
    page: '/',
    // The list runs past the fold; its second row is a task in Review,
    // with both buttons, wholly on screen.
    selector: 'section[aria-label="Needs you"] li:nth-child(2)',
    title: t('Needs you'),
    text: t('Needs you lists the serious open problems and the tasks in Review. Accept moves a task to Done; Send back returns it to Doing.'),
    captions: [
      { voice: 'sell', title: 'Everything that waits for you', text: 'Tasks to review and serious problems are listed on the home page, each with the buttons to act on it.' },
      { voice: 'story', title: 'Accept a task', text: 'You read a task in Review and press Accept. A toast says Accepted, and the task moves to Done.' },
      { voice: 'tech', title: 'One status update', text: 'Accept and Send back post status done or doing to /api/tasks/{id}/update. The server appends the change to task_events.csv.' },
    ],
    zoom: 'push',
    hold: 5.5,
  }),
  B({
    id: 'home-start',
    chapter: CH.loop,
    page: '/',
    title: t('Start an agent'),
    text: t('Type what an agent should do and press Start an agent. The task goes into Doing and a terminal opens with an agent working on it.'),
    captions: [
      { voice: 'sell', title: 'One sentence starts an agent', text: 'Describe the work in one line, and an agent starts on it with the task already on the board.' },
      { voice: 'story', title: 'Type the task, press Start', text: 'You type Add a size guide to the product page and press Start an agent. A terminal opens, and the card appears in Doing.' },
      { voice: 'tech', title: 'A task, then a terminal', text: 'The page posts the task to /api/tasks with status doing. A terminal session then runs claude, codex or opencode with the task id in the prompt.' },
    ],
    // Typed, never sent: the film shows the words in the box.
    action: {
      kind: 'type',
      selector: 'input[aria-label="Start an agent on a task"]',
      text: 'Add a size guide to the product page',
      frames: 4,
      interval: 220,
    },
    // On the box: the rest of the page is today, still empty until the
    // first chat of the day.
    zoom: 'push',
    hold: 5.5,
  }),
  B({
    id: 'about',
    chapter: CH.what,
    page: '/about',
    title: t('About'),
    text: t('Slightly Parallel runs on your computer, for one person and their agents. A hook records every chat, agents write entries through their tools, and you read the pages.'),
    captions: [
      { voice: 'sell', title: 'Your agents\' work, on your machine', text: 'Everything is stored as files on your computer, for you and the agents you run.' },
      { voice: 'story', title: 'Open About', text: 'You click the mark at the top of the sidebar. About describes the product and links to Guide, Setup and Internals.' },
      { voice: 'tech', title: 'CSV, Markdown and DuckDB', text: 'Records are CSV rows with Markdown text in one data folder. The server builds DuckDB views from them in process; the About page itself is static.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'guide',
    chapter: CH.what,
    page: '/guide',
    title: t('The guide'),
    text: t('The guide explains every page and every command in plain words. Take the tour plays a tour like this one over the live pages.'),
    captions: [
      { voice: 'sell', title: 'Every page explained', text: 'Read what each page is for and what each command does, then take a tour across the live pages.' },
      { voice: 'story', title: 'Press Take the tour', text: 'You open Guide and press Take the tour. The first tour walks the pages and points at one example on each.' },
      { voice: 'tech', title: 'Written from the page list', text: 'The page texts come from features/guide/pages.ts and the commands from the lens config. Take the tour plays the first preset over the live routes.' },
    ],
    zoom: 'full',
    hold: 5,
  }),

  // ---- Agents ----
  B({
    id: 'project-overview',
    chapter: CH.agents,
    page: '/project/{project}',
    title: t('The project page'),
    text: t('The project page opens on its numbers and the agent timeline: one row per chat, marked where it named a task.'),
    captions: [
      { voice: 'sell', title: 'One project, one page', text: 'See the project\'s numbers and every chat on a timeline, with the tasks each one worked on.' },
      { voice: 'story', title: 'Open a project', text: 'You click shopfront. The page opens on its tiles and the agent timeline, and each lane shows the tasks that chat named.' },
      { voice: 'tech', title: 'Task ids found in chat turns', text: 'The page reads /api/project/{code}. Lane marks come from /api/tasks/mentions/by-agent: every task id the hook saw in a chat.md turn.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'project-agents',
    chapter: CH.agents,
    page: '/project/{project}#agents',
    title: t('The project\'s agents'),
    text: t('One card per agent: its time, turns, lines changed and tasks. Copy resume command reopens the chat in its folder.'),
    captions: [
      { voice: 'sell', title: 'Pick up any chat again', text: 'Each agent\'s card shows its work, and one copied command reopens the chat in its folder.' },
      { voice: 'story', title: 'Copy the resume command', text: 'You find the agent\'s card and press Copy resume command. You paste it into a terminal, and the chat continues.' },
      { voice: 'tech', title: 'Profiles from scans and turns', text: 'The cards read /api/agents/profiles. Lines are summed from the agent\'s scans; the command is claude -r, codex resume or opencode --session.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'agents-page',
    chapter: CH.agents,
    page: '/agent',
    title: t('Agents'),
    text: t('Every agent, grouped by project, starred ones first. Click a card to open the agent.'),
    captions: [
      { voice: 'sell', title: 'Every agent, across projects', text: 'Find any chat from any project in one place, with the ones you starred on top.' },
      { voice: 'story', title: 'Find an agent', text: 'You type a name in Find an agent. The cards narrow to the match, and you click one to open it.' },
      { voice: 'tech', title: 'One profile request per project', text: 'The page calls /api/agents/profiles once for each project and groups the cards by project. Stars come from /api/marks.' },
    ],
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'agent-overview',
    chapter: CH.agents,
    page: '/agent/cc-4b1e9c07',
    nav: 'nav a[href="/agent"], aside a[href="/agent"]',
    title: t('The agent page'),
    text: t('The work of one chat: time, turns, lines, tasks and entries, and the chat it continued.'),
    captions: [
      { voice: 'sell', title: 'One chat\'s work, measured', text: 'Time, turns, lines, tasks and decisions of a single agent show what one chat delivered.' },
      { voice: 'story', title: 'Open an agent', text: 'You click an agent card. The overview shows its time, turns and lines; the arrows open the previous and next agent of the project.' },
      { voice: 'tech', title: 'One profile endpoint', text: 'The page reads /api/agents/{agent_id}/profile, built from the chat\'s meta.json and its entries. The open section is kept in the URL hash.' },
    ],
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'agent-chat',
    chapter: CH.agents,
    page: '/agent/cc-4b1e9c07#sec=chats',
    nav: 'nav a[href="/agent"], aside a[href="/agent"]',
    title: t('The chat'),
    text: t('Every message and reply is kept, with the files changed and the commits made in each turn.'),
    captions: [
      { voice: 'sell', title: 'Reread any conversation', text: 'Every message and reply is kept with the files and commits of that turn, so you see what was said and what it changed.' },
      { voice: 'story', title: 'Read the chat', text: 'You click chats in the agent\'s rail. The turns appear in order, each with the commits and files of that turn.' },
      { voice: 'tech', title: 'chat.md joined with work.jsonl', text: '/api/sessions/turns reads the verbatim turns from chat.md and joins each with its line in work.jsonl: commits, diff and files touched.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),

  // ---- The board, inside a card ----
  B({
    id: 'task-open',
    chapter: CH.board,
    page: '/project/{project}#tasks',
    title: t('The task window'),
    text: t('Click a card to open the task. Here you set its status, priority, due date, milestone, sprint and links.'),
    captions: [
      { voice: 'sell', title: 'Everything about a task, one window', text: 'Status, priority, dates, sprint, links and history are in the task window, one click from the card.' },
      { voice: 'story', title: 'Click a card', text: 'You click Refunds from the admin order page. The task window opens; you change the priority and press Save.' },
      { voice: 'tech', title: 'tasks.csv and task_events.csv', text: 'The window reads /api/tasks/{id} and saves through /api/tasks/{id}/update. Each changed field is appended to task_events.csv.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label^="Edit task: Refunds from the admin order page"]',
      focus: '[role="dialog"]',
      frames: 5,
      interval: 160,
    },
    zoom: 'full',
    hold: 6,
  }),
  B({
    id: 'task-turns',
    chapter: CH.board,
    page: '/project/{project}#tasks',
    title: t('Turns'),
    text: t('Press next turn to ask for the next step on the same task. The earlier request stays below, and the copy for the agent carries the turn number.'),
    captions: [
      { voice: 'sell', title: 'Every request on a task, kept', text: 'Ask for the next step on the same task, and every earlier request stays readable below it.' },
      { voice: 'story', title: 'Press next turn', text: 'You press + next turn and write the next step. After Save, the copy for the agent carries the task id with the turn number.' },
      { voice: 'tech', title: 'A turn appended to the task', text: 'Save posts to /api/tasks/{id}/turn. The server appends a Turn N heading to the task\'s Markdown and logs a turn event in task_events.csv.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label^="Edit task: Refunds from the admin order page"]',
      focus: '#task-desc',
      frames: 5,
      interval: 160,
    },
    zoom: 'push',
    hold: 6.5,
  }),
  B({
    id: 'board-sprint',
    chapter: CH.board,
    page: '/project/{project}#tasks',
    title: t('The sprint chip'),
    text: t('Each running sprint has a chip above the board with its tasks done, days left and hours. Click it to see only the cards of that sprint.'),
    captions: [
      { voice: 'sell', title: 'One sprint, in focus', text: 'Click a sprint to see its cards alone, with the days left and the hours used beside its name.' },
      { voice: 'story', title: 'Click the sprint chip', text: 'You click Payments hardening above the board. The board shows that sprint\'s cards; you click the chip again to see all.' },
      { voice: 'tech', title: 'Active sprints from sprints.csv', text: '/api/sprints/board returns the active rows of sprints.csv. Days left are bet_days minus the days since the start; hours come from timer entries.' },
    ],
    action: {
      kind: 'click',
      selector: 'button:has-text("Payments hardening")',
      // The filter is remembered: click the chip again for the beats after.
      after: 'button:has-text("Payments hardening")',
      frames: 5,
      interval: 180,
    },
    zoom: 'full',
    hold: 6,
  }),

  // ---- Plans and time ----
  B({
    id: 'calendar-month',
    chapter: CH.time,
    page: '/project/{project}#calendar',
    title: t('The calendar'),
    text: t('The month shows due dates, planned days, finished tasks and entries. Drag an undated task onto a day to give it a due date.'),
    captions: [
      { voice: 'sell', title: 'Plan by dragging onto a day', text: 'See due dates and finished work on one month, and give a task its date by dropping it on a day.' },
      { voice: 'story', title: 'Drag a task onto a day', text: 'You open undated and drag a task onto a Friday. A toast says Due with the date, and the task appears on that day.' },
      { voice: 'tech', title: 'One calendar request', text: '/api/calendar returns tasks, entries, milestones and the facts per day. A drop posts due_date in YYMM-DD to /api/tasks/{id}/update.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'calendar-week',
    chapter: CH.time,
    // A full week of the example month, not the current one.
    page: '/project/{project}#calendar&{weeks-ago:1}',
    title: t('The week view'),
    text: t('Each day is a column. The panel on the right lists the tasks of the chosen day and the work done on it.'),
    captions: [
      { voice: 'sell', title: 'Your week, day by day', text: 'Each day has its own column with its tasks and the work done, so the week fits in one view.' },
      { voice: 'story', title: 'Switch to week', text: 'You click week and pick a day. The panel on the right lists its tasks and the chats and commits of that day.' },
      { voice: 'tech', title: 'Facts per day', text: 'Week reads the same /api/calendar answer. The work of each day is counted from sessions, turns, commits, lines and hours.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="View"] >> text="week"',
      after: '[aria-label="View"] >> text="month"',
      frames: 4,
      interval: 200,
    },
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'milestones',
    chapter: CH.time,
    page: '/project/{project}#calendar',
    title: t('Milestones'),
    text: t('A milestone names an outcome and when it counts as done. Its tasks sit under it, and the bar shows how many are finished.'),
    captions: [
      { voice: 'sell', title: 'How close the next outcome is', text: 'Each milestone shows its target date, its tasks and how many of them are done.' },
      { voice: 'story', title: 'Mark a milestone reached', text: 'You open the current milestone and check its tasks. You press Reached, add the proof, and the bar turns green.' },
      { voice: 'tech', title: 'milestones.csv and a link table', text: 'Milestones are rows in milestones.csv; milestone_tasks.csv links each task to one milestone. The page reads /api/milestones.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="View"] >> text="milestones"',
      after: '[aria-label="View"] >> text="month"',
      frames: 4,
      interval: 200,
    },
    zoom: 'full',
    hold: 6,
  }),
  B({
    id: 'project-sprints',
    chapter: CH.time,
    page: '/project/{project}#sprints',
    title: t('The runway'),
    text: t('Each sprint is a bar of planned days. The fill is the days spent; each tick is a task, green when it is done.'),
    captions: [
      { voice: 'sell', title: 'See which sprint runs late', text: 'Each sprint\'s bar shows the days spent against the days planned, with its tasks as ticks.' },
      { voice: 'story', title: 'Click a tick', text: 'You read a sprint\'s runway and click a tick. The task opens; the green ticks are the tasks done.' },
      { voice: 'tech', title: 'Runway from /api/sprints/board', text: 'The runway reads the active sprints from /api/sprints/board. The bar is bet_days long, and the fill is the days since started_date.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'sprint-blocks',
    chapter: CH.time,
    page: '/project/{project}#sprints',
    title: t('Blocks'),
    text: t('Blocks lists the tasks of each sprint by status, with the backlog beside it.'),
    captions: [
      { voice: 'sell', title: 'Move work between sprints', text: 'Each sprint\'s tasks are listed by status, with the backlog beside them, ready to drag.' },
      { voice: 'story', title: 'Drag a task into a sprint', text: 'You switch to blocks and drag a task from the backlog into a sprint. The task joins that sprint\'s list.' },
      { voice: 'tech', title: 'sprint_id on the task', text: 'A drag posts sprint_id to /api/tasks/{id}/update. The change goes to tasks.csv, and one event to task_events.csv.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="Sprints view"] >> text="blocks"',
      after: '[aria-label="Sprints view"] >> text="runway"',
      frames: 4,
      interval: 200,
    },
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'sprints-progress',
    chapter: CH.time,
    page: '/sprints',
    title: t('Progress'),
    text: t('Progress shows each sprint per day: tasks by status, your hours and agent hours, and the tasks planned for today.'),
    captions: [
      { voice: 'sell', title: 'Progress you can count', text: 'Each day shows the tasks by status, your hours and the agents\' hours, so slow days stand out.' },
      { voice: 'story', title: 'Switch to progress', text: 'You click progress and pick 30 days. Each day shows its task changes and hours, and today\'s planned tasks are listed.' },
      { voice: 'tech', title: 'One deck request', text: '/api/sprints/deck returns every active sprint with its timers, tasks and events. A task is planned for today when its today_on is today.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="Sprints view"] >> text="progress"',
      after: '[aria-label="Sprints view"] >> text="running"',
      frames: 4,
      interval: 200,
    },
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'timer-project',
    chapter: CH.time,
    page: '/project/{project}#tools',
    title: t('The timer'),
    text: t('Clock in on a block of work. The dial shows today, the grid shows the last six months, and the list shows when you worked and on what.'),
    captions: [
      { voice: 'sell', title: 'Your own hours, beside the agents\'', text: 'Clock in on a block of work and see your time by day and over six months.' },
      { voice: 'story', title: 'Clock in', text: 'You click a block tile to clock in. The dial counts today\'s time; you click again to clock out, and the entry appears below.' },
      { voice: 'tech', title: 'time_entries.csv', text: 'Clock in posts to /api/time/start and appends a row to time_entries.csv. A running timer is a row with an empty ended_at.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'timer-page',
    chapter: CH.time,
    page: '/time',
    title: t('The Timer page'),
    text: t('Your hours per block for each of the last 7 days, with a 30- or 90-day total. Start a block from its row.'),
    captions: [
      { voice: 'sell', title: 'All your hours, one table', text: 'See where your time went across every project, block by block, for the last week.' },
      { voice: 'story', title: 'Start a block', text: 'You open Timer and press start on a block\'s row. The timer runs, and today\'s column for that block grows.' },
      { voice: 'tech', title: 'Entries from time_entries.csv', text: 'The page reads every entry from /api/time-entries and groups them by project and block. Start and stop post to /api/time/start and /api/time/{id}/stop.' },
    ],
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'stats',
    chapter: CH.time,
    page: '/stats',
    title: t('Statistics'),
    text: t('Every finished task with its messages, chat time, commits and files, and the time from the first message to done.'),
    captions: [
      { voice: 'sell', title: 'Know how long a task takes', text: 'Each finished task shows its messages, chat time, commits and files, so the next estimate starts from data.' },
      { voice: 'story', title: 'Open Statistics', text: 'You open Statistics and choose 90 days. Each finished task lists its messages, chat time and commits; you click one to open it.' },
      { voice: 'tech', title: 'Counted over the chat stretch', text: '/api/stats/tasks counts each task\'s stretch of the chat. A task closed with #done has an exact stretch; the others are estimated from where it was named.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),

  // ---- Decisions, architecture, files ----
  B({
    id: 'project-decisions',
    chapter: CH.adds,
    page: '/project/{project}#decisions',
    title: t('The decision log'),
    text: t('Every decision of the project in one list. Search it, or filter it by agent and by date.'),
    captions: [
      { voice: 'sell', title: 'Every choice, searchable', text: 'One list holds every decision of the project, so the reason for any choice is a search away.' },
      { voice: 'story', title: 'Filter by an agent', text: 'You pick an agent in the filter. The list keeps that agent\'s decisions, newest first.' },
      { voice: 'tech', title: 'One query, filtered in the browser', text: 'The tab reads decisions from /api/project/{code}, a DuckDB query over decisions.csv. Search and filters run in the browser.' },
    ],
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'architecture-map',
    chapter: CH.adds,
    page: '/project/{project}#architecture',
    title: t('The map'),
    text: t('Map lists every part of the program as a row: runtimes, frameworks, libraries, entry points, pages and interfaces, each with its file.'),
    captions: [
      { voice: 'sell', title: 'A map of the program', text: 'Every part of the code is a row with its file, so a new reader finds the entry points and the connections at once.' },
      { voice: 'story', title: 'Switch to map', text: 'You click map. The table lists each part with its kind, name and file; What connects to what shows the links between them.' },
      { voice: 'tech', title: 'map/vNNN.json through map_write', text: 'A helper agent calls map_material, then map_write. The server saves projects/<code>/map/vNNN.json and lists rows whose path is missing under To fix.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="Architecture mode"] >> text="map"',
      after: '[aria-label="Architecture mode"] >> text="page"',
      frames: 4,
      interval: 200,
    },
    zoom: 'full',
    hold: 6,
  }),
  B({
    id: 'files-ranking',
    chapter: CH.adds,
    page: '/project/{project}#files',
    title: t('Ranking'),
    text: t('Ranking orders the files by recent work, churn or importance, with the last line the agent wrote about each one.'),
    captions: [
      { voice: 'sell', title: 'The files that matter, first', text: 'Order the files by recent work, churn or importance, and read the agent\'s last note on each.' },
      { voice: 'story', title: 'Switch to ranking', text: 'You click ranking and pick an order. The list reorders, and each row shows what the agent wrote last about that file.' },
      { voice: 'tech', title: 'Ordered in the browser', text: 'Ranking uses the same /api/files/heatmap answer as the grid. The orders are computed in the browser; the note is the newest why written for the path.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="File view"] >> text="ranking"',
      after: '[aria-label="File view"] >> text="grid"',
      frames: 4,
      interval: 200,
    },
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'files-story',
    chapter: CH.adds,
    page: '/project/{project}#files',
    title: t('Story'),
    text: t('Story shows each file with its latest notes from the agent, newest first.'),
    captions: [
      { voice: 'sell', title: 'Each file\'s history, in words', text: 'Read why a file changed, scan after scan, in the agent\'s own words.' },
      { voice: 'story', title: 'Switch to story', text: 'You click story. Each file becomes a card with its latest notes, newest first, and the earlier ones folded below.' },
      { voice: 'tech', title: 'Notes from file_details/', text: 'Each note is the why an agent wrote for that path in a file entry, kept in file_details/. The card shows the newest four.' },
    ],
    action: {
      kind: 'click',
      selector: '[aria-label="File view"] >> text="story"',
      after: '[aria-label="File view"] >> text="grid"',
      frames: 4,
      interval: 200,
    },
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'scans-page',
    chapter: CH.adds,
    page: '/scans#project={project}',
    title: t('The Scans page'),
    text: t('Each scan says what changed and why, with its files and its changes to the architecture. The calendar marks the days with a scan.'),
    captions: [
      { voice: 'sell', title: 'Every checkpoint, day by day', text: 'Each scan says what changed and why, with its files and its architecture changes, so a week reads in minutes.' },
      { voice: 'story', title: 'Read a day of scans', text: 'You open Scans and pick a day. Each scan shows why and what changed; you open Files or Changes for the detail.' },
      { voice: 'tech', title: 'One request for the page', text: '/api/scans/page returns every scan with its text, its file entry and its architecture rows. Scans are kept in scans.csv and snapshots/.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),

  // ---- Search and history ----
  B({
    id: 'search-words',
    chapter: CH.find,
    page: '/search',
    title: t('Before you search'),
    text: t('The page counts what the records hold: the words used most, the kinds of entries and the chats with the most turns.'),
    captions: [
      { voice: 'sell', title: 'See what your records hold', text: 'Before a search, the page shows the words, kinds and chats that fill your records.' },
      { voice: 'story', title: 'Click a word', text: 'You open Search with an empty box. You click a word in the Words list, and the page searches for it.' },
      { voice: 'tech', title: 'Counted when the index is built', text: '/api/search/overview returns counts computed once when the index is built. Common English words and numbers are left out of the Words list.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'project-chats',
    chapter: CH.find,
    page: '/project/{project}#activity',
    title: t('Chats'),
    text: t('Pick a day on the calendar or a chat in the list. The chat opens on the right, and the counts show what the chats produced.'),
    captions: [
      { voice: 'sell', title: 'Every chat of the project', text: 'Find any conversation by day or by agent, and see what each one produced.' },
      { voice: 'story', title: 'Pick a day', text: 'You click a day on the month grid. The chats of that day are listed, and the one you pick opens on the right.' },
      { voice: 'tech', title: 'Sessions from chat.md', text: 'The tab reads /api/sessions. Each row carries what the chat produced, its tasks and its marks; the agent filter runs in the browser.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'chats-find',
    chapter: CH.find,
    page: '/chats',
    title: t('Find in chats'),
    text: t('Type a word in Find in chats. The list keeps the chats that mention it.'),
    captions: [
      { voice: 'sell', title: 'Find the chat that said it', text: 'Type a word and keep only the chats that mention it, across every agent.' },
      { voice: 'story', title: 'Type refund', text: 'You type refund in Find in chats. The list narrows to the chats that mention it, each with its count of matches.' },
      { voice: 'tech', title: 'A match in every turn', text: 'The word goes to /api/sessions as q. The server matches it in every turn, ignoring case, and returns a count of matches per chat.' },
    ],
    action: {
      kind: 'type',
      selector: 'input[aria-label="Find in chats"]',
      text: 'refund',
      frames: 5,
      interval: 300,
    },
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'important',
    chapter: CH.find,
    page: '/important',
    title: t('Important'),
    text: t('Star a message, an agent or a task. Important keeps them together, with the project and the time.'),
    captions: [
      { voice: 'sell', title: 'What matters, on one page', text: 'Messages, agents and tasks you starred are in one list, each with its project and when you marked it.' },
      { voice: 'story', title: 'Type #important in a chat', text: 'You add #important to a message. The message, its agent and the task it names appear on Important.' },
      { voice: 'tech', title: 'marks.csv from the chat log', text: 'The server finds #important in your messages and copies each mark into marks.csv. A task\'s star is the remember field in tasks.csv.' },
    ],
    // The page's few rows sit at the top: words go below them.
    place: 'bottom',
    zoom: 'full',
    hold: 4.5,
  }),
  B({
    id: 'prompts',
    chapter: CH.keep,
    page: '/prompts',
    title: t('Prompts'),
    text: t('Type #prompt in a message to keep it. Each prompt keeps its versions, its sends and what its chats changed. Copy it into the next chat.'),
    captions: [
      { voice: 'sell', title: 'Your best prompts, ready to reuse', text: 'The prompts you rely on are kept with their versions and what they produced, one copy away.' },
      { voice: 'story', title: 'Type #prompt in a message', text: 'You add #prompt to a message you will send again. It appears in the table; you click the row to compare versions and copy it.' },
      { voice: 'tech', title: 'Harvested from the chat logs', text: 'The hook matches #prompt, and the server reads the message from chat.md into prompts.csv. Repeats are found by a fingerprint of the normalised text.' },
    ],
    // The page's few rows sit at the top: words go below them.
    place: 'bottom',
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'artifacts',
    chapter: CH.keep,
    page: '/artifacts',
    title: t('Artifacts'),
    text: t('Type #artifact and the agent keeps a result as a folder: a dataset, a document or a page. Each one shows its files and your words.'),
    captions: [
      { voice: 'sell', title: 'Results in one place', text: 'Datasets, documents, pages and apps an agent made for you are on one page, each with your request beside it.' },
      { voice: 'story', title: 'Ask with #artifact', text: 'You ask for a result with #artifact. The agent writes the folder, and it appears under its kind with your words.' },
      { voice: 'tech', title: 'A folder and artifact_write', text: 'The agent writes projects/<project>/artifacts/<name>/ with ARTIFACT.md, then calls the MCP tool artifact_write. The record goes to artifacts.csv.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),

  // ---- Setup, step by step ----
  B({
    id: 'setup-folders',
    chapter: CH.setup,
    page: '/setup',
    selector: 'section:has-text("Choose where Slightly Parallel keeps its records")',
    title: t('Where the records are kept'),
    text: t('Setup shows the app folder, the contract and the data folder. The data folder holds the example project; pick another folder to keep the records elsewhere.'),
    captions: [
      { voice: 'sell', title: 'One folder for everything', text: 'Every record lives in one folder you choose. Move it, back it up or open it in a file manager.' },
      { voice: 'story', title: 'Pick the data folder', text: 'You open Setup. The first card names the folders; you keep the default and go on to the projects.' },
      { voice: 'tech', title: 'data_root in settings', text: 'GET /api/setup/info returns app_root, data_root and whether the contract file exists. The data folder is set once and kept in .env.' },
    ],
    zoom: 'focus',
    hold: 6,
  }),
  B({
    id: 'setup-integrate',
    chapter: CH.setup,
    page: '/setup',
    selector: 'section:has-text("Integrate your projects")',
    title: t('Integrating a project'),
    text: t('Enter the project\'s code, its folder and a note, then press Integrate. Preview shows what will be written before anything is.'),
    captions: [
      { voice: 'sell', title: 'One form per project', text: 'A code, a folder, one click. Preview shows every file Setup will write before it writes one.' },
      { voice: 'story', title: 'Fill the form', text: 'You type the code and the folder, press Preview, read the list, then press Integrate.' },
      { voice: 'tech', title: 'POST /api/setup/integrate', text: 'The preview flag returns the files without writing. Integrate writes the AGENTS.md block, the hooks, .mcp.json and a row in integrations.csv.' },
    ],
    zoom: 'focus',
    hold: 6.5,
  }),
  B({
    id: 'setup-projects',
    chapter: CH.setup,
    page: '/setup',
    selector: 'h3:has-text("Integrated projects")',
    title: t('Integrated projects'),
    text: t('Each project row shows its hooks, git and whether the contract block is fresh. Re-integrate rewrites it; Disconnect stops the recording and keeps the data.'),
    captions: [
      { voice: 'sell', title: 'See what is recorded', text: 'Every integrated project in one list, with the state of its hooks and its contract block.' },
      { voice: 'story', title: 'Read the project rows', text: 'You check the row of the project: hooks present, git found, contract fresh. It is ready.' },
      { voice: 'tech', title: 'integrations.csv, checked live', text: 'The list comes from integrations.csv; for each row the server checks the hooks file, the git folder and the block hash in AGENTS.md.' },
    ],
    place: 'left',
    zoom: 'focus',
    hold: 6,
  }),
  B({
    id: 'setup-agent',
    chapter: CH.setup,
    page: '/setup',
    selector: 'section:has-text("Start an agent")',
    title: t('Starting an agent'),
    text: t('Open a new agent session in the integrated folder. Its first answer names the project and the agent id; from then on every message is recorded.'),
    captions: [
      { voice: 'sell', title: 'The agent runs as it is', text: 'Start the agent as usual in the project folder. The hooks do the rest, without spending tokens.' },
      { voice: 'story', title: 'Start Claude Code in the folder', text: 'You open a terminal in the project and start the agent. Its first answer carries the project code and the agent id.' },
      { voice: 'tech', title: 'The hook prints the identity', text: 'On the first turn the capture hook prints [slightly-parallel] project … · agent_id …; the MCP server reads the same breadcrumb to stamp writes.' },
    ],
    zoom: 'focus',
    hold: 6.5,
  }),
  B({
    id: 'setup-running',
    chapter: CH.setup,
    page: '/setup',
    selector: 'section:has-text("Optional: keep it running")',
    title: t('Keeping it running'),
    text: t('sp.sh up runs the servers in the background; status, logs and down are the other commands. State and the log live in the .sp folder.'),
    captions: [
      { voice: 'sell', title: 'Runs in the background', text: 'One command starts it, one stops it, one shows the log. It keeps running after the terminal closes.' },
      { voice: 'story', title: 'Run sp.sh up', text: 'You copy sp.sh up from the card and run it. The app answers on port 8123 until you run sp.sh down.' },
      { voice: 'tech', title: 'A supervisor in .sp/', text: 'sp.py runs a supervisor that restarts the backend and the frontend; its pid, state and log are files in .sp/, ignored by git.' },
    ],
    zoom: 'focus',
    hold: 6,
  }),

  // ---- Care: the server's own pages ----
  B({
    id: 'health',
    chapter: CH.setup,
    page: '/health',
    title: t('Health'),
    text: t('Server status, slow requests and the log on one page. Copy for AI puts the whole page on the clipboard for an agent to read.'),
    captions: [
      { voice: 'sell', title: 'When something is wrong', text: 'Status, slow requests, errors and the log on one page, with a copy button an agent can read from.' },
      { voice: 'story', title: 'Open Health', text: 'You open Health after a slow morning. The request table names the costliest path; you copy the page for an agent.' },
      { voice: 'tech', title: 'GET /api/health/status', text: 'The page reads the server log and the request timings kept in memory: p50 and max per path, errors and warnings counted.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'internals',
    chapter: CH.setup,
    page: '/internals',
    title: t('Internals'),
    text: t('How capture works, what triggers an entry, what can break, and a check of the data files.'),
    captions: [
      { voice: 'sell', title: 'How it works, inside', text: 'Four tabs explain the recording, the triggers, what can break and whether the data files are sound.' },
      { voice: 'story', title: 'Read the capture tab', text: 'You open Internals to see which tools are recorded and how. The badges name each adapter and its state.' },
      { voice: 'tech', title: 'Doctor over the data root', text: 'The data check runs scripts/doctor.py logic over every CSV and detail folder and lists what it would repair.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'backups',
    chapter: CH.setup,
    page: '/backups',
    title: t('Backups'),
    text: t('Copies of the data folder as .tar.gz files beside it. Back up now makes one; Restore replaces the current data with a copy.'),
    captions: [
      { voice: 'sell', title: 'A copy in one click', text: 'Back up the whole data folder from the page, verify a copy, restore it when needed.' },
      { voice: 'story', title: 'Press Back up now', text: 'You press Back up now before a risky change. The new copy appears in the list with its size and a verify button.' },
      { voice: 'tech', title: 'backup.py behind the page', text: 'POST /api/backups runs scripts/backup.py: a tar.gz of the data root, a checksum and a manifest; restore unpacks it beside the live folder first.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),
  B({
    id: 'monitor',
    chapter: CH.setup,
    page: '/monitor',
    title: t('Monitor'),
    text: t('CPU, memory, disk, network and the connection, sampled in the background. Unusual readings are kept as events.'),
    captions: [
      { voice: 'sell', title: 'The machine, watched', text: 'See when the laptop was busy, out of memory or offline, next to what the agents were doing.' },
      { voice: 'story', title: 'Open Monitor', text: 'You open Monitor after an agent stalled. The memory line shows the hour it ran out, and the event is listed below.' },
      { voice: 'tech', title: 'A sampler thread', text: 'The backend samples psutil every few seconds, keeps a ring of readings and writes an event when a reading crosses a threshold.' },
    ],
    zoom: 'full',
    hold: 5.5,
  }),

  // ---- Setup and settings ----
  B({
    id: 'settings',
    chapter: CH.setup,
    page: '/settings',
    title: t('Settings'),
    text: t('Choose the language, the reminders agents get in a chat, and the tab a project opens on.'),
    captions: [
      { voice: 'sell', title: 'Set how agents are reminded', text: 'Choose which notices agents get in a chat and how the dashboard opens, all on one page.' },
      { voice: 'story', title: 'Change a setting', text: 'You change Project page opens on and press Save. The next project you open starts on that tab.' },
      { voice: 'tech', title: 'settings.json in the data folder', text: 'POST /api/settings saves the values to settings.json. The capture hook reads its agent settings on each turn to decide which notices to print.' },
    ],
    zoom: 'full',
    hold: 5,
  }),
  B({
    id: 'appearance',
    chapter: CH.setup,
    page: '/settings/appearance',
    // A settings page is reached from Settings in the sidebar.
    nav: 'nav a[href="/settings"], aside a[href="/settings"]',
    title: t('Appearance'),
    text: t('Pick a theme and an app skin. The whole dashboard changes at once.'),
    captions: [
      { voice: 'sell', title: 'Make it look your way', text: 'Pick light or dark, a skin and an accent, and the whole dashboard changes at once.' },
      { voice: 'story', title: 'Pick a theme', text: 'You click Dark under Theme. The page changes at once, and the choice is kept in every browser.' },
      { voice: 'tech', title: 'Data attributes and ui_prefs.json', text: 'The theme sets data-theme on the html element, and the skin sets data-skin. Choices are saved to ui_prefs.json through /api/prefs.' },
    ],
    zoom: 'full',
    hold: 4.5,
  }),
  B({
    id: 'sidebar-settings',
    chapter: CH.setup,
    page: '/settings/sidebar',
    title: t('The sidebar'),
    text: t('Drag pages between groups, hide the ones you seldom use, or add a group of your own.'),
    captions: [
      { voice: 'sell', title: 'A sidebar with your pages', text: 'Keep the pages you use in the order you want, and hide the rest.' },
      { voice: 'story', title: 'Drag a page', text: 'You drag a page into another group and click the eye on one you seldom use. The preview beside the list changes at once.' },
      { voice: 'tech', title: 'One layout string', text: 'The layout is saved under the pref key sp-sidebar-layout in ui_prefs.json, through /api/prefs. Dragging uses dnd-kit.' },
    ],
    zoom: 'full',
    hold: 4.5,
  }),

]

/* ------------------------------- presets ------------------------------ */

/**
 * The project every tour walks and the film is photographed on: the example
 * project (backend/example.py), in the user's own data. Its board, chats and
 * entries are the same on every install, apart from the dates.
 */
export const TOUR_PROJECT = 'shopfront'

const BASE: Omit<Script, 'id' | 'name' | 'note' | 'beats'> = {
  title: 'Slightly Parallel',
  subtitle: t('a dashboard for the coding agents in your repositories: what they did, why, and what is left'),
  endline: t('Runs on your computer · the data stays in plain CSV and Markdown files'),
  theme: 'midnight',
  aspect: '16:9',
  panel: 'card',
  project: TOUR_PROJECT,
  demo: TOUR_PROJECT,
  base: '',
  lead: 3,
  tail: 3.5,
}

function cut(ids: string[]): Beat[] {
  const by = new Map(LIBRARY.map((b) => [b.id, b]))
  const picked = ids.map((id) => {
    const b = by.get(id)
    // A preset that names a beat the library lost would quietly play shorter.
    if (!b) throw new Error(`tour preset names an unknown beat: ${id}`)
    return b
  })
  const rest = LIBRARY.filter((b) => !ids.includes(b.id)).map((b) => ({ ...b, on: false }))
  return [...picked.map((b) => ({ ...b, on: true })), ...rest]
}

/** The article sections the presets are filed under, in reading order. */
export const SECTIONS = {
  what: t('What it is'),
  first: t('First run'),
  board: t('The board'),
  loop: t('The agent loop'),
  arch: t('Decisions and architecture'),
  memory: t('Project memory'),
  time: t('Time'),
  find: t('Search and history'),
  agents: t('Agents'),
  setup: t('Setup and integrations'),
}

/** One story: its title card says its name, and under it the note. */
function story(id: string, section: string, name: string, note: string, ids: string[], over: Partial<Script> = {}): Script {
  return { ...BASE, id, section, name, note, title: name, subtitle: note, beats: cut(ids), ...over }
}

/**
 * The two films of the channel, then the studio's catalogue.
 *
 * The short film answers "what is this" in a minute and stops. The long
 * one walks every page in product order, from Setup to the server's own
 * pages, a chapter per section, so a viewer jumps to the part they need.
 * The rest are the stories the pages' own tours and the studio open on:
 * short ones of three to five beats, long ones of ten to twenty.
 */
const SHORT = ['overview', 'board', 'copy-task', 'evidence', 'scan-source', 'standup', 'decision-reasons']

const LONG = [
  'setup-folders', 'setup-integrate', 'setup-projects', 'setup-agent', 'setup-running',
  'overview', 'home-needs-you', 'home-start', 'capture', 'about', 'guide',
  'project-overview', 'project-agents', 'agents-page', 'agent-overview', 'agent-chat',
  'board', 'task-open', 'drag-card', 'swim-lanes', 'board-sprint',
  'copy-task', 'agent-column', 'evidence', 'contract', 'skills-install',
  'scan-source', 'scans-page', 'standup', 'decision-reasons', 'project-decisions',
  'architecture-page', 'architecture', 'architecture-map', 'files', 'files-ranking', 'files-story',
  'visions-page', 'visions-give', 'rules-page', 'rules-all', 'problems-page', 'problems-rule',
  'skills-page', 'skills-list', 'skills-projects', 'artifacts', 'prompts', 'important',
  'sprints', 'project-sprints', 'sprint-blocks', 'sprints-progress', 'calendar-month', 'calendar-week', 'milestones',
  'timer-project', 'timer-page', 'stats',
  'search', 'search-words', 'project-chats', 'chats-find', 'timelapse',
  'health', 'internals', 'backups', 'monitor', 'settings', 'appearance', 'sidebar-settings',
]

/** The presets the channel renders; the rest stay in the studio. */
export const CHANNEL = ['quick', 'full']

const CUTS: Script[] = [
  // ---- What it is ----
  // ---- The two films of the channel ----
  story('quick', SECTIONS.what, t('Slightly Parallel in a minute'), t('what it is: the agents\' day, the board, the proof, the records'), SHORT,
    { title: 'Slightly Parallel', subtitle: t('a dashboard for the coding agents in your repositories, in a minute'), tail: 6 }),
  story('full', SECTIONS.what, t('How Slightly Parallel works'), t('every page in product order, from Setup to the server\'s own pages'), LONG,
    { title: 'Slightly Parallel', subtitle: t('how it works: every page, from Setup to the server\'s own pages'), lead: 4 }),
  story('in-brief', SECTIONS.what, t('In brief'), t('the board, a scan and a decision, in half a minute'),
    ['overview', 'board', 'scan-source', 'decision-reasons']),
  story('the-idea', SECTIONS.what, t('The idea'), t('what the product is for, and where to read more'),
    ['about', 'overview', 'guide']),
  story('a-day', SECTIONS.what, t('A day with Slightly Parallel'), t('from the morning standup to the evening search'),
    ['overview', 'home-needs-you', 'standup', 'board', 'task-open', 'home-start', 'copy-task', 'agent-chat',
      'evidence', 'scan-source', 'decision-reasons', 'timer-project', 'sprints', 'search']),
  story('week-review', SECTIONS.what, t('The weekly review'), t('what the week produced, what it cost and what is next'),
    ['sprints-progress', 'stats', 'project-decisions', 'scans-page', 'files-ranking', 'architecture', 'timer-page',
      'milestones', 'important', 'timelapse']),

  // ---- First run ----
  story('first-run', SECTIONS.first, t('From Setup to the first page'), t('connect a project and see it fill'),
    ['setup', 'overview', 'project-overview', 'board']),
  story('first-chat', SECTIONS.first, t('The first recorded chat'), t('a chat is saved, read back and summed up'),
    ['setup', 'capture', 'agent-chat', 'scan-source']),
  story('help', SECTIONS.first, t('Help inside the app'), t('the guide, the page tours and the about page'),
    ['guide', 'visions-page', 'about']),
  story('first-week', SECTIONS.first, t('The first week'), t('a new project, step by step, until it explains itself'),
    ['setup', 'capture', 'overview', 'project-overview', 'board', 'agent-column', 'copy-task', 'evidence',
      'scan-source', 'standup', 'decision-reasons', 'architecture-page']),

  // ---- The board ----
  story('board', SECTIONS.board, t('The board in three moves'), t('columns, a drag and the swim lanes'),
    ['board', 'drag-card', 'swim-lanes']),
  story('inside-a-card', SECTIONS.board, t('Inside a card'), t('what a task holds and how it reaches an agent'),
    ['board', 'task-open', 'task-turns', 'copy-task']),
  story('board-sprints', SECTIONS.board, t('Sprints on the board'), t('one sprint on the board, then as a runway and as blocks'),
    ['board', 'board-sprint', 'project-sprints', 'sprint-blocks']),
  story('board-deep', SECTIONS.board, t('The board, all of it'), t('cards, sprints, proof, dates and the film of the month'),
    ['board', 'drag-card', 'swim-lanes', 'board-sprint', 'task-open', 'task-turns', 'agent-column', 'copy-task',
      'evidence', 'calendar-month', 'milestones', 'timelapse']),

  // ---- The agent loop ----
  story('loop', SECTIONS.loop, t('The agent loop'), t('the task, the work and the proof'),
    ['board', 'drag-card', 'task-open', 'copy-task', 'agent-chat', 'agent-column', 'evidence', 'scan-source',
      'standup', 'contract'],
    { title: t('Working with agents') }),
  story('hand-off', SECTIONS.loop, t('Hand a task to an agent'), t('open the card, copy it, read the chat'),
    ['task-open', 'copy-task', 'agent-chat']),
  story('agent-finds', SECTIONS.loop, t('An agent adds a task'), t('a task from an agent, planned by you'),
    ['agent-column', 'task-open', 'drag-card']),
  story('proof', SECTIONS.loop, t('Proof before Done'), t('the task asks for evidence, the agent brings it, you accept'),
    ['copy-task', 'evidence', 'home-needs-you']),
  story('scan-story', SECTIONS.loop, t('From a chat to a scan'), t('one message becomes a record of files and architecture'),
    ['agent-chat', 'scan-source', 'files', 'architecture']),
  story('morning', SECTIONS.loop, t('The morning standup'), t('yesterday in one page, then what waits today'),
    ['standup', 'home-needs-you', 'board']),
  story('instructions', SECTIONS.loop, t('What agents are told'), t('the instruction file, the rules and the skills'),
    ['contract', 'rules-all', 'skills-install']),
  story('start-agent', SECTIONS.loop, t('Start an agent from the home page'), t('a sentence becomes a task and a running agent'),
    ['home-start', 'board', 'agent-chat']),

  // ---- Decisions and architecture ----
  story('decisions', SECTIONS.arch, t('Why it was done'), t('decisions with their reasons, and the chat behind them'),
    ['decision-reasons', 'project-decisions', 'scan-source']),
  story('architecture', SECTIONS.arch, t('The architecture in three views'), t('the page, the map and the changes'),
    ['architecture-page', 'architecture-map', 'architecture']),
  story('files', SECTIONS.arch, t('Which files matter'), t('the grid, the ranking and the story of each file'),
    ['files', 'files-ranking', 'files-story']),
  story('arch-deep', SECTIONS.arch, t('How the project explains itself'), t('scans, the architecture, files and decisions'),
    ['scan-source', 'scans-page', 'architecture-page', 'architecture-map', 'architecture', 'files', 'files-ranking',
      'files-story', 'decision-reasons', 'project-decisions', 'search']),

  // ---- Project memory ----
  // One tour per page of the library, reached from a link on that page.
  // They are short on purpose: a reader who opened this is already there.
  {
    ...BASE,
    id: 'visions',
    section: SECTIONS.memory,
    name: t('Visions'),
    note: t('what the page shows, and how to give it to an agent'),
    title: t('Visions'),
    subtitle: t('your ideas about the product, kept in your own words'),
    beats: cut(['visions-page', 'visions-context', 'visions-group', 'visions-give']),
  },
  {
    ...BASE,
    id: 'rules',
    section: SECTIONS.memory,
    name: t('Rules'),
    note: t('how a rule reaches every agent, and how to remove it'),
    title: t('Rules'),
    subtitle: t('what every agent follows'),
    beats: cut(['rules-page', 'rules-all', 'rules-show', 'rules-from-problem']),
  },
  {
    ...BASE,
    id: 'problems',
    section: SECTIONS.memory,
    name: t('Problems'),
    note: t('what went wrong, what fixed it, and the rule written from it'),
    title: t('Problems'),
    subtitle: t('what went wrong and what fixed it'),
    beats: cut(['problems-page', 'problems-open', 'problems-rule']),
  },
  {
    ...BASE,
    id: 'skills',
    section: SECTIONS.memory,
    name: t('Skills'),
    note: t('writing a skill, installing it, and keeping the copies current'),
    title: t('Skills'),
    subtitle: t('instructions an agent loads when a task matches'),
    beats: cut(['skills-page', 'skills-list', 'skills-projects', 'skills-copies', 'skills-used']),
  },
  story('problem-to-rule', SECTIONS.memory, t('From a problem to a rule'), t('what went wrong becomes a rule every agent reads'),
    ['problems-page', 'problems-rule', 'rules-from-problem', 'rules-all']),
  story('skill-from-chat', SECTIONS.memory, t('A chat becomes a skill'), t('the work of one chat, installed for every agent'),
    ['agent-chat', 'skills-install', 'skills-projects', 'skills-used']),
  story('kept-results', SECTIONS.memory, t('Results worth keeping'), t('artifacts, prompts and starred things'),
    ['artifacts', 'prompts', 'important']),
  story('memory-deep', SECTIONS.memory, t('What the project remembers'), t('visions, rules, problems and skills, page by page'),
    ['visions-page', 'visions-context', 'visions-give', 'rules-page', 'rules-all', 'rules-show', 'problems-page',
      'problems-open', 'problems-rule', 'rules-from-problem', 'skills-page', 'skills-projects', 'skills-used']),

  // ---- Time ----
  story('hours', SECTIONS.time, t('Your hours'), t('the timer in a project, across projects, and per sprint'),
    ['timer-project', 'timer-page', 'sprints']),
  story('sprints', SECTIONS.time, t('Sprints'), t('planned days, the tasks in them and the progress per day'),
    ['project-sprints', 'sprint-blocks', 'sprints', 'sprints-progress']),
  story('plan-ahead', SECTIONS.time, t('Plan the weeks ahead'), t('the month, the week and the milestones'),
    ['calendar-month', 'calendar-week', 'milestones']),
  story('task-time', SECTIONS.time, t('How long work takes'), t('finished tasks, sprint days and your hours'),
    ['stats', 'sprints-progress', 'timer-page']),
  story('time-deep', SECTIONS.time, t('Time and plans, all of it'), t('the day, the timer, sprints, the calendar and the numbers'),
    ['overview', 'timer-project', 'timer-page', 'project-sprints', 'sprint-blocks', 'sprints', 'sprints-progress',
      'calendar-month', 'calendar-week', 'milestones', 'stats']),

  // ---- Search and history ----
  story('log', SECTIONS.find, t('Views of the history'), t('the recorded chats as entries, pages, files and a film'),
    ['capture', 'chats-find', 'scans-page', 'standup', 'decision-reasons', 'architecture', 'files', 'search',
      'important', 'timelapse'],
    { title: t('One history, many views'), subtitle: t('entries, architecture, files and a film, from the recorded chats') }),
  story('find', SECTIONS.find, t('Find anything'), t('one word, every kind of record'),
    ['search-words', 'search', 'chats-find']),
  story('timelapse', SECTIONS.find, t('A month as a film'), t('the board moves, then the whole month plays'),
    ['board', 'drag-card', 'timelapse']),
  story('chats', SECTIONS.find, t('Read any chat again'), t('the chats of a project, a search, one chat in full'),
    ['project-chats', 'chats-find', 'agent-chat']),
  story('stars', SECTIONS.find, t('Star what matters'), t('agents and tasks you starred, on one page'),
    ['project-agents', 'board', 'important']),

  // ---- Agents ----
  story('agents', SECTIONS.agents, t('One page per agent'), t('every agent, one of them, its chat'),
    ['agents-page', 'agent-overview', 'agent-chat']),
  story('agent-team', SECTIONS.agents, t('Every chat of a project'), t('the timeline, the cards, one agent'),
    ['project-overview', 'project-agents', 'agent-overview']),
  story('agents-deep', SECTIONS.agents, t('The agents, in depth'), t('who worked, on what, how long, and what they were told'),
    ['agents-page', 'project-overview', 'project-agents', 'agent-overview', 'agent-chat', 'important', 'stats',
      'home-start', 'copy-task', 'contract']),

  // ---- Setup and integrations ----
  story('setup', SECTIONS.setup, t('Connect a project'), t('Setup, the instruction file and the settings'),
    ['setup', 'contract', 'settings']),
  story('look', SECTIONS.setup, t('Make it yours'), t('language, theme and the sidebar'),
    ['settings', 'appearance', 'sidebar-settings']),
  story('setup-deep', SECTIONS.setup, t('Setup and settings, all of it'), t('from connecting a project to what every agent reads'),
    ['setup', 'settings', 'appearance', 'sidebar-settings', 'contract', 'rules-all', 'skills-install',
      'skills-projects', 'visions-give', 'guide', 'about']),
]

/** How a cut looks: its caption skin and its stage colours. */
type Look = { panel: Panel; theme: string }

/**
 * One look for the whole channel: the headline panel on the slightly
 * theme, opened by the two stems settling into the name and closed on the
 * plate. Every cut is the same film in that sense, so the catalogue reads
 * as one channel and a viewer learns the layout once. The other panels,
 * themes and hands stay one click away in the studio.
 */
const LOOK: Look & { opening: Opening; ending: Ending } = { panel: 'headline', theme: 'slightly', opening: 'stems', ending: 'plate' }

const dress = (cuts: Script[]): Script[] => cuts.map((c) => ({ ...c, ...LOOK }))

export const PRESETS: Script[] = dress(CUTS)
