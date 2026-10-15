/**
 * The text at the top of the visions, rules and problems pages: what the
 * page shows and how to add to it, then "How it works" — the steps from a
 * tagged message to what agents read. Windows XP style: plain words, one
 * fact per line. Every step describes what the code does.
 */

import { t } from '../../i18n/scope/shell'

export interface Guide {
  /** What the page shows and how to add an entry. */
  intro: string[]
  /** What each part of an entry or the page does: [name, text]. */
  parts: Array<[string, string]>
  /** How it works, in order. */
  steps: string[]
  /** How to give entries to an agent. */
  giveTitle?: string
  give?: Array<[string | null, string]>
  /** A last line under the steps. */
  note?: string
}

export const VISIONS_GUIDE: Guide = {
  intro: [
    t('This page shows your ideas about the product.'),
    t('To add a vision, type #vision in the chat. Slightly Parallel keeps the message. The agent writes what it understood.'),
  ],
  parts: [
    [t('Your words'), t('the message as you wrote it.')],
    [t('Context'), t('the messages before and after it.')],
    [t('Edit'), t('change the text. Each change is saved as a new version.')],
    [t('Tags and sets'), t('group visions.')],
    [t('Projects'), t("write a set to a project's AGENTS.md, so the agents in that project can read it.")],
  ],
  steps: [
    t('You type #vision in the chat.'),
    t("Slightly Parallel keeps the message from the chat log and gives the agent the vision's ID."),
    t('The agent writes what it understood. This is version 1.'),
    t('The vision appears on this page. Context shows 3 messages before and 3 after, taken from the chat log.'),
    t('When you edit the text, Slightly Parallel keeps a new version. The first version stays.'),
  ],
  giveTitle: t('To give visions to an agent:'),
  give: [
    [t('Copy'), t('copies the text. Paste it into a message.')],
    [t('Projects'), t("writes a set into the project's AGENTS.md. Agents read AGENTS.md at the start of a chat.")],
    [null, t('After you change a vision in a set, the project shows "older copy". Click Update.')],
  ],
}

export const RULES_GUIDE: Guide = {
  intro: [
    t('This page shows rules for agents.'),
    t('To add a rule, type #rule in the chat. Slightly Parallel keeps the message. The agent writes the rule.'),
  ],
  parts: [
    [t('For all agents'), t('the rule is added to AGENTS.md in every project.')],
    [t('Sets and Projects'), t('add rules to chosen projects only.')],
    [t('Archive'), t('remove the rule from all projects.')],
  ],
  steps: [
    t('You type #rule in the chat.'),
    t('Slightly Parallel keeps the message. The agent writes the rule.'),
    t('Turn on For all agents: Slightly Parallel writes the rule into AGENTS.md in every project in Setup. Only you can turn it on or off.'),
    t('When you change, archive or restore a rule, Slightly Parallel updates AGENTS.md in every project automatically. A project added to Setup later gets the rules too.'),
    t('For chosen projects only: add the rule to a set, then write the set from Projects. After a change, click Update.'),
  ],
  note: t('Agents read AGENTS.md when a chat starts. A running chat reads it again after a restart, or when Slightly Parallel asks it to during a long chat.'),
}

export const PROBLEMS_GUIDE: Guide = {
  intro: [
    t('This page shows problems found during work.'),
    t('To add a problem, type #problem in the chat. The agent writes what is blocked and what was tried.'),
  ],
  parts: [
    [t('Resolve'), t('mark the problem as fixed.')],
    [t('Create rule'), t('write a rule based on the problem.')],
  ],
  steps: [
    t('You type #problem in the chat. An agent can also add a problem when it is blocked.'),
    t('Slightly Parallel keeps your message. The agent writes what is blocked and what was tried.'),
    t('Resolve marks the problem as fixed. You can also type "#problem solved" with the problem\'s ID in a message, and the agent resolves it.'),
    t('Create rule: you write a rule based on the problem. The rule is linked to the problem. The problem keeps its status. The rule then works like any other rule.'),
  ],
  giveTitle: t('To give problems to an agent:'),
  give: [[null, t('Copy, or add them to a set and write the set from Projects.')]],
}

export const SKILLS_GUIDE: Guide = {
  intro: [
    t('This page shows skills: instructions an agent follows for a task you repeat.'),
    t('To add a skill, type #skill in the chat. The agent writes the skill from what was done in that chat.'),
  ],
  parts: [
    [t('SKILL.md'), t('the name, the description and the steps. Agents read the description to decide when to use the skill.')],
    [t('Checks'), t('problems that stop the skill from working, or make agents skip it.')],
    [t('Projects'), t('install the skill into a project, or into all projects at once.')],
    [t('Used'), t('how many times agents used the skill, and in which chats.')],
  ],
  steps: [
    t('You type #skill in the chat.'),
    t('Slightly Parallel keeps the message and asks the agent for a draft.'),
    t('The agent writes SKILL.md from the chat. This is version 1. Slightly Parallel checks it.'),
    t('You read the draft, edit it if needed, and install it into a project. Slightly Parallel writes the folder into .claude/skills for Claude Code and .agents/skills for Codex. OpenCode reads both.'),
    t('All projects writes the skill into the same folders in your home folder. Every agent on this machine reads them, in any project.'),
    t('Skills already on your computer are listed under "Not in Slightly Parallel". Take one in to keep its versions and copies here. Slightly Parallel reads the folder and leaves it in place.'),
    t('When you edit the skill, Slightly Parallel keeps a new version. Projects with the older version show "older copy". Click Update.'),
    t('If a copy in a project is edited by hand, the project shows "changed on disk". Keep that copy as a new version, or overwrite it.'),
    t('When a Claude Code agent uses a skill, Slightly Parallel keeps the chat and the message.'),
  ],
  note: t('Only you install skills. Agents write drafts.'),
}

export const ARTIFACTS_GUIDE: Guide = {
  intro: [
    t('This page shows artifacts: folders an agent made for you. A dataset, a document, a page, an app.'),
    t('To ask for one, type #artifact in the chat and say what you want. The agent writes the folder and the entry.'),
  ],
  parts: [
    [t('Chapters'), t('one per kind. A dataset shows its fields and a sample. A document shows its text. A page opens in a frame. An app shows its files and the line that runs it.')],
    [t('Your words'), t('the message you typed. It stays as written.')],
    [t('Files'), t('what the folder holds, with sizes.')],
    [t('ARTIFACT.md'), t('the name, the kind, the description, and any notes the agent left.')],
  ],
  steps: [
    t('You type #artifact in the chat and say what you want.'),
    t('Slightly Parallel keeps the message and tells the agent the folder to write: projects/<project>/artifacts/<name>/ in the data folder.'),
    t('The agent writes the folder, then writes the entry with one call. The artifact appears here.'),
    t('When the agent edits the folder and writes the entry again, the page shows the folder as it is.'),
    t('A folder you made by hand goes in with Add a folder.'),
    t('Archive takes an artifact off the page. The folder stays on disk. Restore brings it back.'),
  ],
  note: t('The skill make-an-artifact on the Skills page tells every agent how.'),
}

export const SCANS_GUIDE: Guide = {
  intro: [
    t('This page shows scans: what one agent changed in a project since its last scan, committed or not, day by day.'),
    t('To ask for one, type #scan in the chat when work is shipped. The agent writes it.'),
  ],
  parts: [
    [t('Month'), t('one cell per day, shaded by how much was said; a dot marks a day with a scan. Click a cell to go to the day. The arrows change the month.')],
    [t('Totals'), t('the month in numbers: scans, files, lines, commits, and the changes by type.')],
    [t('Day'), t('the date, then the day\'s numbers: agents, messages, tasks done and moved, commits, files and lines, minutes.')],
    [t('Scan'), t('one sentence, then the changes as chips, why it changed, and what changed in up to five lines; Show all opens the rest.')],
    [t('Files and Changes'), t('collapsed by default, with their counts. The switch in the title row expands them all.')],
    [t('Text size'), t('the five A\'s in the title row. The entries grow; each page keeps its own size.')],
    [t('No scan'), t('a day with work and no scan is one grey line with the day\'s numbers.')],
  ],
  steps: [
    t('You type #scan in a message to the agent.'),
    t('The agent gets its own commits since its last scan, the files its turns changed and what is not committed, with lines counted.'),
    t('The agent writes the scan, then the file entry, then the architecture form.'),
    t('A scan of the day appears under that day, with the numbers Slightly Parallel counted.'),
  ],
  note: t('Only you ask for a scan. The skill make-a-scan holds the steps.'),
}

export const STANDUPS_GUIDE: Guide = {
  intro: [
    t('This page shows standups: one per project per day, written from every chat of that day.'),
    t('The first agent of a new day asks to write it. To get one now, type #standup in the chat.'),
  ],
  parts: [
    [t('Month'), t('one cell per day, shaded by how much was said; a dot marks a day with a standup. Click a cell to go to the day. The arrows change the month.')],
    [t('Totals'), t('the month in numbers: standups, messages, tasks done and commits. Under them, the days that have a standup.')],
    [t('Numbers'), t('beside each day: agents, messages, tasks done and moved, commits, files and lines, minutes. Slightly Parallel counts them; the agent does not.')],
    [t('Text size'), t('the five A\'s in the title row. The entries grow; each page keeps its own size.')],
    [t('Focus'), t('the Focus button in the title row, or F: one day full screen — the days on the left, the day drawn small by section on the right. [ and ] move between days, j and k between sections, A reads every day as one, Esc leaves.')],
    [t('The day'), t('the story of the day in a few paragraphs: what was done and why it mattered.')],
    [t('What went wrong, What moved'), t('what broke or was redone, then what changed, each line marked New, Changed, Fixed, Architecture, Cleanup or Decided.')],
    [t('Tasks and agents of the day'), t('every task that moved, with its moves, and every agent that worked, with a button to resume it. Taken from the record, not written by the agent.')],
    [t('Created'), t('artifacts, rules, skills, visions, problems and ideas made that day.')],
    [t('Decisions'), t('what was chosen and why, by you or by an agent.')],
    [t('Maybe forgotten, More'), t('collapsed: what was asked or promised and not done; what needs your answer and what is next.')],
    [t('No standup'), t('a day with work and no standup is one grey line with the day\'s numbers.')],
  ],
  steps: [
    t('A new day starts. Slightly Parallel tells the first agent that the day before has no standup.'),
    t('The agent asks you: write it now, or postpone.'),
    t('A helper agent reads every message of that day and writes the standup. Settings holds the model.'),
    t('The page shows one section per day, newest first.'),
    t('Click a day in the strip above, or a cell in the month, to go to it.'),
  ],
}

export const DECISIONS_GUIDE: Guide = {
  intro: [
    t('This page shows decisions: what was chosen, why, and what was turned down, read day by day.'),
    t('Agents log decisions when a piece of work is done. To log one now, type #decision in the chat.'),
  ],
  parts: [
    [t('Month'), t('one cell per day, shaded by how much was said; a dot marks a day with a decision. Click a cell to go to the day.')],
    [t('Totals'), t('the month in numbers: decisions, how many are major, messages and commits.')],
    [t('Day'), t('the date, then the day\'s numbers: agents, messages, tasks done and moved, commits, files and lines, minutes.')],
    [t('Decision'), t('one sentence: what was chosen. Major and minor decisions are marked.')],
    [t('Why'), t('the reason the agent gave. A major decision also says what would undo it.')],
    [t('Alternatives'), t('options someone proposed. An option turned down is struck, with the reason.')],
    [t('Text size'), t('the five A\'s in the title row. The entries grow; each page keeps its own size.')],
    [t('Where it was decided'), t('the chat around the decision, folded.')],
    [t('No decision'), t('a day with work and no decision is one grey line with the day\'s numbers.')],
  ],
  steps: [
    t('A piece of work is done, or you type #decision.'),
    t('The agent lists each point where a choice was made. It logs one only if the product would be different had it gone the other way.'),
    t('Each decision gets a weight: minor, normal or major. The skill log-a-decision holds the steps.'),
    t('The decision appears under the day it was made, beside the work of that day.'),
  ],
}

export const PROMPTS_GUIDE: Guide = {
  intro: [
    t('This page shows the prompt library as a table: the messages you kept as prompts.'),
    t('To add one, type #prompt in a message. The server keeps the message. The agent writes nothing.'),
  ],
  parts: [
    [t('Row'), t('one prompt: its project and task, score, sends, what it made and when it was last sent.')],
    [t('Sent again'), t('a message you sent several times is offered above the table: keep it as a prompt, copy it, or mark it not a prompt.')],
    [t('A and B'), t('two versions of the prompt, side by side.')],
    [t('What changed'), t('what differs between the two versions.')],
    [t('Where it was sent'), t('the chats the prompt was sent in, and what they changed. Collapsed under the prompt.')],
  ],
  steps: [
    t('You type #prompt in the chat.'),
    t('The server keeps the message as a prompt.'),
    t('Click a row to open the prompt. Click it again to close it.'),
  ],
}

export const FILES_GUIDE: Guide = {
  intro: [
    t('This page shows the file entries of every project, newest day first.'),
    t('A file entry is written by an agent after a scan. To ask for a scan, type #scan in the chat.'),
  ],
  parts: [
    [t('Day'), t('what shipped on that day, and in which project.')],
    [t('File entry'), t('one line per scan. Click it to list the files it changed, with lines added and deleted and how important each is.')],
    [t('Path'), t('click a path to read the history of that file: every file entry that named it.')],
  ],
  steps: [
    t('You type #scan in the chat.'),
    t('The agent writes the scan, then the file entry: the files that matter, with a line on each.'),
    t('The file entry appears here under its day.'),
  ],
}

export const ARCHITECTURE_GUIDE: Guide = {
  intro: [
    t('This page shows the architecture of one project, in three views. Page: what the project is. Map: every part of the program in one table. Changes: what each scan changed.'),
    t('The page and the changes are written at the end of a scan. The map is written by a helper agent when you choose it. Each can be asked for alone: #page, #map, #architecture.'),
  ],
  parts: [
    [t('Project'), t('pick the project. The number is how many changes it holds.')],
    [t('Page, map and changes'), t('the switch next to the picker. Your choice is remembered.')],
    [t('Computed by Slightly Parallel'), t('the top band of the page. It comes from the folder, with no agent: active or dormant, size, folders, recent commits.')],
    [t('Claim'), t('one item of the page. It says where the thing is, how the agent knows, who made it and who checked it.')],
    [t('Marks'), t('red: the path was not found. Amber: the file changed after the page was written.')],
    [t('Map'), t('one row per part of the program: runtime, entries, surfaces, modules, stores, outside services, build, deploy, tests. Under it, what connects to what. Written by a helper agent that reads up to 40 files, so the agent asks first.')],
    [t('Changes'), t('what each scan changed, in eight groups, read three ways. Debts and actions stay on top.')],
  ],
  steps: [
    t('You type #scan. The agent writes the scan, then the architecture form, then a new version of the page when the scan changed what the project is.'),
    t('A new day starts. The first agent asks about the standup and offers to map the program with a second helper. You answer with a number.'),
    t('For the page, the agent keeps what is verified, corrects what is wrong and adds what it touched. Slightly Parallel checks every path and marks what it did not find.'),
    t('For the map, the helper reads the repository and fills the rows of the template. Slightly Parallel checks every row against the vocabulary, the template and the folder.'),
  ],
}

export const KANBAN_GUIDE: Guide = {
  intro: [
    t('This page shows every board: one per project, then the saved boards.'),
    t('You add a task on the board. An agent adds one when you type #task in the chat; it goes into From agents.'),
  ],
  parts: [
    [t('Boards'), t('the strip on top. + new board saves a board of your own.')],
    [t('Columns'), t('Unclassified, Backlog, Next, From agents, To do, To do · parked, Doing, Review, Review later, Done, Done archived. The 3-col view leaves out Backlog, Next and Review.')],
    [t('Card'), t('click a card to open the task window: description, tags, milestone, auto and evidence.')],
    [t('Auto'), t('when an agent reports the task done, the card moves to Review. When off, the card shows a badge.')],
    [t('Evidence'), t('when on, the agent attaches proof after it reports the task done. #evidence asks for it by hand.')],
    [t('Storyboard'), t('below the board: story notes put into documents. Copy a document\'s pack to an agent; the agent posts the finished text back as a version. Open a version to read it, copy it or compare it with the one before. Paste one yourself for an agent without the tools.')],
  ],
  steps: [
    t('You write a task, or type #task and the agent writes it into From agents.'),
    t('You move the cards. An agent does not change a status.'),
    t('You copy the task to an agent. The agent works and reports the task done.'),
    t('The report shows on the card. With evidence on, the proof is in the task window.'),
  ],
  note: t('Only you change a status. An agent reports that a task is done.'),
}

export const SPRINTS_GUIDE: Guide = {
  intro: [
    t('This page shows sprints: blocks of work.'),
    t('Running shows each running sprint as a strip. Progress shows the history over time.'),
  ],
  parts: [
    [t('Running'), t('each running sprint with its tasks and timer, edited in place.')],
    [t('Progress'), t('tasks, effort and lead time per day.')],
    [t('Top of the page'), t('stays the same under both views.')],
  ],
  steps: [
    t('Open Running to work on the running sprints.'),
    t('Open Progress to see how past sprints went.'),
  ],
}

export const CALENDAR_GUIDE: Guide = {
  intro: [
    t('This page shows the month, the week and the milestones across projects.'),
    t('Pick the projects with the project picker.'),
  ],
  parts: [
    [t('Month and week'), t('tasks on their days.')],
    [t('Milestones'), t('a milestone names a result, with a done-when check and its proof.')],
    [t('Drag'), t('drag a task onto a milestone or a day.')],
  ],
  steps: [
    t('Pick a view: month, week or milestones.'),
    t('Write a milestone with its done when and its proof.'),
    t('Drag tasks onto it, and onto days.'),
  ],
}

export const AGENTS_GUIDE: Guide = {
  intro: [
    t('This page shows every agent, project by project, most recently active first.'),
    t('An agent appears when it sends its first message in an integrated project.'),
  ],
  parts: [
    [t('Totals'), t('the number of agents and projects, and the time worked.')],
    [t('Find'), t('one search over names, ids and headlines.')],
    [t('Groups'), t('chips that show only the agents of one group.')],
    [t('Card'), t('click a card to open the agent: its chats, its tasks and its work.')],
  ],
  steps: [
    t('Setup connects a project: the hook that records chats, the agent tools and a section of AGENTS.md.'),
    t('You start an agent in that project. The hook records each message.'),
    t('The agent appears here under its project.'),
  ],
}

export const CHATS_GUIDE: Guide = {
  intro: [
    t('This page shows every recorded chat: the list on the left, the chat on the right.'),
    t('Chats are recorded automatically, each message as it was sent.'),
  ],
  parts: [
    [t('Month'), t('one cell per day, shaded by how much was said; a dot marks a day with a chat. Click a cell to open the first chat of that day. The arrows change the month.')],
    [t('Totals'), t('the month in numbers: chats, turns, time, agents and commits.')],
    [t('Agents'), t('beside the month: the agents of this project, the most talkative first, with turns and the day each was last active. Click one to see only its chats. The box finds an agent by name.')],
    [t('What a chat holds'), t('chips that filter the list. What came out: commits, a task, and every kind of entry an agent can write. What came in: the saved prompt a chat was sent from, and the messages kept out of it. Weight: turns and minutes. Each chip shows how many chats it would leave.')],
    [t('List of chats'), t('date, turns and time, then the first line of the chat and what came out of it. A dashed line marks a gap of six hours or more.')],
    [t('Focus'), t('the Focus button, or F: the chat alone, full screen. j and k move between turns, [ and ] between chats, A reads every chat in one scroll, Esc leaves.')],
    [t('Chat'), t('the turns, oldest first. Each turn shows the message, the reply, and the commits it made.')],
    [t('Find'), t('the box in the title row reads every turn of every chat, beyond the headlines. Each row says how many turns match.')],
    [t('Over the panes'), t('how wide the list is, its text size and the chat\'s, how many chats it holds, and whether you read one chat or every chat in one scroll.')],
    [t('Settings'), t('the gear sets the order of turns, markdown or raw text, and whether a turn shows its commits.')],
  ],
  steps: [
    t('You start an agent in a connected project. The hook saves each message and reply.'),
    t('The hook also records the commits made during a turn.'),
    t('The chat appears here after its first message.'),
    t('Resume opens the chat again in the tool it ran in.'),
  ],
}

export const TIMER_GUIDE: Guide = {
  intro: [
    t('This page shows the timers of every project and where your time went.'),
    t('A timer runs on a block: a running sprint of a project, or everything else in it. Start and stop it here.'),
  ],
  parts: [
    [t('Top'), t('the numbers, today as a dial, and the last 26 weeks, for all projects together.')],
    [t('Table'), t('a row for each block: start or stop it, and read its time today, on each of the last 7 days and in the period.')],
    [t('Entries'), t('the last 7 days of every project. Click a row to open the project.')],
    [t('Mode'), t('remind asks when you open a task, auto counts while you work on the project, manual counts only what you start.')],
    [t('Period'), t('7, 30 or 90 days. It sets the last column of the table.')],
  ],
  steps: [
    t('Start a block. The timer runs on the server and keeps running after a reload.'),
    t('Stop it. The time becomes an entry.'),
    t('Open a project to edit an entry, set a share or write a note on its Timer tab.'),
  ],
}

export const OVERVIEW_GUIDE: Guide = {
  intro: [
    t('This page is the home page: how long the agents worked today against a usual day, what runs now, what waits for your decision, and every day of the year that had agent time.'),
    t('Every line links to the page where you act on it.'),
  ],
  parts: [
    [t('Start an agent on a task'), t('type the work and pick a project: it becomes a task on that project\'s board, and an agent starts on it in a terminal.')],
    [t('The day'), t('agent time through the day. The dashed line is a usual working day: the mean of the days with agent time in the 30 days before. Early in the morning it shows yesterday.')],
    [t('Now'), t('the chats working or waiting for you now.')],
    [t('Latest standups'), t('the newest standup of each project.')],
    [t('Needs you'), t('urgent problems and tasks in review. Accept or Send back decides a task here.')],
    [t('With agents'), t('the last 30 days against the 30 before, and every day with agent time.')],
    [t('Projects'), t('each project with its latest standup and its agent time per day.')],
  ],
  steps: [
    t('Read the line on top: who works and what waits.'),
    t('Accept or send back the tasks in review.'),
    t('Click a line to open its page.'),
  ],
}

export const IMPORTANT_GUIDE: Guide = {
  intro: [
    t('This page shows everything you marked important, in three sections: messages, agents and tasks.'),
    t('Type #important in a chat to mark the message, its agent and the task it names.'),
  ],
  parts: [
    [t('#important-message, #important-agent, #important-task'), t('mark only one of them.')],
    [t('★'), t('marks by hand on the board, on the agent cards and in the chat reader.')],
  ],
  steps: [
    t('You type #important in a chat, or click a ★.'),
    t('The mark appears here, in its section.'),
    t('Click an entry to open it.'),
  ],
}

export const STATS_GUIDE: Guide = {
  intro: [
    t('This page shows what each finished task took: messages and time in the chat, commits and files, and the time from creation to done.'),
    t('Pick a project and a period. Click a task to open it.'),
  ],
  parts: [
    [t('Numbers'), t('how many tasks finished and how many were reopened, then the medians of what a task took.')],
    [t('Table'), t('one row per finished task. Click a column head to sort by it.')],
    [t('Closed'), t('exact when the task was closed with #done in the chat, estimated otherwise.')],
  ],
  steps: [
    t('A task is closed with #done in a chat, or moved to done on the board.'),
    t('With #done the stretch of the chat is exact. Otherwise it runs from where the task was named to where the next one was.'),
    t('The task appears here with what it took.'),
  ],
}

export const MONITOR_GUIDE: Guide = {
  intro: [
    t("This page shows this computer's CPU, memory, disk, network, connection and temperature."),
    t('Readings are taken every few seconds. An unusual reading is saved as an event, with the processes running at that moment.'),
  ],
  parts: [
    [t('Tiles'), t('each measure now, with its last minutes.')],
    [t('Charts'), t('the chosen span. Unusual moments are shaded.')],
    [t('Events'), t('what was unusual lately. Click one to see its processes.')],
    [t('Switch and Settings'), t('turn the monitor off, or set what is read, how often and how long it is kept.')],
  ],
  steps: [
    t('The monitor reads the computer in the background.'),
    t('A reading past a limit, or far from usual, becomes an event.'),
    t('Old readings are thinned out. Events are kept longer.'),
  ],
}

export const SEARCH_GUIDE: Guide = {
  intro: [
    t('This page finds a word across tasks, entries, map parts and chat turns.'),
    t('Each result opens its own page. Under the box are the numbers of the index.'),
  ],
  parts: [
    [t('Box'), t('type a word. The rail on the left narrows the matches by kind, project, month, where the word sits and who said it. Each filter shows as a chip in the box; Backspace drops the last one.')],
    [t('Results'), t('entries first, then chat turns grouped by chat. Enter opens the one picked.')],
    [t('Numbers'), t('how many rows, turns and words the index holds, and where the word was said.')],
  ],
  steps: [
    t('Type a word.'),
    t('Move through the results with the arrow keys.'),
    t('Press Enter to open the result on its own page.'),
  ],
}

export const TOUR_GUIDE: Guide = {
  intro: [
    t('This page lists the tours: the ones that cross the product, and one each for Visions, Rules, Problems and Skills.'),
    t('A tour runs over the real pages of the example project, shopfront, and points at the example entries.'),
  ],
  parts: [
    [t('Tours'), t('click one to start it.')],
    [t('Studio'), t('write your own tours at /tour/custom, and photograph them on the example project for a film.')],
  ],
  steps: [
    t('Pick a tour.'),
    t('Follow the steps. Each step points at one control and says what it is for.'),
    t('Press Escape to stop. The page stays where you left it.'),
  ],
}

export const TERMINAL_GUIDE: Guide = {
  intro: [
    t('This page lists every terminal by project. A terminal is a shell on this computer, in the dashboard.'),
    t('The ` key shows a terminal on any page.'),
  ],
  parts: [
    [t('Resume'), t("reopens a chat's agent in a terminal.")],
    [t('Start an agent'), t('opens one on a task.')],
    [t('Copy'), t('drag with the mouse, or right-click for Paste, Copy the last output and Select lines.')],
    [t('Paths'), t('Ctrl+click a printed path to open it in your editor.')],
  ],
  steps: [
    t('Open a terminal in a project.'),
    t('Each terminal shows its state. The top bar is highlighted when an agent waits.'),
    t('With tmux, terminals keep running after the page closes or the server restarts.'),
  ],
}
