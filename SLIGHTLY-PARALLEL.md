# Slightly Parallel agent contract

You are working in a project observed by Slightly Parallel — a self-hosted dashboard
where humans read and agents write. Follow this contract so your work is
visible and durable.

You write through the Slightly Parallel MCP server, `slightly-parallel`, which Setup wires
into every observed project. Its tools stamp your identity (project,
agent id, date, time) and check the vocabulary before a request exists,
so you never copy those values by hand. The server refuses a write that
names an agent and did not come through the MCP tools, while the
operator's setting `agents.mcp_only` is on (it is on by default). Some
tools load MCP tools only when they are searched for (Codex): if
`write_entry` is not in your list, look for the `slightly-parallel` tools,
or call its `doctor`. Only if that fails is the server not connected: then
tell the user before writing anything; reading the dashboard over HTTP
(`GET`) is always fine.

The server lists its tools, each with what it takes. Section 4 names the
tool for each kind of writing; `write_entry` writes one entry of any lens.
The resources `sp://contract`, `sp://schema`, `sp://rules`
and `sp://health` hold this file, the write schema, the active rules
and the server's state.

## 1. Capture and signals

Your conversation is captured automatically — each user message and your
final answer land verbatim in the project's chat log, and the dashboard
reads the chats (when, how long, how many turns) from the timestamps.
Your job is the *entries*: write them with the MCP tools when section 4
says so.

Bracketed `[slightly-parallel]` notices may appear in your context. They are operator
signals — act on them before substantive work. Each one names itself first:
`[slightly-parallel] <name> — <what happened>. <what to do>`, where the name is one of
the kinds below, or the command (`#scan`) or the tag (`#vision`) that fired
it. The identity notice is the one exception: it opens with the project.

- **identity notice** (first turn, and on refresh) — your `agent_id`, the
  project code and the current date/time. The MCP tools stamp these for
  you; the notice is how you know capture is on.
- **standup notice** — a new day started: write a standup for the previous
  day (section 4).
- **decision notice** — the conversation sounds like a decision: offer to
  log it (section 4).
- **refresh notice** — long chat: re-read THIS file and the rules in
  the project's AGENTS.md, so the contract and the operator's corrections
  survive context compaction.
- **files notice** — a scan has no file entry behind it: write the file
  entry for that scan (section 4).
- **architecture notice** — a scan has no architecture answer behind it:
  write the eight-group form, or all groups `checked` (section 4).
- **kept notice** — the user tagged the message `#vision`, `#rule`,
  `#problem` or `#entrypoint`: the server keeps it; write its interpretation with
  `interpret` (section 4, Kept messages). For `#skill`, write the skill
  from this chat with `skill_draft` (section 4, Skill).
- **command notice** — the user typed a command (section 2): it names the
  skill with the steps and the tool to start with.
- **evidence notice** — the user typed `#evidence`: it names the task
  (section 4, Finishing a task).
- **capture-failure notice** — the hook could not write the turn: tell the
  user, and write nothing as an agent until it is fixed.

In Claude Code the notices arrive in your context. Under Codex and
OpenCode they do not: read the commands in section 2 yourself.

Never write Slightly Parallel's CSVs directly, and never post to the HTTP API as an
agent — the MCP tools are the only way to write (the preamble says what the
server does with a write that goes around them).

Vocabulary the tools and the server enforce (a wrong value is refused with
the allowed list, never a silent loss): task `status` ∈ unclassified ·
backlog · next · agent · todo · parked · doing · review · review-later ·
done · done-archived (`agent` is the only status you may create with —
section 4, `#task`); problem `status` ∈ open · resolved; architecture `op`
∈ add · change · remove over a closed set of entity types, with per-type
required fields and path checks (section 4). A decision requires its
`decision` line.

## 2. Commands

When the user types one of these, act as described. Commands start with
`#` and may stand anywhere in the message. One written with three hashes
(`###now-todo`) is the message's only command: the other tags in it are
silenced, and the notice names only that one.

| Command | What you do |
|---|---|
| `#scan` | Checkpoint: write a scan, then the file entry and the architecture form it triggers (section 4). The only way a scan is written — the user asks for it |
| `#architecture` | Bring the architecture up to date: the form for the last scan, the page and the map, each only when out of date (the skill update-the-architecture) |
| `#evidence` | Get the operator's instructions with task_evidence_ask, then attach the evidence (Finishing a task, section 4) |
| `#task <hint>` | Write the task the user is pointing at, from the conversation, into the `agent` column, for later; `#task {lane} …` names the board lane (section 4) |
| `#now <text>` | Title the task this chat starts on; the server keeps the operator's message as its text, in `doing`, in the lane for #now or the one in braces; then do the work; `#done` closes it (section 4) |
| `#now-todo <text>` | Title the operator's message; the server files it, as written, in To do (also `-next`, `-backlog`, `-review`, `-parked`, `-done`, `-doing`); not started in this chat (section 4) |
| `#page` | Write the next version of the project's architecture page: architecture_material, then architecture_page (the skill keep-the-architecture-page) |
| `#decision` | Log the decision just made (also offered on `decision_hint`) |
| `#map` | Map the program: ask the operator first, then a helper agent calls map_material, then map_write (the skill map-the-program) |
| `#problem <text>` | Nothing to write — the server keeps the message as a problem; write its interpretation (Kept messages, section 4) |
| `#problem solved <id or text>` | Update it: `status:"resolved"`, `resolved_date` |
| `#standup` | Write the standup for yesterday now (also offered on the first message of a day) |
| `#rule <text>` | Nothing to write — the server keeps the message as a rule; write its interpretation (Kept messages, section 4) |
| `#vision` | Nothing to write — the server keeps the message as a vision; write its interpretation (Kept messages, section 4) |
| `#prompt` | Nothing to write — the server keeps the message in the operator's prompt library |
| `#important` | Nothing to write — the server stars the message, its agent and the tasks it names; `#important-agent`, `-task` or `-message` stars one of them |
| `#skill` | Write the skill from what was done in this chat (Skill, section 4) |
| `#artifact <what>` | Write the folder under the project's artifacts/, then make its record with artifact_write (Artifact, section 4) |
| `#help` | Answer the operator with the list of commands and what each does for them (the skill sp-help holds it) |
| `#done` | MCP tool task_done: the server has moved the task; say what moved, then your task_report line (the skill finish-a-task) |
| `#entrypoint` | Nothing to write — the server keeps the message as an entry point; write its text (Kept messages, section 4): What, Where, How, State, Next |
| `#undo <what was the mistake>` | MCP tool undo_find, list the candidates by number, then undo_propose with the operator's numbers and show its confirm text (the skill undo-a-mistake) |
| `#undo-yes` | The operator confirmed: MCP tool undo_apply. The server archives only on this reply right after your proposal |
| `#sp <what worries you>` | MCP tool checkup: say what works and what is a concern, in the fixed shape; with text, look into that too. Read freely; change nothing without the operator's yes (the skill sp-checkup) |

**Resolving `<id or text>`**: if it looks like an id (`sp_…`, `pb_…`), use it.
Otherwise read the lens (`search`, or `GET /api/<lens>?project=…`), match
the text against headlines, and confirm with the user when more than one
candidate fits. A task id may carry a turn — `tk_28b1b490.2` is the second
round of instruction on that task, and the text you were given is that
round alone. Strip the suffix to address the task; keep it when you name
the task in your entries, so the work can be tied back to the round that
asked for it. The earlier rounds are in the task's description. `ar_…`
names two things: an artifact and an architecture form. The notice that
gave you the id says which — an artifact id arrives with `#artifact`,
while an architecture form is addressed through its scan's `trigger_id`.

**Lifecycle updates** go through `update_entry {lens, id, changes}` with
only the fields to change (each lens's mutable fields are in
`sp://schema`; a field outside them is refused by name). The text of
an entry is changed by the same names it was written with (section 3),
every name but the first: `changes: {why: "…"}` on a decision rewrites its
why, while the `decision` line itself is fixed once written. Tasks are the
exception: their text is `description` (and rounds are `turns`), and they
are edited with `task_update`.

## 3. What an entry holds

Every entry is one call: `write_entry {lens, fields}`. `fields` holds the
whole entry by name: what the entry says, and the columns of its lens.
The page of each lens decides what an entry holds, so the names differ by
lens:

| lens | the line | the text | the list (one item each) | the long part |
|---|---|---|---|---|
| `scan` | `summary` | `why` | `deltas` | `proof` |
| `file` | `summary` | `narrative` | `per_file` | `diff` |
| `decision` | `decision` | `why` | `alternatives` | `excerpt` |
| `problem` | `problem` | `impact` | `attempts` | `excerpt` |
| `standup` | `summary` | `deviation` | `movement` | `detail` |
| `task` | `title` | `description` | | |
| `sprint` | `headline` | `retro` | `points` | `detail` |
| any other | `headline` | `summary` | `points` | `detail` |

Section 4 says what goes in each, per lens. `sp://schema` lists every
lens with its names and columns. A name the lens does not have is refused,
and the refusal lists the names it has. Do not send project, agent id,
date or time: the tool stamps them.

Two rules hold everywhere. The first field is one sentence: what happened,
or what it is. A field you cannot fill is left out: the wrong kind of
content is worse than an empty field. The answer may carry a `warnings`
list when an entry falls short. Fix it with `update_entry {lens, id,
changes}` — every name but the first — and write a new entry only when the
first line itself is wrong. The same entry written twice is one entry.

**Born from a discussion** (decisions, and any entry you write because of
an exchange; tagged visions, rules, problems and entry points are kept by the server
instead, section 4): the long part holds the chat excerpt as it was said.
The list holds the exchange, one item per point ("user: …", "agent: …").
The text holds the takeaway. The reader goes from the one line to what
was said.

Dates use `YYMM-DD` (`2608-12` = 2026-08-12). Times are `HH:MM`. The tool
stamps both.

**How to write an entry.** This holds for every entry, and most of all for
scans, standups and decisions.

The reader is the team lead. They know the product in outline. They were not in the chat. They do not know file names, function names, variant numbers, internal nicknames or what was tried. Their time is expensive, and they decide from what you write.

Do these four things, in this order.

**1. List before you write.** Go through all the material, every chat, to the last turn. List each separate change, each thing that went wrong, and each question left open for the lead. One change is one item: never join two. Then write from the list.

**2. Say only what the material says.** Do not fill a field because it is there: leave it empty. No invented reasons, alternatives, plans or states. No "all", "every", "each" unless you counted. A state is what the material states: done, built but not checked, waiting on someone (say who), or left (say what is left).

**3. Make every sentence clear with no chat history.**
- Name the concrete thing, in the words the page shows: "the Evidence section of the task window", "the #evidence command". Never an umbrella word in its place: not "the setup", "the framework", "the standard tools", "the flow".
- The first time a product term appears, add up to eight words saying what it is. After that, use the same word.
- A word that lives only in the chat or the code is replaced by what it is: not "the framework" but "the operator's evidence feature (a checkbox and saved prompts)"; not "fork" but "a helper agent"; not "variant v03" but "the third draft layout"; not "the other session" but "a second agent working in the same repository".
- Leave out file names, function names, commit hashes, variant numbers and code. Say what the thing does for the user or for an agent.
- A task is its title, then its id: "Evidence upgrade (tk_0e571cfa)". Put an id only on work the material ties to that id.
- Numbers carry their unit and their base: "11 of 45 files".
- A question for the lead carries what they need to answer it: what it is, how old, and what happens under each choice.
- Something that was broken or unsafe says since when, and whether it was used or lost anything — or "not known". A screen that crashed is never a "small fix".
- Do not address the reader as "you". Do not cite turn numbers.

**4. Make it short.**
- One fact per sentence, 25 words at most. Subject, verb, object.
- Say each fact once in the whole entry. A later field never repeats an earlier one.
- A sentence states a fact. Cut a sentence that states a benefit: "reduces noise", "without guessing", "makes it clearer".
- Keep to the word budget of the task. Over budget: cut the least important item. Never cut the few words that say what a thing is.
- The plain word: "removed", "shows", "uses".
- No metaphors, sayings or slogans — the small ones too: not "path", "gap", "hole", "gate", "door", "spine", "nearby". Things do not act like people: not "the page knows", "the test holds", "the fork died".
- No praise, no drama: not "finally", "real", "clean", "simply", "just", "earns its keep".
- Say what is. Leave out what is not, unless the lead would expect it.
- No introduction, no conclusion.

Examples of the change to make:

| Written for the chat | Written for the lead |
|---|---|
| Fork died on rate limit at 50%. | A helper agent stopped at the usage limit. The copy button and date format are unified. Agent names and tests for the new parts are left. |
| Named fields per lens; old slot keys removed. | Each kind of entry (decision, standup, scan) now has its own field names, such as `why` and `alternatives`. Before, all kinds shared four numbered levels. |
| `deps.identity_of` closes the hole. | A raw request could pass as the operator by naming both the operator and an agent. The server now treats such a request as the agent's. |
| The day went to plan with multiple features shipped. | (cut — it states no fact) |
| Closes security gaps and reduces friction. | (cut — say what a user or an agent can now do, or could not do before) |

Before you send it, read each sentence as the lead: is it clear with no chat history? Would the lead miss it? Does the material say it? Fix or cut.

## 4. When and what to write

**Checkpoint** (`#scan`). Only when the user types `#scan` — never on your own. You may offer one after shipping or before a risky change. A scan is three entries: the scan, its file entry and its architecture form. It ends with the architecture page when the scan changed what the project is. Call `scan_material`: it returns this chat's commits since your last scan, the files they touched, what is not committed, the counters, and the instructions for all three. The skill `make-a-scan` holds the steps.

**File entry** (`write_entry {lens: "file"}`). Written after a scan, with the scan's id as `trigger_id`: your judgment of the files that matter. `scan_material` carries the instructions.

**Architecture** (`#architecture`). Keeps three things current, each only when out of date: the form for the last scan (`write_entry {lens: "architecture"}`, with the scan's id as `trigger_id`: eight groups, each checked or with its changes; written after every scan), the architecture page, and the map of the program. Call `architecture_status`: it says which are needed and why. The skill `update-the-architecture` holds the steps. `#page` and `#map` still do their one part.

**Finishing a task — `task_report {id, summary}`.** Task status belongs to
the operator: never change a task's `status` yourself. When you believe a
task is done, report it — `summary` is one line: what shipped. The server
records your opinion (the operator sees a badge), moves the card to
*review* only if the operator switched auto-manage on for that task, and
answers with `evidence: true|false`. When evidence is wanted, the answer
carries the operator's instructions verbatim — follow them with
`task_evidence {id, items}`: each item is `{kind: "text", title, body}`
(markdown) or `{kind: "image", title, data_base64, ext}` (a screenshot).
At most 8 items per post; the operator's prompt usually asks for 1–3.
The same item written twice is one item.

**`#evidence`** is the same thing asked by hand. Call
`task_evidence_ask {id}` for the task the `[slightly-parallel] #evidence` notice
names: it returns the same instructions a done-report would have
carried. Follow them the same way.

Under the operator's instructions the answer may carry `evidence_extra`:
say what the task touched and what it did, as one `files` item and one
`change` item beside the proof. `task_work {id}` returns the files the
repository saw in the turns that named the task: read it before writing
the `files` item, so you judge the list instead of hunting for it. The
skill `task-evidence` holds the fields and an example. Keep both short: up
to seven files that matter, not every file.

Story notes on the Storyboard are the operator's field — write one only
when asked, and the ask arrives as a *press release request*: a prompt
from the operator that names a request id (`sr_…`). Answer it with
`task_story {id, request_id, body, images}` — markdown body; a screenshot
goes into the text as `![title](image:1)`, 1-based. Without an open
request id the write is refused; one piece per request, and the kind of
note is the one the operator asked for.

A Storyboard document comes to you as a *pack*: one markdown the operator
copied, with the doc id (`dc_…`) on its second line. Make the document
final in the pack's shape, then post the whole text with
`doc_version {id, body, note}` — markdown body; `note` is one line on what
this version changed. Each post is the next version; the operator reads
and compares them on the Storyboard. An unknown id is refused.

**Agent task** (`#task <hint>`, `#now <text>`, `#now-todo <text>`). Only when the user writes one of them, with `write_entry {lens: "task"}`. `#task`: you write the task from the conversation, title and text, into the `agent` column for later. `#now`: the task this chat starts on, in `doing`; `#now-todo` (`-next`, `-backlog`, `-review`, `-parked`, `-done`) files it in that column, not started. A `#now` task's text is the operator's message as written, kept by the server: you send the title and tags only; a note of yours goes after it with `task_update {id, comment}`. `{lane}` after the tag names the board lane; the server sets it. The skill `write-a-task` holds the steps.

**Architecture page** (part of `#architecture`, and at the end of a `#scan`; `#page` still asks for it alone). One page per project: what it is, what it does now, what it is made of and what is owed, as claims with their evidence, for a team lead who was not in the chat. Call `architecture_material`: it returns the computed facts, the current page and the instructions. Write the next version with `architecture_page {text, note}`. The skill `keep-the-architecture-page` holds the steps.

**Decision** (`#decision`, or on your own when a piece of work is done). Log each point where a choice was made, if the product would be different had it gone the other way. One `write_entry {lens: "decision"}` each, with a `weight`: minor, normal or major. The skill `log-a-decision` holds the steps.

**Map** (part of `#architecture`; `#map` still asks for it alone). For a project that is a program: every part as a row in one table (runtime, entry, surface, api, module, service, store, external, config, build, deploy, test …), and what connects to what. It reads up to 40 files, on a helper agent on the model Settings names. Under `#architecture` it runs when `architecture_status` says the program's shape changed, without asking; a bare `#map` is the operator asking. The helper calls `map_material`, then `map_write {map, note}`. The skill `map-the-program` holds the steps.

**Problem — `#problem`, or `write_entry {lens: "problem"}`.** The user's
`#problem` is kept by the server (see *Kept messages*). When you are
blocked yourself, write one the moment it happens — before workarounds
bury it. `problem`: what is blocked, in one line. `impact`: what it
affects, and who or what owns the fix. `attempts`: one item per attempt:
`"<tried> — <result>"`. `excerpt`: the error or the log. Resolve with
`#problem solved` → `update_entry {lens: "problem", id, changes: {status:
"resolved", resolved_date}}`.

**Standup** (`#standup`, or the `[slightly-parallel] No standup for …` notice). One per project per day, from every chat of that day. Ask the operator: write it now, or postpone. A helper agent calls `standup_material {claim: true}`, which carries the instructions, and writes it. The skill `daily-standup` holds the steps.

**Rule — `#rule`.** The operator's correction of how you work, kept by the
server in the operator's own words (see *Kept messages*). Rules reach you
through AGENTS.md: the block "Rules for all agents", which Slightly Parallel keeps in
every project, and any set of rules the operator wrote into this project.
Follow them. A kept rule holds the operator's words as written, and the
interpretation beside them. Whether a rule is for all agents is the
operator's choice.

**Vision — `#vision`.** A directional idea, kept by the server in the
user's own words.

**Kept messages — `#vision`, `#rule`, `#problem`, `#entrypoint`.** The tagged message is
the entry: the server takes it from the chat log verbatim. Do not write an
entry for it. A message that is only the tag keeps nothing: no id is
minted and no notice appears — ask the user what to keep. The hook names the id —
`[slightly-parallel] #vision — the server keeps this message as vs_…` — and your part
is the interpretation, written in the same turn:
`interpret {lens: "vision" | "rule" | "problem" | "entrypoint", id, text}` (`text` is
markdown; `note` is one optional line on what changed).

The interpretation is the message read with the conversation around it:
what the user means, in plain words, with what the context settles —
constraints, rejected options, what it replaces. A vision: the direction
and what it would change. A rule: the rule, imperative, and the incident
behind it. A problem: what is blocked and what was tried. An entry point:
the five sections of its own part (Entry point, below). Keep the user's
words where they are exact; add nothing that was not said. Each write is a
version; the operator edits from there. On the page, the message is "Your
words" and the interpretation sits beside it.

`#prompt` is kept the same way, into the operator's prompt library. It
asks nothing of you: answer the message as usual.

`#important` is kept the same way, as a star: the server marks the message,
the agent of the chat and every task the message names; `#important-agent`,
`#important-task` (the named task, else the last task named in this chat)
and `#important-message` mark one of them. There is nothing to write.

**Skill — `#skill`.** The operator wants what was just done to become a
skill: a procedure any agent loads when a task matches. The server keeps
the message and the hook names the id. Write the draft from what actually
happened in this chat, not from general knowledge:
`skill_draft {id, skill_md, files, note}` — `skill_md` is the whole
SKILL.md; `files` is `{"scripts/check.sh": "…"}`, relative paths to text.

SKILL.md starts with a `---` block: `name` — lowercase letters, digits and
single hyphens, the folder name agents see; `description` — what the skill
does and when to use it, in the words the operator uses when asking for
it, at most 1,024 characters. Agents read only the description when they
choose a skill. The body: the steps in order, the exact commands, the check
that proves it worked, and the mistakes made in this chat that the next
agent should avoid. Put long reference text and scripts in `files` and
link them from SKILL.md. When you rewrite SKILL.md later, leave `files`
out to keep the ones the skill has; send `{}` only to remove them. The
answer lists `checks`: fix every error and write again. The operator reads
the draft on the Skills page and decides where it is installed; you do not
install skills.

**Artifact** (`#artifact`). The operator wants a result kept in one place and shown on the Artifacts page: a dataset, a document, a page or an app. Write the folder yourself at `<data_root>/projects/<project>/artifacts/<name>/`, then make its record with `artifact_write {id, name, kind, description}`. The skill `make-an-artifact` holds the steps.

**Help** (`#help`). Answer the operator with the list of commands, what each does for them and where they see the result. The skill `sp-help` holds the list; give it as it is, in the operator's language, and add nothing that is not in it.

**Done** (`#done`). The operator closes a task from the chat: the server moves it to done and gives it its stretch of the chat. Call `task_done`, say what moved, then your one-line `task_report`. The skill `finish-a-task` holds the steps.

**Entry point — `#entrypoint`.** The way into a topic, for whoever comes
back to it after a while — the operator in a month, or an agent in a new
chat. One entry point per topic ("the install film", "the launch"), kept by
the server from the operator's message; you write its text through
`interpret {lens: "entrypoint", id, text, note}`.

The text has five sections, as Markdown headings, 400 words at most
(Where is the long one: every path and link the topic needs):

- **What** — what the topic is and what for, one or two sentences.
- **Where** — the files, folders, artifacts and links the topic lives in,
  one per line, exact paths.
- **How** — how to run or repeat it: the commands, the pages, the skill to
  use.
- **State** — where the work stopped, as of this version.
- **Next** — what comes next, by items.

Write it from this chat: the paths and commands that were used, the state
as the last messages leave it. Nothing that was not done or decided. A
second `#entrypoint` on the same topic is a new version of the same
record: replace State and Next, add to Where and How, keep the rest.
`topic` is the title, four words or so.

When the operator opens a topic that has an entry point, read it first
(the Entry points page, or `GET /api/entrypoints?project=…`): it says
where things are and where the work stopped.

**Undo** (`#undo`). The operator archives entries made by mistake. List the candidates from `undo_find` by number; send their numbers' ids to `undo_propose` and show its confirm text; on `#undo-yes`, call `undo_apply`. Never archive without both. The skill `undo-a-mistake` holds the steps.

**Is it working** (`#sp`). Call `checkup` and report it in the fixed shape: the verdict, each concern as what · why it matters · the next step, then one line of what is fine. What could not be checked is said, never called fine. With text after the tag, look into that worry too. Read and investigate freely; restart, re-integrate or change nothing without the operator's yes. The skill `sp-checkup` holds the steps.

## 5. Reading

Reading is open: the MCP readers and the HTTP `GET` routes both answer.

- `tasks {project?, status?}` — the board; `search {q}` — tasks,
  decisions and agents by text; `project {code}` — one project's bundle;
  `deck` — every running sprint block; `doctor` — the data-integrity report.
- `sp://rules` — the active rules; `sp://schema` — every lens,
  its fields and what is mutable; `sp://contract` — this file.
- `GET /api/<entity>?project=<PROJECT>` — any ledger, filterable.
- `GET /api/<entity>/{id}` — one entry with its text and fields.
- `GET /api/sessions?project=<PROJECT>` — the chats, read from the turns (read-only).
- `GET /api/agents/<agent_id>/profile` — everything under one agent id:
  chats, scans, entries, the tasks its turns named, links, group
  (read-only; yours is under your own id).
- `GET /api/snapshot` — the cross-project overview.

Full reference: `docs/api.md` in the Slightly Parallel repo, or `/docs` on the server.
The dashboard's Guide page describes every page as it is.
