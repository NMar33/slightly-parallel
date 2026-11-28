# Slightly Parallel API reference

Every route the server publishes, once each, grouped by area and in route
order inside the area. Interactive OpenAPI docs are at
`http://localhost:8123/docs`; this page lists them.

Each line reads: **method · path — what it does. Body: … Answers: …**
"Body" lists the JSON keys a `POST` reads; "Answers" the top-level keys of
the 200/201 payload. `—` means none beyond the lens shape.

## How the API works

- **Dates** use `YYMM-DD`: `2608-12` = 2026-08-12. Times are `HH:MM`, local.
- **ETags** — every list and detail 200 carries an `ETag`; send
  `If-None-Match` and get `304` while nothing changed.
- **Missing data** — missing files and unknown projects answer with empty
  payloads. A CSV that cannot be read is served as an empty list, shows up in `GET /api/health` as `degraded: true` with `load_errors`,
  and the server keeps serving. Any unhandled error answers with an
  `error_id` that matches the traceback in the server log.
- **The repeat rule** — a create mints a deterministic id from
  `(created_date, created_time, project, agent_id, headline)`. Posting the
  same payload again writes nothing and answers `200` with `existing: true`;
  something written answers `201`. This holds on every create route: the
  lenses, scans, the architecture form, task evidence, story notes and tasks.
- **Named fields** — an entry is written by what it holds, not by slot
  numbers. Each lens has its own names (`backend/backend/entry_fields.py`):
  a decision has `decision`, `why`, `alternatives`, `excerpt`; a problem has
  `problem`, `impact`, `attempts`, `excerpt`; a scan has `summary`, `why`,
  `deltas`, `proof`; a lens with nothing of its own has `headline`,
  `summary`, `points`, `detail`. Creates and updates take these names next
  to the lens's columns. `GET /api/schema` lists them per lens.
- **Row and text** — each entry is a CSV row plus an optional Markdown
  document named by `md_ref`, whose text sits in three sections. The slots
  `l1…l4` are storage only; the server maps each name onto its slot and no
  agent-facing text names them. The MCP translator refuses the slots: an
  agent writes by name or not at all.
- **Entry warnings** — a create that falls short still persists, and the
  answer carries a `warnings` list. Checked today: decisions (rejected
  `alternatives`, the reversal condition in `why`), problems (`impact`,
  `attempts`), rules (the incident behind the rule).
- **Refused writes** — a value that would make a row silently invisible is
  refused with 422 and the allowed list: `sprint.status`, `task.status`,
  `problem.status`. A decision or goal with no first line is refused the
  same way; the requirement is derived from the read models, so the two
  sides cannot drift.
- **Every reason at once** — a refusal whose checks do not depend on each
  other names all of them (`backend/backend/refusals.py`): `detail` is
  text, one line per reason (`reason — what to do`), most general first,
  and the status is the first reason's; one reason reads as it always has.
  The answer adds `reasons`, one `{reason, instead, code, field?}` each; the
  MCP translator numbers two or more. A missing entity (404) and no access
  (403) are each the only reason: the other checks are not run.
- **Agents write through MCP** — a POST whose `actor` or `agent_id` names an
  agent is accepted only with the header `X-SP-Via: mcp`, which the MCP
  translator sets on every call; otherwise 422, naming the tools. The
  operator's pages send a house actor and pass. Setting `agents.mcp_only`
  turns the gate off.
- **Identity in an agent's body** — on every path the MCP writes to (the
  lens creates and updates and `server._MCP_WRITE_PATHS`), an agent's body
  names who it is by `agent_id` or `actor` and nothing else of identity.
  `from`, `from_agent`, `agent`, `created_by`, `session`, `session_id`,
  `created_date` and `created_time` are refused with 422 «`session_id` is
  stamped by Slightly Parallel; leave it out»; a lens create's own
  `created_date`/`created_time` are the exception (the translator stamps
  them there). The same names, or a `project`, inside an object the body
  carries (an evidence item, a map row, a way in) are refused with 422 and
  where they were: «… (inside items[0])». `actor` and `agent_id` naming two
  different agents is 422. Other routes keep their own rules. A writer
  Slightly Parallel has no chat of is refused with 403 on every agent write
  («agent cc-… is not a chat Slightly Parallel has recorded; nothing was
  written. Tell the operator»). With `agents.mcp_only` off these checks
  still hold.

---

## Reading

Derived and aggregate reads. Nothing here appends to a ledger except the two
noted writes.

- `GET /api/health` — liveness plus data-root diagnostics (`degraded`,
  `load_errors`).
- `GET /api/snapshot` — the Overview payload: KPIs, per-project summaries
  with task counts, recent chats and decisions, open tasks in play, every agent.
  Helper chats (a `codex exec`, a `claude -p`, an `opencode run` another chat
  started; `helper` in their `meta.json`, see [logging.md](logging.md)) are
  left out of the agents, the counts, the hours and the recent chats here, in
  `GET /api/project/{code}` and in `GET /api/timeline`; search answers no
  helper as an agent (its turns are still found).
- `GET /api/search?q=&types=&limit=` — one word over everything
  (`searchlib.py`): every entity in the registry, every scan, every agent,
  every row of a project's map, and every captured **turn** of every chat —
  a turn at a time, not the transcript as one blob. Each row is matched on its id,
  its own words and its detail document; a turn is matched on what was said,
  never on its chat's name, which every turn of that chat shares. `types`
  names the kinds to look in, singular or plural; empty means all. Answers
  `hits` — `{kind, id, title, project, date, snippet, where, count}`, and for
  a turn also `{role, turn, at, session_id, agent_id}` — title matches first
  and newest first inside that, with `counts` per kind and `total` over every
  match, not the returned page. The index is held in memory and rebuilt when the
  store or a chat changes.
- `GET /api/search/overview?q=&types=` — what is in the index, for a search
  page that has no query yet: the kinds, every day with how much landed on
  it, how long a turn runs (buckets), the chats that carry the weight, who
  said more, and the words that come up most with stop words dropped. It is
  counted once when the index is built, so the page costs a lookup. With
  `q`, the same shape over the rows that match, plus `near`: the words that
  keep this one company, ranked by how much more often they sit beside it
  than they do anywhere else.
- The index is rebuilt when the store or a chat changes, but not more often
  than every 15 seconds: the chat being typed into moves its file on every
  turn, and rebuilding per request cost half a second each.
- `GET /api/timeline?project=&from=&to=` — per-agent activity lanes.
- `GET /api/heatmap?project=` — file × date touch counts from agent metadata.
- `GET /api/timelapse?project=` — one project's whole life as film source:
  cards, moves, the activity chart's series, marks.
- `GET /api/project/{code}` — one project's bundle: summary with task counts,
  decisions, activity, agents.
- `GET /api/projects/{code}/reason` — the operator's one-line note on why
  the project matters. Answers: `project`, `kind` (attention · money · time ·
  learning · other), `text`, `updated_at`.
- `POST /api/projects/{code}/reason` — write it. Body: `kind`, `text`.
  Answers: `project`.
- `GET /api/agent/{agent_id}` — one agent: meta, chat availability, its
  decisions. Agents carry `tool`, `session_ref`, `cwd` — the origin the
  capture hooks record from the first turn, enough to print a resume command.
  Answers: `agent`, `chat_lines`, `chat_available`, `decisions`.
- `GET /api/agents/groups?project=` — the groups in use, with their members.
- `GET /api/agents/links?project=` — the hand-drawn links between agent lanes.
- `POST /api/agents/links` — draw one. Body: `from`, `to`, `kind`, `style?`,
  `note?`, `from_at?`, `to_at?`, `actor?`. Directed: *from* is the earlier
  lane. Idempotent on `(from, to, kind)`. Answers: `created`, `link`.
- `POST /api/agents/links/{link_id}/update` — body: `kind`, `style`, `note`;
  the ends stay. Answers: `link`.
- `POST /api/agents/links/{link_id}/delete` — answers: `deleted`.
- `GET /api/agents/profiles?project=` — every agent of a project with its
  profile: the roster in one read. Helper chats are not in `profiles`: each
  is in its parent's `helpers`, and `orphans` lists the project's helpers
  whose parent is not known or was not recorded. A helper row:
  `{agent_id, agent_name, chat_title, project, tool, helper_kind, helper_of,
  helper_of_by, started, first_line, message_count, tokens, cost_usd}` —
  `tokens` new input plus output, helpers included; `cost_usd` dollars at
  API prices, null when nothing was priced.
- `GET /api/agents/{agent_id}/profile` — everything one agent left behind,
  `helpers` (the runs it started) included. A helper's own profile carries
  `helper`, `helper_kind` and `helper_of` in `agent`.
- `GET /api/agents/{agent_id}/membership` — the agent's projects
  (tk_d1d25a4d): `origin` (the project of the folder its chat started in),
  `home`, `members` (origin first), `joined`, `projects` (the same as a comma
  string, the shape tasks carry), `level` 1–3 with `level_words`,
  `runs_from_folder`, `helper`, and `summary`, the operator summary in three
  lines. Folded from `agent_memberships.csv` per request.
- `POST /api/agents/{agent_id}/membership` — the operator's only. Body:
  `op` (`join` | `leave` | `level`; `home` is refused until routing and
  accounting follow it), `project` (join, leave), `value` (level: 1, 2 or 3;
  otherwise an optional one-line reason). Refused, each in one line and
  writing nothing: an agent's identity, a project that does not exist, a
  join of a project the agent is in, a leave of its origin or home or of a
  project it is not in, a helper chat, the values the project delete and the
  chat move write (`project deleted`, `moved from …`), `op: moved`, a field
  of the wrong shape (422 naming it). 503 while a delete or a move holds the
  ledger. Answers: the GET's fields and `row`, the row written.
  A leave and an agent's write that race: a write whose membership check
  starts after the `leave` row is in the ledger is refused; one checked while
  the agent was still a member counts, even when it lands after the leave
  (tests/test_membership_race.py).
- `POST /api/agents/{agent_id}/move-chat` — the operator's only. Body: `to`,
  one of the agent's member projects other than its origin. Moves the chat
  folder there (copy, verify bytes, sha256 and turns, set `project` in the
  copy's meta.json, rename; the original to `.trash/move-<id>-<stamp>/`) and
  writes a `moved` row. Refused in one line, writing nothing: a target that
  is not a member project or is the origin, a folder already at the target,
  a running agent (a turn open, a change in the last 60 s, a lock a hook
  holds), a chat that changed during the copy, a helper chat, two chat
  folders. Answers: `agent_id`, `from`, `to`, `folder`, `trash`, `turns`,
  `files`, `row`, and `effects` — its past minutes, tokens and commit
  ownership count to `to`; its session ids change. A move that stopped
  before the original went to the trash leaves two folders: a second try is
  refused saying which holds the later writes and what to do.
- `POST /api/agents/{agent_id}/move-chat/abandon` — the operator's only.
  Body: `to`, the project that holds the copy a stopped move left. Moves the
  copy (and a `.incoming-<id>` one) to `.trash/abandon-<id>-<stamp>/` by one
  rename, so the move can be made again. Refused in one line, writing
  nothing: `to` not a project code, no copy at `to`, the copy being the
  chat's only folder, two originals, a copy holding writes the original
  lacks, a lock a hook holds in the copy. Answers: `agent_id`, `to`,
  `original`, `trash`, `removed`.
- `GET /api/project-aliases` — the short names the operator's braces may
  name a project by (`#task {SP} …`). Answers: `aliases`, each `{alias,
  project}`. Read from `project_aliases.csv` (`id, at, project, alias, op,
  actor`), append-only, folded by `membership_fold.aliases`.
- `POST /api/projects/{code}/aliases` — the operator's only. Body: `op`
  (`add` or `remove`), `alias` (1–40 letters, digits, `.`, `-`, `_`). An
  alias is unique, any case, across every project code and every alias;
  the check and the write are one step under the file's lock. Refused in one
  line, writing nothing: no such project (404), a name taken (409), not an
  alias of this project on remove (409), a bad name (422). Answers:
  `aliases`, `row`. The settings page for them comes later (step 7).

The braces after `#task` / `#now` (any number, any order, each at most 80
characters: `#now-todo {ui} {writing-tracker} …`) are read by one rule in the
hook and the server (`hookshared.resolve_braces`): `{project:x}` /
`{lane:x}`; an exact project code or alias, any case (a project the chat is
not a member of is refused); an exact live lane of the target board; a near
miss of a code or alias (difflib ratio ≥ 0.8) refused with a hint; anything
else a new lane. Two projects or two lanes are refused and no card is made.
Every refusal of the braces is named at once (`reasons`; the hook's notice
joins them with "; "), except a project the chat is not a member of, which
is said alone. A lane name close to an existing lane files the card in the
default lane with its proposed name and suggestions. A bare name that is
both a project and a lane still asks which after filing. A new lane named
by the operator opens on the board. An exact match to an agent lane promotes it. An agent's create on that command must send the project
the braces named; its status, text, lane, title and tags are then checked
together, every refusal in one answer.
- `POST /api/agents/{agent_id}/group` — body: `group` (empty removes).
  Answers: `agent_id`, `agent_group`.
- `POST /api/agents/{agent_id}/rename` — body: `name`, stored as
  `agent_name` in the agent's `meta.json`. Answers: `agent_id`, `agent_name`.
  Both of these are presentation only; the ids never change.
- `GET /api/chat/{agent_id}?range=a-b` — a raw `chat.md` line slice.
- `GET /api/sessions?project=` — the chats, newest first. Helper chats are
  left out unless `agent_id` names one or `helpers=1`. Each row carries `chat_end_line`, the chat's last line in chat.md, which grows with every captured line (a page's cue to fetch that chat's turns again). Read from the
  captured turns; agents never write these. The pages call them chats; the
  route keeps the name it was published under, and one chat with a long
  pause in it is read as two.
  Each row carries `produced` — every kind an agent can write during the
  run, all twelve of them, counted by agent, day and the chat's own time
  window (`produced.py`) — and `marks`: the saved prompt the chat was sent
  from, and the messages kept out of it by kind (`kept-vision`, `kept-skill`,
  …). Both are read once per store version.
- `GET /api/sessions/turns?ids=a,b,c` — the turns of many chats in one
  round trip, up to 500. Answers: `turns`.
- `GET /api/sessions/{session_id}` — one chat: turn summaries plus a raw
  excerpt.
- `GET /api/sessions/{session_id}/diff?…` — the change behind a work line:
  one file of one commit, or a whole commit.
- `POST /api/sessions/{session_id}/open` — body: `path`; opens the file on
  this laptop with whatever opens it. Answers: `opened`, `path`.
- `GET /api/files/heatmap?project=` — touches aggregated per date and per
  file entry. Without `project`, every project: a file is then keyed by
  `project::path` (`key` on each file row, and in `matrix` and `cells`).

---

## Entries

Every lens has the same trio, and a fourth route where it has mutable
columns:

```
GET  /api/<base>             # list  — {"total": n, "<listKey>": [rows]}
GET  /api/<base>/{id}        # detail — {"metadata", "l2", "l3", "l4", "text", …}
POST /api/<base>             # create — CSV row + MD document, 201 (see the repeat rule)
POST /api/<base>/{id}/update # lifecycle fields and/or the text; unknown fields ignored
```

Every list takes `project`, `agent_id` (alias `agent`), `from_date` (alias
`from`), `to_date` (alias `to`) and `limit`, plus the extra filters below.
`?with_l2=1` (alias `with_desc=1`) attaches each row's text inline, one
request instead of N; on tasks it attaches `description`, `turns_n` and
`turn_last` instead.

| Lens · routes | Extra list filters | Mutable via `/update` | Detail extras |
|---|---|---|---|
| `/api/activity` · `/api/activity/{id}` | `goal_id`, `activity_type`, `min_duration`, `max_duration` | — | for external pipelines; agents never post it |
| `/api/architecture` · `/api/architecture/{id}` | — | — | see **Architecture** |
| `/api/artifacts` · `/api/artifacts/{id}` · `/api/artifacts/{id}/update` | — | `status`, `tags` | see **Artifacts** |
| `/api/decisions` · `/api/decisions/{id}` · `/api/decisions/{id}/update` | `source`, `related_goal_id` | `tags`, `weight` | — . A new decision's answer carries `similar`: the project's one decision most like it (`id`, `decision`, `created`, `score`), with a line in `warnings`; never refused |
| `/api/files` · `/api/files/{id}` · `/api/files/{id}/update` | `trigger_lens` | `files_ignored_n`, `files_important_n` | `paths` (see below) |
| `/api/goals` · `/api/goals/{id}` · `/api/goals/{id}/update` | `status`, `parent_goal_id`, `sprint_id`, `root_only` | `confidence_pct`, `retro_outcome`, `sprint_id`, `status`, `success_comment`, `time_est` | `children`. **Retired**: the product no longer writes goals; the routes stay so pre-task data still reads, and sprints still join the rows they have |
| `/api/ideas` · `/api/ideas/{id}` | `tag` | — | `body`. Legacy reader — the library retired in favour of tasks |
| `/api/notes` · `/api/notes/{id}` | `tag` | — | `body`. Legacy reader |
| `/api/problems` · `/api/problems/{id}` · `/api/problems/{id}/update` | `tag`, `severity`, `status`, `search` | `archived_at` (operator), `resolved_date`, `severity`, `status`, `tags` | see **Kept messages and skills** |
| `/api/prompt-runs` · `/api/prompt-runs/{id}` · `/api/prompt-runs/{id}/update` | — | `intervention`, `note`, `regression`, `score`, `task_success` | see **Prompts** |
| `/api/prompts` · `/api/prompts/{id}` · `/api/prompts/{id}/update` | `tag` | `archived_at`, `marks`, `status`, `tags`, `title` | see **Prompts** — the list and detail routes are shadowed |
| `/api/rules` · `/api/rules/{id}` · `/api/rules/{id}/update` | `tag`, `auto`, `kind`, `severity` (alias `importance`), `status` | `auto`, `kind`, `severity`, `status`, `tags` | see **Kept messages and skills** |
| `/api/scans` · `/api/scans/{id}` · `/api/scans/{id}/update` | — | `summary`, `why`, `deltas`, `proof` | see **Standups and scans** |
| `/api/skills` · `/api/skills/{id}` · `/api/skills/{id}/update` | — | `status`, `tags` | see **Kept messages and skills** |
| `/api/snippets` · `/api/snippets/{id}` | `project` only | via `/api/snippets/{id}/update` | — |
| `/api/sprints` · `/api/sprints/{id}` · `/api/sprints/{id}/update` | `status`; dates map to `started_date`/`ended_date` | `bet_days`, `confidence_pct`, `ended_date`, `goals_declared_n`, `goals_shipped_n`, `name`, `started_date`, `status`, `theme`, `time_budget_h` | `goals`; see **Tasks** |
| `/api/standups` · `/api/standups/{id}` · `/api/standups/{id}/update` | — | `blockers_n`, `goals_closed_n`, `goals_open_n`, `hours_today` | see **Standups and scans** |
| `/api/tasks` · `/api/tasks/{id}` · `/api/tasks/{id}/update` | `status`, `assignee`, `priority`, `lane` | see **Tasks** | see **Tasks** |
| `/api/time-entries` · `/api/time-entries/{id}` · `/api/time-entries/{id}/update` | `goal_id`, `sprint_id`, `running` | `duration_min`, `ended_at`, `goal_id`, `note`, `share_pct`, `sprint_id`, `started_at` | see **Operator-only admin** |
| `/api/visions` · `/api/visions/{id}` · `/api/visions/{id}/update` | `tag`, `category`, `impact`, `search` | `archived_at` (operator), `category`, `effort`, `impact`, `tags` | see **Kept messages and skills** |
| `/api/entrypoints` · `/api/entrypoints/{id}` · `/api/entrypoints/{id}/update` | `tag`, `status`, `search` | `topic`, `status` (`open`, `closed`), `tags`; an agent changes `topic` and `tags` only | see **Entry points** |

Writes an agent may not make (422 with the reason): `sprints` (the operator
plans them), `prompts` (harvested from the chat
log instead), `skills` (use `skill_draft`), `artifacts` (use `artifact_write`).

`children_n` on goals is always derived from the actual child rows; the
stored CSV value is ignored, so counts cannot drift.

Routes that do not follow the trio:

- `POST /api/files` also takes `paths`: one record per modified file —
  `path`, and optionally `action`, `lines_add`, `lines_del`, `importance`,
  `blast_radius`, `test_coverage`, `novelty`, `security_surface`,
  `agent_confidence`, `tags`, `why`. It is stored as YAML frontmatter on the
  detail document and comes back from `GET /api/files/{id}` as `paths`.
  `prev_file_id` chains per project; when the project's registered path is a
  git repo, missing line counts are filled in from git.
- `POST /api/snippets/{snippet_id}/update` — answers: `snippet`.
- `POST /api/snippets/{snippet_id}/delete` — answers: `deleted`.

---

## Tasks

The board, its blocks, and everything hung off a task.

- `GET /api/tasks` · `GET /api/tasks/{id}` · `POST /api/tasks` —
  the lens trio. Create takes the text in `description`; turns come later.
  The operator's create may add `title_from: "message"` and `title_source`
  (`<agent_id>#<turn>`, `…/reply`): the server titles the task from that
  message for now, and the title waits for that chat's agent, who sets it
  once with `title` on update (the hook's `#task-title` notice asks); an
  operator rename first ends the wait.
  For a card filed on the agent's own initiative, `lane` uses an existing
  lane or creates one in the Agents group. A similar name is refused
  with suggestions. The task rows carry `lane_kind` (`agent` or empty)
  and `lane_choice` (empty or a JSON cell with `name` and `options`).
- `POST /api/tasks/{task_id}/lane-choice` — operator only. Body: `lane`,
  the proposed name or one of the card's suggestions. Assigns the existing
  card and clears its unresolved choice.
- `GET /api/tasks/lanes?project=` lists lane names the operator saved on
  the board, including empty ones. `POST /api/tasks/lanes` takes `project`,
  `lane` and `op` (`add`, `remove` or `rename` with `previous`).
- `POST /api/tasks/lanes/promote` — operator only. Body: `project`, `lane`.
  Moves a lane and its tasks out of the Agents group.
- `POST /api/tasks/{task_id}/update` — body: `title`, `description`,
  `status`, `turn` (which round to rewrite), plus the mutable columns
  (`assignee`, `priority`, `lane`, `sprint_id`, `remember`, `today_on`,
  `stack_id`, `resurface_on`, `resurface_to`, `resurface_every_days`, …).
  Status is the operator's; an agent that sets it is refused, unless the
  task has auto-manage on, or the agent drops its own card from the agent
  column (`done-archived`). Lane, assignee, impact, effort, position,
  projects, priority, due date and the switches are the operator's too;
  an agent's tags are `ag_*`. `comment`
  adds a note after the task's text, under `--- comment from agent:` (an
  agent's) — each call adds one; on a #now card an agent's `description` is
  refused, since its text is the operator's message. An agent changes
  `title`, `description` and `today_on` only on a task it created (the
  task's `agent_id`); on the operator's or another agent's task they are
  refused, naming the creator. `comment` is open to every agent on any
  task. The one exception is the waiting title of a task made from a
  message (above).
  `think: true | false` sets or removes the operator's think mark (the
  columns `think_at`, `think_by`; `#think` / `#think-off` in a chat do the
  same). An agent sending `think` is refused. While the mark is on, an
  agent's change of `status`, `lane` or `assignee`, its
  `POST /api/tasks/{task_id}/report`, its archive and its move to another
  project are refused with a reason that names the mark; comments, notes, evidence and links stay
  open. The operator is never refused; the operator's `#done` closes the
  task and clears the mark. A refused update names every reason at once: a
  task that is not there alone (404), then who may change what (the mark,
  the operator's switches, the card's creator, the status), then the values
  (vocabulary, tags, lengths, shapes).
- `POST /api/tasks/{task_id}/turn` — the next round of instruction. Body:
  `text`, `actor`, `created_date`, `created_time`. Answers: `task`, `turn`,
  `turns`, `description`, `ref`.
- `GET /api/tasks/{task_id}/events` — every field change appended by
  `/update`, newest first.
- `GET /api/tasks/{task_id}/work` — the task's commits and files: the ones
  signed (`Task:`) or linked to it, then what the repository saw in its
  stretch of a chat. The operator opens a stretch — a message that names the
  task, or the `#now` that started it — and closes it by naming another task;
  an agent naming a task in its answer opens and closes nothing (the turn
  still shows under the task's mentions). After a pause the stretch goes on
  only into a session that names the task again. A commit several chats saw
  appear is the chat's whose `git commit` call was running when it was made
  (the hook records these calls for Claude Code, Codex and OpenCode), else
  whose tools touched its files, else whose turn was running; when nothing
  tells, it is nobody's until linked (stamps from before the calls were
  recorded keep the chat that stamped it first). Answers: `task_id`, `work`.
- `POST /api/tasks/{task_id}/commits` — `{shas: [sha …]}` (7–40 hex): the
  agent (MCP `task_commits`) or the operator links commits that carry no
  `Task:` line to this task. Answers `linked` (the new ones) and the task's
  `work`. A commit's own `Task: tk_…` line does the same without a call.
  A hash is accepted from any repository of the task (`taskwork.task_repos`):
  its project's, those of the codes in its `projects` and of the projects it
  moved from, and those of the chats that named it; `repositories` maps each
  linked commit outside the project's own repository to where it is. The
  task's `work` (GET `/api/tasks/{task_id}/work`) reads the same set, merged
  newest first.
- `POST /api/tasks/{task_id}/move` — `{to}`: the task moves to project `to`
  and keeps its id (MCP `task_move {id, project}`). The operator, or an agent at task level
  3 that is a member of both projects. `project` becomes `to`, `projects`
  loses the old project (the card leaves its board), the column and the
  document stay, the lane stays when a live card of `to` carries it (else it
  is cleared), a topic of the old project, a stack (its next card becomes
  the head), a sprint and milestone links are let go, and its notes,
  evidence, story requests and story images move with it. The
  history gets `project` (old → new) and «moved from A to B, by …». Refused
  with every reason at once, writing nothing, the most general first: no
  such task or project (404, alone); an agent below level 3 or not a member
  of `to` (403, both named, nothing else said); then together a done or
  archived task (409), the same project (409) and, for an agent, a task with
  the operator's think mark (422, naming the mark; the operator's move keeps
  the mark). Answers `task_id`, `from`, `to`, `lane`, `projects`, `lane_cleared`,
  `topic_dropped`, `stack_dropped`, `sprint_dropped`, `milestones_dropped`, `where`, `said`.
- `GET /api/commits/signed?project=&days=7` — per project with a repository:
  commits in the last `days` days, how many carry a `Task:` line (`signed`),
  how many were linked later (`linked`), and the same by the `Agent:` line.
- `GET /api/git/commit?repo=<project>&sha=<7–40 hex>[&diff=1]` — one commit
  of a project's repository, read only (the terminal window's commit card,
  and its check before a printed hash is underlined). `repo` is a project
  code, never a path. Answers `sha`, `short`, `subject`, `author`, `at`,
  `files` (`path`, `add`, `del`), `add`, `del`, `tasks` (its `Task:` lines),
  `agent`; with `diff=1` also `diff` (cut at 400 000 characters, `diff_cut`).
  404 for an unknown project, a project with no repository, or a hash that
  is not one of its commits.
- `GET /api/tasks/{task_id}/mentions` — every captured turn naming this
  task, newest first. Copying a task puts its id in the text (`tk_… · Title`)
  and the chat reading scans every turn for task ids (`tk_…`, readable ids too), so
  mentions cost nothing extra and need no ledger. `?full=1` adds the task's
  thread: `turns`, each once, with `why` (`mention`; `done` — inside a
  stretch a #done closed; `next` — after a mention no #done closed, up to
  the next task the operator names), `roles` (which sides named it), the
  operator's message `said` and the agent's `reply`, whole; and
  `done_turns`, `next_turns`, `has_done`.
- `GET /api/tasks/mentions/summary?project=` — per task: count and last
  mention.
- `GET /api/tasks/mentions/by-agent?project=` — the same, per agent lane.
- `GET /api/tasks/status-since?project=` — per task, when it entered its
  current column.
- `GET /api/tasks/timeline?project=&window=&limit=` — per task: creation,
  status changes and everything else that happened to it. `window` ∈ day ·
  week · month · all (since the project's first event).
- `POST /api/tasks/{task_id}/link` — body: `to`, `kind` ∈ blocks · relates ·
  parent, `actor?`. Answers: `created`, `link`.
- `GET /api/tasks/{task_id}/links` — both directions, resolved.
- `GET /api/tasks/links?project=` — every link touching a task of the
  project, home or member.
- `POST /api/tasks/links/{link_id}/update` — body: `kind?`, `reverse?`,
  `actor?`. Same rules as a new link. Answers: `link` (new id), `changed`.
- `POST /api/tasks/links/{link_id}/delete` — body: `actor`. Answers: `deleted`.
- `POST /api/tasks/{task_id}/archive` — body: `actor`; hides the task from
  the board, keeps everything, reversible.
- `POST /api/tasks/{task_id}/restore` — body: `actor`; the undo.
- `POST /api/tasks/{task_id}/delete` — moves row, detail document, events,
  links and story notes to `.trash/`. Answers: `deleted`, `moved`, `trash`.

### The agent-done loop

An agent reports; the operator judges. The report is never the verdict.

- `POST /api/tasks/{task_id}/report` — body: `agent_id`, `summary`. Answers:
  `task_id`, `status`, `recorded`, `moved`, `auto_manage`, `evidence`,
  `evidence_extra`, `evidence_prompt`, `evidence_prompt_id`, `next` — the
  instructions for the evidence the report owes. Refused with every reason
  at once after the 404: no `agent_id`, the think mark, the summary's shape
  and length. An archived task is refused (409) on the file, under its lock.
- `GET /api/tasks/{task_id}/evidence` — the task's evidence with git's
  account of the same work beside it. Query: `path`, `paths`, `changes`,
  `start_here`. Answers: `task_id`, `evidence`, `missing`, `work`.
- `POST /api/tasks/{task_id}/evidence` — body: `agent_id`, `items`.
  Answers: `task_id`, `saved`, `existing`. A missing task is the 404 before
  anything; every bad item is named, by its index.
- `GET /api/tasks/{task_id}/evidence/ask` — `#evidence`: the same
  instructions a done-report would have carried. Answers: `task_id`, `next`,
  `work`, `evidence_prompt`, `evidence_prompt_id`, `evidence_extra`.
- `GET /api/tasks/evidence/summary?project=` — counts per task. Answers:
  `evidence`, `images`.
- `GET /api/tasks/evidence/{evidence_id}/file` — the stored file itself.
- `POST /api/tasks/evidence/{evidence_id}/delete` — answers: `deleted`,
  `task_id`.
- `GET /api/evidence-prompts` — the saved asks the loop can use.
- `POST /api/evidence-prompts` — body: `id`, `name`, `text`, `make_default`.
  Answers: `saved`.
- `POST /api/evidence-prompts/{prompt_id}/delete`.

### Story notes, docs and press releases

- `POST /api/tasks/{task_id}/notes` — body: `type` ∈ article · post ·
  release, `body`, `template?`, `actor?`. Answers: `note`, `existing`.
- `GET /api/tasks/{task_id}/notes` — the notes of one task.
- `GET /api/tasks/notes?project=` — every story note of the project's tasks.
- `GET /api/tasks/notes/summary?project=` — counts per task.
- `POST /api/tasks/notes/{note_id}/update` — body: `type`, `body`. Answers:
  `note`.
- `POST /api/tasks/notes/{note_id}/delete` — answers: `deleted`.
- `GET /api/docs` · `POST /api/docs` — the Storyboard. Create body:
  `project`, `kind`, `title`, `actor`. Answers: `doc`.
- `GET /api/docs/{doc_id}` — the doc with its items in order. Answers:
  `doc`, `items`, `versions` (newest first: `id`, `created_at`, `agent_id`
  — an agent, or `operator` for a pasted one — `body`, `note`), `mentions`.
- `POST /api/docs/{doc_id}/update` — title and the doc's own fields.
  Answers: `doc`.
- `POST /api/docs/{doc_id}/delete` — answers: `deleted`.
- `GET /api/docs/{doc_id}/pack` — the whole doc as one text, for sending.
  It tells the agent to post its result with the MCP tool `doc_version`.
- `POST /api/docs/{doc_id}/items` — body: `note_id` places a note, `text`
  adds a free block, `position?`. Answers: `item_id`, `items`.
- `POST /api/docs/{doc_id}/items/{item_id}/update` — body: `text`.
- `POST /api/docs/{doc_id}/items/{item_id}/delete`.
- `POST /api/docs/{doc_id}/reorder` — body: `item_ids`, the new order.
- `POST /api/docs/{doc_id}/versions` — the finished text, kept, dated and
  signed; the doc's status becomes `drafted`. An agent posts it with the MCP
  tool `doc_version {id, body, note?}` (identity stamped); the operator
  pastes one from the Storyboard. Body: `body` (markdown, required, at most
  200 000 characters), `note?` (one line, at most 400), `agent_id`.
  Answers: `version`, `n` (the doc's version count), `doc` (`id`,
  `title`); the same text from the same writer in the same minute answers
  200 with `existing: true`. 404 for an unknown doc; a `dc_…` id that
  names a decision says so.
- `GET /api/story/templates` — answers: `kinds`, `types`, `templates`.
- `POST /api/tasks/{task_id}/story-requests` — the operator asks for a
  piece. Body: `type?`, `focus?`, `brief_id?`, `brief?`, `style_id?`,
  `style?`, `actor?`. Answers: `request`, `prompt`.
- `GET /api/tasks/{task_id}/story-requests` — answers: `requests`, `total`.
- `GET /api/story/requests/{request_id}/prompt` — the prompt as sent.
- `POST /api/story/requests/{request_id}/cancel` — answers: `request`.
- `POST /api/tasks/{task_id}/story` — the agent answers a request. Body:
  `request_id`, `agent_id`, `body`, `images?` (`title`, `data_base64`,
  `ext`). Answers: `note`, `images`, `request_id`. A missing task or request
  (404) and a request of another task (422) are each the only reason; the
  rest — the request's state, the agent, the body, each image — are named
  together.
- `GET /api/story/images?…` — answers: `images`, `total`.
- `GET /api/story/images/{image_id}/file` — the image itself.
- `GET /api/story/prompts` — the saved brief and style presets.
- `POST /api/story/prompts` — body: `part`, `name`, `text`, `id?`. Answers:
  `part`, `preset`.
- `POST /api/story/prompts/{preset_id}/delete` — answers: `deleted`, `part`.

### Sprints — blocks of work

- `GET /api/sprints/board?project=` — the board strip: every active sprint
  with everything the strip draws.
- `GET /api/sprints/deck` — every running block of every project, one call.
- `GET /api/sprints/timeline?project=` — every sprint, running and ended,
  with its window.
- `GET /api/sprints/{sprint_id}/dossier` — one sprint in full: the planned
  days, how it ran, the tasks, both retros.
- `GET /api/sprints/{sprint_id}/series` — per-day series derived from the
  ledgers.
- `POST /api/sprints/{sprint_id}/delete` — for a sprint that should not
  exist; real endings are a status change. Answers: `deleted`, `sprint_rows`,
  `tasks_freed`, `trash`.

### Boards — multi-project tasks

- `GET /api/boards` — the saved boards.
- `POST /api/boards` — body: `name`, `projects?`; with no projects the board
  is standalone and mints its own code.
- `POST /api/boards/{board_id}/update` — body: `name`, `projects`.
- `POST /api/boards/{board_id}/delete` — the board is forgotten; tasks are
  never touched. Answers: `deleted`.

---

## Kept messages and skills

A message tagged `#vision`, `#rule`, `#problem`, `#entrypoint`, `#skill`, `#artifact` or
`#publish` is adopted into its ledger on the way past the next list or detail read. The
kept text stays verbatim; the *interpretation* is what an agent or the
operator writes about it, as a new version under `kept_versions/`.

- `POST /api/visions/{item_id}/interpretation`
- `POST /api/rules/{item_id}/interpretation`
- `POST /api/problems/{item_id}/interpretation`
- `POST /api/entrypoints/{item_id}/interpretation` — the entry point's record: What, Where, How, State, Next; an agent writes it only from the chat that chose the topic last with `#entrypoint` (made it, chose it in answer to the question, or typed its exact name), and only on a topic of its chat's project. `item_id` may be the id the hook named for the command; 409 while the operator has not chosen its topic. Each version keeps its chat (`by`, `command` in `kept.versions`); `kept.renames` lists each change of the topic's name, oldest first (`at`, `old`, `new`, `agent_id`, `command_id`). No word limit: at most 200 000 characters (the file size guard), where the other lenses take 20 000
- `POST /api/artifacts/{item_id}/interpretation`
  — all five: body `text` (at most 20 000 characters; an entry point's record 200 000), `note?`. Answers: `metadata`, `kept` (the
  versions). 422 if the entry was posted rather than kept, since then its
  text belongs to `update_entry`.
- `POST /api/problems/{item_id}/rule` — the operator writes a rule on the
  basis of a problem. Body: `text`, `title?`. Answers: `metadata`, `kept`.
- `GET /api/examples/state` — the example vision, rule, problem and skill
  ids: `present`, `removed`, `all`.
- `POST /api/examples/remove` — take the examples out. Answers: `removed`.
- `POST /api/examples/restore` — put them back. Answers: `added`.

**Publish** (`#publish`, the operator's: what shipped, worth telling): the
cards are the kept kind `publish` (`GET /api/publish`, `GET /api/publish/{id}`,
`POST /api/publish/{id}/update` — `tags`; `POST /api/publish/{id}/interpretation` is
the operator's edit of the text, the same as the page's `text` route); an agent's
write there is refused: it writes a card with MCP `publish_write`. The Publish page reads and writes under
`/api/publishing` (docs/publish.md): `GET /api/publishing?project=` (the
cards with their sources, text and context versions, and what was attached
— tasks, notes, commits, files, images, links — and placements; the
documents with their versions and items) ·
`POST /api/publishing/cards/{card_id}/write` (`text?`, `context?`, `note?`,
`base?`, `tasks?`, `notes?`, `commits?`, `links?`, `files?`, `images?`,
`merge?` — the agent with MCP `publish_write`, or the operator) ·
`POST /api/publishing/cards/{card_id}/merge` (`into`; the operator's) ·
`POST /api/publishing/sources/{source_id}/remove` (a merge taken back, or an
appended message dropped; the operator's) ·
`GET /api/publishing/cards/{card_id}` (with `history`) ·
`POST /api/publishing/cards` (`project`, `text`: a card written by hand on the page) ·
`POST /api/publishing/cards/{card_id}/text` (`text`, `note?`) ·
`POST /api/publishing/docs` (`project`, `name`; the same name answers the
existing document) · `POST /api/publishing/docs/{doc_id}/update` (`name?`,
`archived?`) · `POST /api/publishing/docs/{doc_id}/versions` (`note?`; the
current items copied) · `POST /api/publishing/docs/{doc_id}/items`
(`card_id`, `text?`, `before?`) · `GET /api/publishing/docs/{doc_id}/markdown`
(`n?`) · `POST /api/publishing/items/{item_id}/update` (`text?`, `before?`) ·
`POST /api/publishing/items/{item_id}/remove` ·
`POST /api/publishing/cards/{card_id}/attach` (attachments only, as `write`
takes them on the operator page. Agents use MCP `publish_write`. The same
attachment again is the existing one) · `GET /api/publishing/attachments/{attachment_id}/file` ·
`POST /api/publishing/attachments/{attachment_id}/remove` (the operator's).
- `GET /api/example` — the example project: `enabled`, `present`, `building`
  and the last error.
- `GET /api/example/source?agent_id=&date=&time=&kind=` — the chat message
  an entry of the example project was written after; `kind` names the
  command (scan, decision, standup, task). Answers: `source`.

Skills are kept entries with files. The ledger row is the lens; the folder
is on disk, and installing writes a copy into a project.

- `GET /api/skills` · `GET /api/skills/{id}` · `POST /api/skills` ·
  `POST /api/skills/{item_id}/update` — the lens trio plus lifecycle.
- `POST /api/skills/new` — a skill written on the Skills page. Body:
  `skill_md`, `files?`, `project?`, `tags?`.
- `POST /api/skills/{item_id}/draft` — the next version. Body: `agent_id` or
  `actor`, `skill_md`, `files?`, `note?`. This is the MCP tool `skill_draft`.
- `GET /api/skills/{item_id}/versions/{n}` — one kept version.
- `POST /api/skills/{item_id}/install` — body: `project`, `dry_run?`,
  `force?`; writes the current version into the project's skill folders.
- `POST /api/skills/{item_id}/uninstall` — body: `project`, `force?`.
  Answers: `removed`.
- `GET /api/skills/{item_id}/copy?project=` — the copy as it is on disk, and
  which files differ from the current version.
- `POST /api/skills/{item_id}/keep-disk` — a copy was edited on disk: keep
  it as the next version. Body: `project`, `path?`.
- `GET /api/skills/found` — skill folders on this machine Slightly Parallel does not
  keep, and where they sit. Answers: `found`.
- `POST /api/skills/import` — body: `path`, `tags?`; takes a folder in
  without changing it. Answers: `skipped`.
- `GET /api/skills/usage` — uses per skill, and skills that ran but are not
  in Slightly Parallel.
- `POST /api/skills/usage/backfill` — read skill uses out of past Claude
  Code logs into the captured chats.

A built-in skill template may hold `{{part:<key>}}`; seeding puts that
contract part's body there (`{{writing-rules}}` is `{{part:writing}}`), so a
skill and the contract have one source. Built-in skills: `make-a-scan`,
`keep-the-architecture-page`, `map-the-program`, `update-the-architecture`,
`daily-standup`, `log-a-decision`, `write-a-task`, `task-evidence`,
`make-an-artifact`, `finish-a-task`, `sp-help`.

---

## Messages between agents

One ledger, `<data root>/messages.csv`: `id` (`msg_…`), `project`,
`from_agent` (an agent id, or `operator`), `to_agent`, `text`, `sent_at`,
`reply_to`, `delivered_at`, `delivered_via` (`codex`, `terminal`, `stop`, `hook`, `inbox`),
`landed_at` and `landed_turn` (the prompt the marker came in as),
`read_at`. Each message is taken once, by the first way that reaches it.

- `POST /api/messages` — `{to, text, reply_to?}`; an agent's through the MCP
  tool `message` (`agent_id` stamped), the operator's from the page (no
  agent). 404 for an unknown chat or `reply_to`, 422 for an empty text, one
  over 8,000 characters or one to itself. For Codex, the server matches the captured full thread UUID against
  the threads loaded on the local app-server under the server user's
  `CODEX_HOME` (default `~/.codex`). It sends a marker asking the chat to
  read its inbox with `turn/start` or, during a turn, `turn/steer`. The
  ledger reserves the wake before sending. An uncertain send is checked in
  thread history before another path may deliver the notice. The notice is
  also typed into a verified empty terminal input, announced on the next
  operator prompt or announced once at Stop when supported. The inbox
  supplies the body. Answers `{message, delivered_via,
  typed, waiting}`.
- `POST /api/messages/inbox` — `{agent_id}` (the MCP tool `messages`): the
  chat's `unread` messages, marked read now, then its `recent` read ones
  (`?recent=`, default 10).
- `GET /api/messages?agent_id=&project=&limit=` — the ledger, newest first
  (one chat's sent and received, one project's, or all). No write.
- `GET /api/messages/{message_id}` — `{message, thread}`. The thread is the
  connected replies between the same two participants, in ledger order.
  Returns 404 for an unknown message. Does not mark messages read.
- `GET /api/messages/terminal?agent_id=&terminal=` — `{types}`: whether
  this server types the calling chat's waiting messages into that terminal.
  Claude Code's Stop hook sends a proof for its own chat and data root in
  `X-SP-Stop-Proof`. With `types: true`, the terminal delivers the notice
  once input is empty and copy mode has ended. Otherwise the Stop block
  opens with a line saying the message is not an error. The lookup changes
  no files and types nothing.

The inbox delivers each message body once. An automatic terminal wake is
best effort. If the server crashes mid-send and the paste may already have
reached the terminal, the message stays available on the next prompt or in
the inbox. A late terminal notice after that delivery is ignored.
If an exact late notice starts a submission, capture keeps the operator's
text that follows and processes its commands normally. A notice quoted
elsewhere in the submission stays in the operator's text.

The capture hook reads a prompt that opens with the marker as the sender's
message only when the ledger holds that id, for this chat, from that
sender, not taken before; it keeps the turn as
`<sp-message from="…" id="…">…</sp-message>` in chat.md, so no tag in it
acts. A marker the ledger does not know is the operator's text.

## Notes

Notes are written by agents through the MCP tools and read back by them;
the marks, comments and the archive are the operator's.

- `GET /api/notes/list?project=&task=` — one line per note (the MCP `notes`
  tool).
- `GET /api/notes/images/{image_id}/file` — a picture of a note.
- `POST /api/notes/write` — writes a note, or a new version of one: `{agent_id,
  project, title?, kind, text, task_id?, entrypoint_id?, replaces?, id?, base?,
  images?}`. MCP `note_write`.
- `POST /api/notes/{note_id}/images` — adds a picture: `{agent_id,
  data_base64, caption?}`. MCP `note_image`.
- `POST /api/notes/{note_id}/marks` — the operator's tick, answer or copy on
  an item: `{item, kind: tick|answer|copy, value}`.
- `POST /api/notes/{note_id}/archive` — `{archived: bool}`, the operator's.
- `GET /api/notes/feed` and `GET /api/notes/{note_id}/full` include a
  `comments` array for the notes returned. `GET /api/notes/{note_id}/agent`
  includes the same comments for the MCP `notes` tool.
- `POST /api/notes/{note_id}/comments` adds an operator comment. Send
  `{text, item?, section?, request_id?}`. Text is limited to 2,000 characters.
  Omit `item` for a note-level comment. Supply the section title when the same
  item text appears in multiple sections. Keep the same `request_id` when
  retrying a submission. The returned `comment` records the original label,
  section and note version.

## Pins, carried messages and forks for later

Three lists of marked messages, one route set each (`pins`, `carries`,
`forks`). A mark is the operator's: typed as `#pin`, `#carry`,
`#carry-brief` or `#fork-later` in a chat, or set here by hand.

- `GET /api/pins` · `GET /api/carries` · `GET /api/forks` — the marks of that
  list in force (`?project=&agent_id=&q=&full=1`), after adopting any new tag.
- `POST /api/pins` · `POST /api/carries` · `POST /api/forks` — marks a message:
  `{chat_agent, turn, side?, project?, session_id?, excerpt?}`; a carry also
  takes `level`: `carry` or `brief`. 201.
- `POST /api/pins/remove` · `POST /api/carries/remove` ·
  `POST /api/forks/remove` — takes the mark off: `{target}`
  (`<agent_id>#<turn>` or `<agent_id>#<turn>/reply`).
- `POST /api/forks/state` — a fork's state: `{target, state}`, where state is
  `""` (waiting), `started` or `dropped`. 404 when the message has no
  fork-later mark.
- `POST /api/carries/brief` — the brief of a `#carry-brief` message: `{target,
  text, agent_id}`. An agent's write, through the MCP tool `carry_brief`, for
  a message of its own chat only (403 for another chat's, a branch's parent
  included).

## Artifacts

An artifact is a folder the agent wrote, with a record in the ledger.

- `GET /api/artifacts` · `GET /api/artifacts/{id}` · `POST /api/artifacts` ·
  `POST /api/artifacts/{item_id}/update` — the lens trio plus `status`,
  `tags`.
- `POST /api/artifacts/new` — register a folder the operator made. Body:
  `project`, `name`, `kind`, `description`, `tags?`.
- `POST /api/artifacts/{item_id}/write` — the agent writes the folder and
  the record together (MCP `artifact_write`). Body: `agent_id` or `actor`,
  `name`, `kind`, `description`.
- `GET /api/artifacts/{item_id}/tree` — the folder listing. Answers: `id`,
  `path`, `tree`.
- `GET /api/artifacts/{item_id}/files/{path}` — one file, for previews; HTML
  is served sandboxed.
- `POST /api/artifacts/{item_id}/interpretation` — see **Kept messages**.

---

## Architecture

The architecture **ledger** is the log of what each scan changed. The
architecture **page** is the picture: what the project is, what it does now,
what it is made of and what is owed, for a team lead who was not in the
chat. One page per project, kept in versions under
`projects/<project>/architecture/vNNN.md`, in two layers.

*Computed facts* (`projectfacts.py`), with no model in the loop: `standing`
(active · paused · dormant, from the last file change against today), size,
every top-level folder with its size and last change, the newest files, the
git history with recent commit subjects, nested repositories, build files,
and what Slightly Parallel holds for the project: the data root, open tasks, recent decisions.

*Claims* (`archpage.py`), written by the agent that works in the project.
Each item reads `name — what it is · where: <path> · seen: <how the writer
knows> · made by: … · checked by: …`. The server parses them leniently,
checks every `where` against the project folder, and on read marks a claim
whose file changed after the version was written.

- `GET /api/architecture` · `GET /api/architecture/{id}` ·
  `POST /api/architecture` — the ledger trio. A create is one answer to
  "what did you do to the shape?" Body: `project`, `agent_id`,
  `created_date`, `created_time`, `trigger_lens`, `trigger_id`, `checked`,
  `changes`. Answers: `posted`, `ids`, `skipped`, `existing`, `checked`,
  `check_id`, `trigger_id`, `warnings`.
- `GET /api/architecture/page?project=&version=` — answers: `page`
  (`n`, `at`, `agent_id`, `note`, `text`, `sections[{title, body, claims[]}]`,
  `counts`), `versions`, `facts`, `word_budget`, `project`. `page` is null
  until one is written; the facts are there either way.
- `POST /api/architecture/page` — the whole next version (MCP
  `architecture_page`). Body: `project`, `agent_id`, `text`, `note?`.
  Refused without the required headings or with no claim at all. Answers:
  `project` plus `warnings`: paths not found, how many items lack `seen:`,
  words over the budget. The same text twice is one version.
- `GET /api/architecture/page/material?project=&agent_id=&cwd=` — what the next version is
  written from (MCP `architecture_material`). Answers: `project`, `facts`,
  `current_page`, `check_again` (claims not found or changed since), `next`,
  `instructions` — the contract part `architecture-page`.
  With `agent_id`, a project that is not one of that chat's projects is
  refused (403, the membership line); with `cwd`, `folder_warning` says when the
  project's registered folder is not where the chat works (a warning only).
- `GET /api/architecture/state?project=` — the screening: scans newest
  first, each with its answer.

Command `#page`; built-in skill `keep-the-architecture-page`; `make-a-scan`
updates the page as its last step when the scan changed the picture.

The **map** is the third part, for projects that are programs: every part as
a row of one kind, and what connects to what (`repomap.py`). A closed list of
twenty row kinds (runtime, framework, library, entry, surface, api, module,
service, store, data-in, data-out, external, config, build, deploy, test,
auth, job, model, step), a template per kind of program (web-service, app,
tool, library, pipeline, research, site) naming the kinds it must answer, one
column set (`kind, name, what, where, version, evidence, note`), and
relations `from · verb · to` over a closed list of verbs. Kept in versions
under `projects/<project>/map/vNNN.json`. The framework was tested on four
repositories of four kinds: every path found, every kind and verb in the
vocabulary, every relation naming a real row.

- `detect(root)` reads with no model in the loop: languages, manifests and
  what they declare, build and CI files, compose services, test folders,
  environment variables the code reads, ports it names, git.
- `GET /api/architecture/status?project=` — MCP `architecture_status`: what
  `#architecture` has to do. `form`, `page`, `map`, each `needed` with `why`:
  the last scan without its form, a scan newer than the page, the program's
  shape changed since the map (or no folder, so no map).
- `GET /api/map?project=&version=` — answers: `map` (`n`, `at`, `agent_id`,
  `note`, `template`, `map{rows, relations, notes}`, `changes{added,
  removed}` since the version before, `problems`, `by_kind`), `versions`,
  `kinds`, `verbs`, `templates`, `facts`, `project`.
- `GET /api/map/material?project=&agent_id=&cwd=` — what the next version is written from
  (MCP `map_material`). Answers: `facts`, `current_map` with its problems,
  the vocabulary, `model` (Settings › Agents), `next`, `instructions` — the
  contract part `map`.
  With `agent_id`, a project that is not one of that chat's projects is
  refused (403, the membership line); with `cwd`, `folder_warning` says when the
  project's registered folder is not where the chat works (a warning only).
- `POST /api/map` — the whole next version (MCP `map_write`). Body:
  `project`, `agent_id`, `map`, `note?`. Refused for a kind or verb outside
  the vocabulary, an unknown template, over 50 rows or 30 relations. Answers
  with `warnings`: a template kind not answered, a path not found, a relation
  naming no row, too many rows of one kind. The same map twice is one version.

Command `#map`; built-in skill `map-the-program`. The agent asks the operator
first, because mapping reads up to 40 files, and a helper agent on
`map.model` maps. The standup's own ask offers both helpers as numbered
choices; a day's numbers list the map versions written that day.

---

## Standups and scans

The standup is the project's, not an agent's: one per day, built from every
chat of that day, written the next time anyone works on the project
(`standuplib.py`). It is an ordinary entry that says which day it covers in
`for_date`; an older one names none and covers the day before it was written.

- `GET /api/standups` · `GET /api/standups/{item_id}` · `POST /api/standups`
  — the lens trio. A standup is written by name: `summary`, `deviation`
  (what went wrong), `movement` (what moved), `story` (the day told),
  `decisions`, `forgotten` (maybe forgotten), `detail`, and `for_date`.
- `POST /api/standups/{item_id}/update` — a standup can be rewritten whole,
  its `summary` too. An update that sends some of `story`, `decisions`,
  `forgotten` and `detail` keeps the others.
- `GET /api/standups/calendar?project=&month=YYYY-MM` — every day of the
  month with its numbers, counted with no model (`daynumbers.py`):
  `messages_n`, `chats_n`, `agents`, `session_minutes`, `tasks_created_n`,
  `tasks_done_n`, `tasks_moved_n`, `commits_n`, `files_n`, `lines_add`,
  `lines_del`, `tracked_minutes`, `decisions_n`, `standup_id`. A drag on the
  board is not a change. The Standups page draws its month from it.
  `material` carries the same `numbers` for its day plus `tasks_changed`,
  every task that changed that day with each change.
- `GET /api/standups/material?project=&date=&clip=` — MCP `standup_material`;
  `date` defaults to yesterday. Answers: `next`, `instructions` (the
  contract's "How to write it" and "Standup" parts), `model` and `ask_first`
  from Settings, plus `standup_id` when the day is written, `claimed_by`
  when another agent is writing it, `postponed`, `messages_n`, `chats_n`,
  `chats` — every message and answer of the day by chat, whole, with the
  commits each turn made (`clip=1` trims each one) — `clipped`, `chars`
  (the day's size in characters, whole and trimmed), `previous` (the last
  standup before this day, for continuity), `numbers` and `tasks_changed`.
- `GET /api/standups/day?project=&date=` — what the Standups page shows
  beside a standup's text, from the record, with no model: `tasks` (moved
  that day or named in a chat, each with its `moves` and `agents`),
  `agents` (chat, from and to, `turns_n`, `commits_n`, `agent_min`, the
  tasks, and `tool`, `cwd`, `session_ref` to resume it) and `created`
  (what the day created: `kind`, `id`, `title`).
- `POST /api/standups/claim` — body: `project`, `date`, `agent_id`. The
  first claim stands for 45 minutes. Answers: `claimed`, `standup_id`, `why`.
- `POST /api/standups/postpone` — body: `project`, `date`, `hours` (MCP
  `standup_postpone`).

Both facts live in `standup_state.json`, which the capture hook reads: the
first message of a day gets `[slightly-parallel] No standup for …` unless the day is
written, claimed or postponed. Settings: `standup.ask` (ask the operator
first, on by default), `standup.model` and `map.model`.

A decision carries `weight` — `minor · normal · major`, what undoing it
would cost — and the write warnings follow it: a minor one owes nothing
more, a normal one its alternatives, a major one also what would undo it.

- `GET /api/scans?project=` · `GET /api/scans/{scan_id}` · `POST /api/scans`
  — the scan trio; a scan is a checkpoint with a snapshot beside it.
- `POST /api/scans/{scan_id}/update` — correct one by name. Body: `summary`,
  `why`, `deltas`, `proof` (the `l1`…`l4` slots are still accepted).
  Answers: `changed`, `metadata`, `text`.
- `GET /api/logs?level=&limit=` — the server's log summed up (uptime, data root,
  rebuilds, requests by path with p50 and max, errors) and the last lines;
  `GET /api/logs/text` is the same as plain text, for the health page's copy
  button and for `curl`.
- `GET /api/checkup?cwd=&agent_id=` — `#sp`: is Slightly Parallel working for
  this chat and folder (checkup.py). `verdict`, `counts`, and `findings`, each
  with `status` (`ok`, `note`, `concern`, `unknown`), `title`, `evidence` and
  `next`: the folder's project, this chat recorded, MCP (ok only when the call
  came through the MCP tool `checkup`), capture, the contract block, hooks,
  skills, data, disk, backups, the server's memory, errors and slow requests.
  Each finding that is not fine also carries its `reason` (`chat.capture_stale`,
  `hooks.script_missing` …) and `recipe` — how to confirm, who acts (the agent
  after a yes, or only the operator), the steps, how to verify — and the answer
  the `rules` every recipe keeps (checkup_fixes.md). Reads only. `python sp.py
  check` prints it, and looks from outside when the server does not answer.
- `GET /api/checkup/fix/{reason}` — one recipe by its reason, with the rules;
  404 names the reasons there are.
- `GET /api/diagnostics/report` — one Markdown file to send when something is
  wrong (diagnostics.py), as an attachment: the machine, the server's memory
  now and at its peak, memory and load hour by hour for a day and the
  monitor's events (from the monitor), the log's memory lines, slow requests
  and warnings, the capture hooks' errors, the data's size and the tools'
  transcripts, the settings, the supervisor's output, and this summary. No
  chat text, no values from `.env`, query strings cut; home paths written from `~`. `python sp.py
  report` writes the same file, and builds it from the files alone when the
  server does not answer.
- `GET /api/capture/health` — is capture working (capturewatch.py): `missed`, `lost` (sessions of the last week, Claude Code or Codex, never recorded),
  the active Claude Code sessions in folders registered in Setup whose latest
  messages Slightly Parallel did not record (or never saw); `errors`, hook failures of
  the last day (`<data root>/.capture/errors.jsonl`); `ok` when neither.
- `GET /api/capture/import?project=&tool=` — the sessions of that project and tool (claude, codex) that
  nothing recorded and that can be read from the tool's own log (sessionimport.py): one row each,
  with its turns, first and last time and first message. Writes nothing.
- `POST /api/capture/import` `{project, tool, sessions?}` — import them as chats, marked
  `capture: import`: the chat only; a tag in an old message is never carried out. A session
  recorded meanwhile, or active in the last hour, is skipped.
- `POST /api/capture/ignore` `{project, tool, ignored}` — the operator says a tool (claude, codex,
  opencode, cursor) needs no recording in a project, or takes it back: its `lost`
  sessions stop warning and Setup drops its Connect line (`.capture/ignored.json`).
- `GET /api/monitor/now` — the system monitor (sysmon.py): the latest reading
  (`sample`), the last few minutes (`spark`), the connection check (`ping`),
  events still going on (`open`), today's counts by severity, `unseen`, what
  the monitor itself costs (`cost`), `host` facts, and the `topbar` setting.
- `GET /api/monitor/series?range=` (15m · 1h · 6h · 24h · 7d · 30d · 90d · 1y)
  or `?from=&to=` (unix seconds) — every measure over the span, about 400
  points from the finest tier that holds it: `series` columns (averages, and
  `*_max` peaks), `gaps`, and the `events` in the span.
- `GET /api/monitor/events?since=&until=&severity=&kind=&q=&limit=&days=` —
  unusual events, newest first; `days=N` adds per-day counts with the worst
  severity (`days`) and the days the monitor was reading (`watched`).
- `GET /api/monitor/events/{event_id}` — one event, with the readings and the
  heaviest processes of its moment.
- `GET /api/monitor/processes?sort=rss|cpu&limit=` — the heaviest processes
  and programs (processes summed by name) at the last scan.
- `GET /api/monitor/storage` — the record's file, size and rows per tier.
- `POST /api/monitor/events/{event_id}/seen` · `POST /api/monitor/events/seen`
  — mark one or all seen. `POST /api/monitor/clear` — body `what` ∈ samples ·
  events · all. The operator's only.
- `GET /api/analytics/schema` — analytics (analytics.py): the tables you can
  query — `messages`, `chats`, `tasks`, `task_events` — their columns, row
  counts, and example queries.
- `POST /api/analytics/query` — body `sql`: one SELECT or WITH, run on an
  in-memory copy with no file access, 10 seconds and 5000 rows at most;
  `{columns, rows, truncated, ms}`, or 422 saying what is wrong.
- `GET /api/stats/tasks?project=` — task statistics (statslib.py): one row per
  task on the board — `messages`, `chats`, `minutes` (active
  time in the chat), `agents`, `commits`, `files`, `add`, `del`, `created`,
  `first`, `done_at`, `lead_hours`, `work_hours`, `closed` (#done · board),
  `stretch` (done: exact, from #done · estimated · none), `reopened`, `reports`,
  and the board's side: `priority`, `assignee`, `impact`, `effort`, `tags`, `lane`,
  `due`, `starred`, `archived`, `age_days`, `in_status_days`, `status_since`,
  `moves`, `edits`, `named_in` (chats) and `activity` (the last 91 days, oldest
  first, today last).
- `GET /api/done-tags?agent_id=` — `#done` (donelib.py): applies every `#done`
  not applied yet (the task moves to done as the operator's move) and answers
  what this agent's latest `#done` did: `tasks` (each with `result` moved ·
  already · archived and its `stretch`), or `unnamed` when no task was named
  since the previous `#done`, and `next`. The MCP tool `task_done` reads it.
- `GET /api/done-tags/capture?agent_id=&capture_root=&capture_turn=` — the
  exact turn's outcome for the capture hook. A different data root returns
  409. When IDs need confirmation, the outcome includes `doubt` with each
  ID and reason and `confirmation` with the ready command.
- `POST /api/done-tags` — the same answer, and the next tasks offered after it
  (nextlib.py, [next-tasks.md](next-tasks.md)). Body: `agent_id`, `proposals`
  (at most three `{title, line}`; absent, null or `[]` answers exactly as the
  GET). Each proposal comes back with `n` and `similar` (up to three open tasks
  of the project: `id`, `title`, `status`, `score`), with `offer` (its id) and
  `show`, the line the agent gives the operator. A wrong shape or a fourth
  proposal is 422 before anything is applied. No offer where it does not belong
  (the `#done` closed nothing, the operator has written since, a helper chat,
  an offer already made into tasks): `proposals_ignored` says why. The MCP tool
  `task_done` posts here when it carries proposals.
- `POST /api/next-tasks/make` — the operator answered the offer: makes the
  tasks they chose in the `agent` column (tag `ag_followup`, the offer's
  project). Body: `agent_id`, `numbers`. Checked against the operator's next
  message in the chat: numbers only there must be the numbers sent; "yes" or
  "all" means every one; a command or a question chooses nothing (`skipped`);
  other text must contain each number sent. 409 when the operator has not
  answered yet or did not write a number sent. A retry answers the same tasks
  (`existing: true`). The MCP tool `next_tasks` posts here.
- `GET /api/next-tasks?project=&agent_id=` — every offer (`next_tasks.csv`):
  `state` offered · made · skipped, the proposals with their similar tasks,
  the `#done` turn and the tasks it closed, `chosen`, `made`; an offer still
  `offered` carries `answer_in_chat`, the operator's next message as read
  (`turn`, `kind`, `numbers`), or null. Reads only.
- `GET /api/undo/candidates?agent_id=` — `#undo` (undolib.py): this chat's live
  `#undo` request (`said`: the operator's words) and the entries it could mean,
  numbered, this chat's first. 409 when the chat has no `#undo` request. The MCP
  tool `undo_find` reads it.
- `POST /api/undo/propose` — the entries the operator chose. Body: `agent_id`,
  `ids`. Answers `confirm`, the text the agent shows, ending with the reply that
  confirms (`#undo-yes`). Archives nothing. 409 without a live request.
- `POST /api/undo/apply` — archives the proposal, only when the operator's next
  message after it carries `#undo-yes`; any other next message cancels the
  request (409). Body: `agent_id`. A rule, skill, artifact or prompt takes its
  `archived` status; a vision, problem or entry point gets `archived_at` and
  leaves the list reads (`?include_archived=1` reads it) and the sets written
  into AGENTS.md; a task gets `archived_at`.
- `POST /api/undo/restore` — brings one archived entry back with the status it
  had. Body: `id`, `agent_id?`.
- `GET /api/undo` — every `#undo` request (`undo.csv`): `state` open · proposed ·
  done · cancelled, the proposal, the turns and what was archived.
- `GET /api/tasks/{task_id}/done` — the task's stretches of the chat, each from
  its first message to the `#done`: `turns`, `chats`, `minutes`, `first`,
  `done_at`; and `reopened` when it left done after.
- `GET /api/marks?project=` — the ★ in force: agents, tasks and messages marked
  important, newest first, each with what it points at (`task`, `agent`).
  Adopts any new `#important` tag in the chats first. A task's star is its
  `remember` field, the board's ☆.
- `POST /api/marks` — star one thing by hand. Body: `kind` ∈ agent · task ·
  message, `target` (agent id, task id, or `<agent_id>#<turn>`), `project?`,
  `agent_id?`, `session_id?`, `turn?`, `excerpt?`. The operator's only.
- `POST /api/marks/unmark` — body: `kind`, `target`. Answers: `removed`.
- `GET /api/scans/page?limit=` — the scans page in one answer: every scan with
  its text, its file entry (`file`: metadata and the annotated `paths`) and
  the id of its architecture form, plus `architecture` rows and `agents`.
- `GET /api/scans/material?project=&agent_id=&cwd=` — MCP `scan_material`: what a
  scan is written from (`scanlib.py`). The window is the asking agent's
  own: the commits this chat made since this agent's last scan of the
  project (by the capture hook's stamps) and what is not committed. Another
  agent's commits in the same repository are counted apart
  (`others_commits_n`); a chat the hook never stamped gets the project's
  commits since the last scan, and `window` says which. Answers: `window`,
  `last_scan`, `repo`, `commits`, `commits_n`, `files` with line counts,
  `uncommitted`, `touched` and `changed` (the files this chat's tools
  changed, git or no git; without git they are the count), the `counters`
  (`files_n`, `lines_add`, `lines_del`, `decisions_n`) already counted,
  `instructions` for the scan, its file entry and its architecture form,
  and `next`. A scan may describe work not committed yet: writing one stores
  what was uncommitted (`scan_marks.json`), and commits made right after
  that hold only those files come back under `already_described`, outside
  the counters.

### Hook parity

Every command of the contract gets a `[slightly-parallel] #<command> — …` notice from
the capture hook, naming the skill and the first tool: the kept tags,
`#evidence` with its task, and `_COMMANDS` for the rest (`#scan`, `#page`,
`#map`, `#architecture`, `#task`, `#now`, `#decision`, `#standup`, `#prompt`,
`#problem solved`, `#core-new`, `#core-note`, `#core`, `#core-off`, `#mute`). The hook also keeps small copies of server facts — the
task id pattern, the standup claim time, setting defaults, kept-tag routes,
whether a standup is owed. `tests/test_hook_parity.py` holds each copy equal
to its original, so a contract that gains a command the hook does not know
fails the suite.

---

## Prompts

Two different things share the word. **Contract parts** are the files under
`prompts/contract/` that compose `SLIGHTLY-PARALLEL.md`. The **library** is the
operator's own prompts, harvested from messages tagged `#prompt`.

Contract parts, addressed by `key`: `contract` is the whole contract,
`contract.<part>` one of its parts (`contract.task`, …), `agents-block` the
AGENTS.md template. `merkhet` and `merkhet.<part>` — the keys before the
product was renamed — still answer, as the same records, and a data root
that kept its versions under `prompts/merkhet*/` keeps using those folders.

- `GET /api/prompts` — every prompt file with its size, whether it differs
  from the original, and its label. Answers: `files`.
- `GET /api/prompts/{key}` — the live text plus the version list, newest
  first.
- `POST /api/prompts/{key}` — replace the live file (for a part, its body).
  Body: `text`, `note`, `enabled`. The content it replaces is kept.
- `POST /api/prompts/{key}/restore` — body: `version` (`"original"` or a
  version id).
- `GET /api/prompts/{key}/versions/{vid}` — one kept version, read-only.
  Answers: `key`, `id`, `text`.

A contract part may carry `brief:` in its frontmatter: the composed contract
then shows the brief, and the whole body reaches an agent through the tool
and the MCP prompt. The scan, file-entry and architecture parts do.

The library:

- `GET /api/prompt-library` — the library newest first, each row with its
  use count, `preview` (the first 400 characters) and `text` (the whole
  current wording). Harvests on the way past.
- `POST /api/prompt-library` — write one by hand. Body: `title`, `text`,
  `tags`, `project`.
- `GET /api/prompt-library/{prompt_id}` — one prompt: every version, the
  notes on each, and where it was used.
- `POST /api/prompt-library/{prompt_id}/update` — the row's own fields, not
  its text. Body: `title`, `tags`, `status`, `marks`.
- `POST /api/prompt-library/{prompt_id}/version` — a rewrite kept beside the
  ones before it. Body: `text`, `note`.
- `POST /api/prompt-library/{prompt_id}/versions/{n}/rating` — judge one
  wording. Body: `task_success`, `regression`, `intervention`, `score`,
  `note`.
- `POST /api/prompt-library/{prompt_id}/runs/{session_id}/{turn}` — judge
  one run, same body.
- `GET /api/prompt-library/candidates?min_sends=` — messages sent again and
  again that were never filed. Answers: `candidates`, `min_sends`.
- `POST /api/prompt-library/candidates/{cluster}/keep` — file one: the
  newest wording becomes version 1, the sends stay behind it.
- `GET /api/prompt-library/marks` — every send of every prompt, by chat
  then turn, for any chat reader. Answers: `marks`.

The judgments are also a lens: `GET /api/prompt-runs`,
`GET /api/prompt-runs/{id}`, `POST /api/prompt-runs`,
`POST /api/prompt-runs/{item_id}/update`.

The `prompt` lens itself (`POST /api/prompts`,
`POST /api/prompts/{item_id}/update`) writes the harvested rows. Its list
and detail routes are **shadowed** by the contract-part routes above, which
are registered first and answer `/api/prompts` and `/api/prompts/{key}`;
read the harvested prompts at `/api/prompt-library`.

---

## Operator-only admin

Setup, settings, backups and the operator's own surfaces. The MCP gate does
not apply here because agents never call these.

### Setup

- `GET /api/projects/folders` — `{folders: {project: absolute path}, data_root}`,
  read from `integrations.csv`. The pages show a path the way the agent wrote
  it, relative to the project folder; copying it gives the absolute path,
  joined in the frontend (`lib/paths.tsx`: `ProjectFolder` gives a page its
  project's folder, `useFolder` reads it however deep, `absolutePath` joins
  the two and leaves a path that is already absolute, a home path, a URL or
  prose alone).


- `GET /api/setup/info` — everything the Setup page needs. Answers:
  `data_root`, `app_root`, `api_url`, `contract_path`, `contract_exists`,
  `data_projects`, `integrations`, `adapters`, `codex`, `tools_installed`,
  `computer` (start at login and the shortcut: each `on` and its `paths`;
  `system`; `sandbox`).
- `POST /api/setup/data-root` — switch the data root: persisted to `.env`
  and hot-swapped in the running app. Body: `path`. Answers: `data_root`,
  `env_file`, `restart_required`.
- `POST /api/setup/integrate` — write or refresh the integration block in a
  target project. Body: `project_code`, `project_dir`, `notes`, `dry_run`,
  `write_agents`, `write_claude_bridge`, `write_claude_hooks`,
  `write_codex_hooks`, `write_mcp`, `write_opencode_plugin`, `autostart`,
  `shortcut` (true turns it on; false leaves it as it is). Answers:
  `project_code`, `project_dir`, `dry_run`, `results`.
- `POST /api/setup/computer` — start at login and the shortcut on this
  computer (Settings › On this computer). Body: `autostart` and/or
  `shortcut`, each true or false. Answers: `changed` (the files written or
  removed), `computer`. A test server (`SP_SANDBOX=1`) answers 409.
- `POST /api/setup/codex` — install or remove the global Codex notify hook.
  Body: `action`, `dry_run`. Answers: `action`, `file`, `file_action`,
  `line`, `status`.
- `POST /api/setup/forget` — disconnect: drop the registry row and undo
  every file Setup wrote. Body: `project_code`, `path`. Answers:
  `forgotten`, `path`, `agents_md`, `claude_md`, `hooks`, `sets`.
- `POST /api/setup/delete-data` — archive everything Slightly Parallel holds for a
  project into `.trash/`. Body: `project_code`, `confirm` (must repeat the
  code). Holds the membership ledger's lock from its check to the trash.
  Refused (409, writing nothing) while the project holds the chat of an
  agent that is a member of other projects: `detail` names them, `held` is
  `[{agent_id, also_in}]`, the projects each chat can move to
  (`POST /api/agents/{agent_id}/move-chat`). Members from elsewhere get a
  `leave` row, value `project deleted`; the answer lists them in `left`.
  `GET /api/setup/info`'s `data_projects` carry the same `held` per project.

### Settings, preferences, doctor

- `GET /api/settings?environment=` — the full schema, grouped, with current
  values; the page renders from it.
- `POST /api/settings` — body: `values`, e.g.
  `{"agent.contract_refresh_turns": 30}`. Answers: `saved`, `values`.
- `GET /api/prefs` — the UI's own preferences.
- `POST /api/prefs` — body: `values`; merge, and a null value deletes the
  key. Answers: `saved`, `total`.
- `GET /api/doctor` — fsck for the data root, read-only: every CSV's
  structure (ragged rows, blank and duplicate ids), every row against the
  reader that consumes it, every `md_ref`, and vocabulary drift in
  filtered-on fields. Answers: `ok`, `issues`, `errors`, `warnings`,
  `checked`, `truncated`, `generated_at`.

### Sets and integration

A set is a named list of rules written into a project's `AGENTS.md` as a
block, and kept current.

- `GET /api/sets?kind=` — saved sets in the order they were made.
- `POST /api/sets` — body: `name`, `kind`, `items?`; names may repeat, the
  id is minted.
- `POST /api/sets/{set_id}/update` — body: `name?`, `items?`; items replace
  the list, in the order given.
- `POST /api/sets/{set_id}/delete` — the set is forgotten; its entries are
  not touched. Answers: `deleted`.
- `GET /api/sets/{set_id}/integrations` — where this set was written.
- `POST /api/sets/{set_id}/integrate` — body: `project`, `dry_run?`.
  Answers: `action`, `file`, `content`, `previous`, `words`, `dry_run`.
- `POST /api/sets/{set_id}/integrate/remove` — body: `project`. Answers:
  `action`, `file`.
- `GET /api/integrations` — where every set was written, and whether each
  block is still current. Answers: `integrations`.
- `GET /api/integrations/targets` — the projects a set can be written into.
  Answers: `targets`.
- `GET /api/integrations/all-rules` — the built-in set: which rules, the
  exact block, and each project's copy. Answers: `items`, `content`, `words`,
  `projects`.
- `POST /api/integrations/all-rules/sync` — write it into every project now,
  for a copy changed by hand. Answers: `results`.

### Backups

- `GET /api/backup` — the ladder, the archives and the clock.
- `POST /api/backup/run` — take one now. Body: `kind` (`manual` | `auto`),
  `label`.
- `POST /api/backup/reveal` — open the backup folder in the file manager.
  Body: `name`. Answers: `opened`, `path`, `detail`.
- `GET /api/backup/{name}/download` — the archive itself.
- `POST /api/backup/{name}/trial` — a trial restore: verify, then unpack into
  a temporary folder and read it as the dashboard would (every file loads,
  the data check finds no error, each ledger's rows all readable). Answers
  `ok`, `problems`, `counts`, `seconds`; kept as the last check. Runs after
  every automatic backup.
- `GET /api/backup/checked` — the last trial restore (`checked`, or null).
- `POST /api/backup/{name}/verify` — re-hash it and read its table of
  contents; a backup counts as good only after a check.
- `POST /api/backup/{name}/restore` — put it back over the live data root.
  Body: `confirm`.
- `POST /api/backup/{name}/pin` — body: `pinned`; exempt from rotation.
  Answers: `archive`, `state`.
- `POST /api/backup/{name}/delete` — answers: `deleted`, `state`.

### Calendar, milestones and time

- `GET /api/calendar?project=&from=&to=` — everything dated on a project for
  a range of days, inclusive.
- `GET /api/calendar/entries?project=` — the operator's own dates.
- `POST /api/calendar/entries` — body: `project`, `kind`, `date`, `title`,
  `time?`, `end_date?`, `end_time?`, `body?`, `actor?`. Answers: `entry`.
- `POST /api/calendar/entries/{entry_id}/update` — any of `kind`, `date`,
  `time`, `end_date`, `end_time`, `title`, `body`. Answers: `entry`.
- `POST /api/calendar/entries/{entry_id}/delete` — answers: `deleted`.
- `GET /api/milestones?project=` — the outcomes tasks feed.
- `POST /api/milestones` — body: `project`, `title`, `outcome?`, `check?`,
  `target_date?`, `status?`, `tasks?`, `position?`, `actor?`. Answers:
  `milestone`.
- `POST /api/milestones/{milestone_id}/update` — any of `title`, `outcome`,
  `check`, `target_date`, `reached_date`, `status`, `position`.
- `POST /api/milestones/{milestone_id}/tasks` — body: `add?`, `remove?`,
  `actor?`; a task serves one milestone at a time. Answers: `milestone`.
- `POST /api/milestones/{milestone_id}/delete` — answers: `deleted`.
- `POST /api/time/start` — open a running entry; several may run at once,
  one per block. Body: `project`, `sprint_id`, `goal_id`, `note`,
  `share_pct`, `actor`, `task_id`. Entries the auto-timer writes carry
  `source: auto`; their share is the top-up above the manual timers.
  `started_at`, `ended_at` and `paused_at` are local ISO times with their
  UTC offset (`2026-11-01T01:30:00-07:00`); a time sent without one is
  read as local and stored with it. Rows from before the offset are given
  it once at start (`time-offsets-migration-<stamp>/` in the backup folder
  holds the file as it was).
- `POST /api/time/{entry_id}/pause` — hold the clock without closing.
- `POST /api/time/{entry_id}/resume` — bank the paused stretch, count again.
- `POST /api/time/{entry_id}/stop` — close it and freeze the duration.
  Body: `note`.
- `POST /api/time/{entry_id}/delete` — remove it outright. Answers: `deleted`.
- `GET /api/time/running` — every open timer, across all projects.
- `GET /api/time/summary?project=&task_id=` — attributed minutes for today,
  the last seven days, and per block; `task_id` narrows it to one task.
- `GET /api/time/auto` — the smart timer: idle seconds and where they are read
  from (`idle_source`), the away settings, each project's mode
  (`remind`/`auto`/`manual`), the auto spans counting now, the away notices,
  and `signals`: the last beat per project (`source`, `task_id`, `sec_ago`).
- `POST /api/time/auto/beat` — `{project, task_id?, source?}`: a page says
  someone is working on this project now (sent every 20 s while there is
  input, and at once on the first input after a quiet spell). `source`:
  `page` (default) or `window` (the terminal window, the tab in front).
- `POST /api/time/auto/mode` — `{project, mode}`.
- `POST /api/time/auto/away/{entry_id}` — `{action}`: `count` (the away stretch
  counts after all), `resume`, `stop`, `dismiss`.
- `GET /api/time/auto/break` — a break the operator took: `on`, and while
  it lasts `since`, `sec`, `project`, `note`, `paused` (manual timers it
  paused) and `closed` (auto spans it closed); `today`: today's breaks
  (`from`, `to`, `sec`, `project`, `note`, `resumed`).
- `POST /api/time/auto/break` — `{on: true, project?, note?}` starts a break:
  the smart timer's open auto spans close and count nothing while it lasts,
  whatever beats arrive; every running manual timer pauses. `project` holds
  one project only (empty: all). `{on: false, note?}` ends it: the manual
  timers it paused resume, only those still paused from its start; the
  note stays with the break. Either again changes nothing. Kept in
  `timer/break.json`, so a restart keeps a break under way. The terminal
  window's «Перерыв» / «Готово» send it.
- The entries themselves are the `time-entries` lens (see **Entries**).

### Cores

The program's core elements the operator keeps in view (`corelib.py`,
`routers/cores.py`): a capability, a feature, a store, a part of the interface, each with
its story. Three ledgers at the data root: `cores.csv`, `core_notes.csv`,
`core_links.csv`. Who writes: anyone makes a core and adds a note (the
operator's `#core-new` and `#core-note` run through the agent); an agent's
`auto` note needs tracking on; approving, tracking, changing and ordering
are the operator's.

- `GET /api/cores?project=` — every core of the project, in view first,
  tracked first, by position: `name`, `type`, `reason`, `status` (view |
  off), `tracking {on, until, days_left, expired}`, `notes_n`, `pending_n`
  (notes awaiting approval), `last_note`, `tasks_n`, `open_n`, `anchors`,
  `grid` (30 days: `{day, story, nearby}`). Also `types`.
- `GET /api/cores/timeline?project=&days=` — the cores over the last `days`
  days (7–120, default 30), one lane each: per ISO day the `notes` (yours and
  agents', with `approved`), the linked tasks `made` and `done`, the `commits`
  of those tasks and the `nearby` commits in the core's files that no linked
  task made; `tracking_spans`; `totals`. Above them `standups` by day and the
  project's release tags (`v…`) as `releases`.
- `GET /api/cores/tasks?project=` — task id → the cores in view it belongs to
  (`id`, `name`, `type`), for the board's cards.
- `GET /api/cores/map?project=` — the current map's rows, each with the cores
  that claim it and how: `linked` (a map link you set), `files` (an anchor of
  the core under the row's path), `tasks` (two or more linked tasks changed
  files under it); the cores with their row counts; `unclaimed`.
- `GET /api/tasks/{task_id}/cores` — the cores the task belongs to.
- `POST /api/tasks/{task_id}/cores` — operator only: `{cores: [id …]}` sets
  them; links missing are added, the others removed.
- `POST /api/cores` — body: `project`, `name` (≤ 60), `type` (capability ·
  feature · interface · store · integration · internals · workflow · experiment),
  `reason?`, `text` (the operator's message, kept as the founding note),
  `comment?`, `anchors?` (file or `file:symbol` paths), `task_id?`,
  `actor|agent_id`. The same name in view answers 200 with `existing: true`.
  Answers: `core`.
- `GET /api/cores/{core_id}` — the core with `notes` (oldest first, each with
  `author`, `kind` founding | note | auto, `text`, `comment`, `approved`),
  `links`, `tasks` (with status), `files` and `commits_n` of the linked
  tasks, `events` (created, tracking on and off, out of view and back), `commits` (every commit
  of the linked tasks: `how` signed · linked · chat, `agent`, `tasks`, `files`), `agents`
  (who worked on it: `tasks`, `commits`, `notes`, `turns`, `sessions`, `last_at`), `nearby` (commits that touched an anchor's file — by path, not by
  sense), `grid`.
- `POST /api/cores/{core_id}/notes` — body: `text?`, `comment?`, `kind?`
  (note | auto), `task_id?`, `actor|agent_id`. The operator's note is
  approved as written; an agent's waits. `auto` from an agent with tracking
  off is refused (422). A task named is linked. Answers: `note`, `core`.
- `POST /api/cores/{core_id}/notes/{note_id}/approve` — operator only: the
  author and the words stay, `approved_at` and `approved_by` are set.
- `POST /api/cores/{core_id}/links` — body: `kind` (task · anchor · map ·
  release · vision · decision · message), `target`, `note?`; or `{remove:
  link_id}` (operator). A target twice is one link (`existing: true`).
- `POST /api/cores/{core_id}/update` — operator only: any of `name`, `type`,
  `reason`, `position`, `status` (view | off).
- `POST /api/cores/{core_id}/tracking` — operator only: `{on, span?: day |
  week, until?: YYYY-MM-DD}`; on with neither is tracking with no end.
  Answers: `core`, `tracking`.
- `POST /api/cores/{core_id}/off` — out of view (`#core-off`, run by the
  agent once the operator confirmed); the story and the links stay.

### Entry points

The outside of a project: a topic the operator opens and comes back to
(`entrypointlib.py`, `routers/entrypoints.py`). The kept `#entrypoint` row is
its record (versions under `kept_versions/`); beside it four ledgers:
`entrypoint_ways.csv` (ways in), `entrypoint_stops.csv` (where it stopped),
`entrypoint_shots.csv` (screenshots, files under `entrypoint_shots/<ep>/`),
`task_topics.csv` (a task's topic, one row per task). `state` is active ·
paused · dead; a row with none reads it from `status` (closed → paused), and
a `status` changed since through `/update` wins (closed → paused, open → active).
`#entrypoint` (with a name, a description or nothing, in any chat of a
project) makes nothing when it is seen: it is kept as a pending command in
`entrypoint_commands.csv` until the operator chooses the topic
(`entrypointask.py`). The agent asks (`POST /api/entrypoints/ask`): the
server finds at most three topics of the chat's project — by the message's
words, by what this chat wrote on (commands, versions, stops, ways in,
shots), by the topics of the tasks named in this chat, one from each in
turn — and a last line for a new topic, and keeps the numbered list in
`entrypoint_asks.csv`. The operator's next message chooses
(`POST /api/entrypoints/answer`): an existing topic opens a new version of
its record, written by that chat's agent (a name written beside its number
becomes its name, a named topic renamed too); the new-topic line makes the topic then, from the command's
message, its id the command's. Only the exact name of one named topic
(equal once case and punctuation are out; the head of the line before a
colon or a dash counts) opens a version at once, without the question.
Commands: `how` pending · name · chosen · new · dropped, `chosen_at` (the
chat that chose last writes the record); `asked` was written before
2026-11-15 only. The chat of each version is in `entrypoint_versions.csv`;
each change of a topic's name (who, when, the old name and the new, the
command whose answer gave it) in `entrypoint_names.csv`.
Who writes: the operator everything; an agent, through the MCP tools, a stop,
a way in (added, or changed when an agent wrote it), a shot and a task's
topic, on a topic of its own chat's project (a chat with no recorded project
writes nothing). Every write checks the shape
first and a refusal writes nothing.

- `GET /api/entrypoints/desk?project=` — every topic (all projects when
  empty): `name`, `title` (the first sentence of the record's What; with no
  record, the message's first line: what an unnamed topic is shown by), `state`, `no_project`,
  `home`, `what` (the record's What, first paragraph), `has_record`,
  `versions`, `ways`, `stops` (the last five) and `stops_n`, `shots` (oldest
  first, each with `src`), `open_tasks`, `chats`, `last_at`. Also `projects`.
- `GET /api/entrypoints/similar?project=&text=` — the topics like `text`
  (`similar`: `id`, `name`, `state`, `score`) and `next`: the line for an
  agent's offer. Writes nothing.
- `GET /api/entrypoints/{ep_id}/context` — `stops` (every message of where it
  stopped, newest first); `chats` (oldest first: `id`,
  `name`, `tool`, `session_ref`, `cwd`, `first`, `last`, `messages` and
  `turns` — the topic's turns of that chat, each once: the #entrypoint turn,
  turns where the operator named a task of the topic, #done stretches, turns
  where a stop or a shot was written — `origin`, `did`, `tail`, `commits`,
  `live`, `from` (handoff or branch, from a chat of this thread), `waiting`
  and `waiting_text`); `open` (every open task) and `done` tasks (done with
  `report` and `chat`); `decisions`, `made`
  (artifacts and Publish cards) made in those turns; `commits` (each once)
  and `files` (summed over those commits), with `commits_n`, `files_n`;
  `spend` (`tokens`, `dollars`, `by_chat`) over those turns; `tasks_n`,
  `tasks_truncated` (over 40 done tasks; the newest 40 are read); `briefing`. Only the topic's project:
  a chat or task of another project never enters.
- `GET /api/entrypoints/{ep_id}/briefing` — `{text}`: what Copy to agent gives:
  the topic, the record's What, the ways in, then the record's Where, How,
  State and Next (every section whole, as written; nothing is cut), where it
  stopped, the open tasks, Resume and the rest.
- `GET /api/entrypoints/{ep_id}/ports` — `ways`: `{id, port, up, why}` per way
  in. A TCP connect on this computer only (localhost on 127.0.0.1 and ::1);
  a host that is not a loopback name or address is never connected to
  (`up: null`); at most a second for all.
- `GET /api/entrypoints/{id}/command` — what an `#entrypoint` opened, by the
  id the hook named (a topic's own id answers its last command): `id` (the
  topic; "" while pending), `command`, `name`, `project`, `opened` (new,
  version, pending: the operator has not chosen, or nothing: their answer
  chose none), `writer` (the chat that writes the record), `versions`,
  `record` (as it is) and `next` (what to write). Reads only; keeps a
  message typed a moment ago first.
- `POST /api/entrypoints/ask` — `{agent_id, id, name?}`: the question after
  the command `id`, typed in this chat. `name` is the agent's proposal for a
  new topic (≤ 80; without it, the head of the message). Answers `asked`,
  `command`, `rev`, `lines` (`{n, kind: topic · new, id, name, named, why:
  text · work · task, stop, stop_at}`), `lang` (en · ru: Russian when the
  command's message has Cyrillic, else the app's language, `sp-lang` in
  `ui_prefs.json`), `show` (the offer the agent gives exactly as it is, in
  `lang`: a heading, then per topic its number, name (or No name), state
  and project when another, the first paragraph of its What, its ways in,
  the last stop with its date and author, the last chat with its date, the
  open tasks and what choosing it does; the new topic; and how to answer,
  with the real numbers; with no candidate one line, `Start the topic «…»?
  Answer «yes» or give your own name.`) and `next`. Asked again before the operator
  answered, it replaces the list (`rev` + 1); 409 once they answered and the
  answer was not read, for another chat's command, in a helper chat, and
  for a command with no words and no `name`. A command already answered
  (or opened by its exact name) answers as `/command` with `asked: false`.
- `POST /api/entrypoints/answer` — `{agent_id, number, name?, id?}`: the
  operator answered. The server reads their next message after the
  question: a command in it chooses nothing and drops the command; a
  question chooses nothing yet (ask again); one number of the list chooses
  that line and `number` must be the same, the text beside it is a name (an
existing topic takes it, its old name written to `entrypoint_names.csv`);
  two numbers or one outside the list choose nothing (ask again); `yes`
  alone chooses the only line, `no` alone nothing; with one line, text
  without a number is the new topic's name when `number` is 1. `name` must
  be written in their message. Answers as `/command`, with `state` (chosen
  · question · unclear · dropped), `chosen` and `existing` (a retry: the
  same answer, nothing written). 409 when the numbers or the name do not
  match, or the operator has not answered yet; nothing is written. Agreement
  is read in English and Russian with softeners and signs (`да`, `думаю да`,
  `ok`, `I think so`, `+`, `👍`): it keeps the proposed name, and a name
  written with it (`yes, call it Review feed`) takes that one; a no with
  more words, or text that is neither a number nor a name, chooses nothing.
  `next` names the steps after the record, in order: the ways in
  (`entrypoint_way`), one stop (`entrypoint_stop`), a shot of each way that
  is up (`entrypoint_shot`, with the ways up now), the topic of the tasks
  this chat named (`task_topic`, with their ids).
- `GET /api/entrypoints/asks?agent_id=` — every question with its lines and
  answer, newest first; reads only.
- `GET /api/entrypoints/shots/{shot_id}/file` — the screenshot.
- `POST /api/entrypoints/{ep_id}/stops` — `text` (≤ 1000), `task_id?` (a task
  of this topic). The same text by the same author for the same task is the
  same message (200, `existing`).
- `POST /api/entrypoints/{ep_id}/stops/{stop_id}/remove` — operator only.
- `POST /api/entrypoints/{ep_id}/ways` — `way: {name, kind (page · site · app ·
  file · folder · script · artifact), url?, path?, command?, folder?, port?,
  note?}`, `id?` to change one.
- `POST /api/entrypoints/{ep_id}/ways/{way_id}/remove` — operator only.
- `POST /api/entrypoints/{ep_id}/shots` — `way_id`, `data_base64` (PNG, JPEG,
  GIF or WebP, read from the bytes), `caption?`, `replaces?` (a shot of this
  topic, then out of the series).
- `POST /api/entrypoints/{ep_id}/state` — operator only: `state`.
- `POST /api/entrypoints/{ep_id}/name` — operator only: `name`, `home?`,
  `no_project?` (true or false). A changed name is written to
  `entrypoint_names.csv` (by the operator).
- `GET /api/tasks/{task_id}/topic` — the task's topic, or null.
- `POST /api/tasks/{task_id}/topic` — `entrypoint_id` ("" clears): a topic of
  the task's project. An agent not a member of the topic's project is
  refused first and alone, 403 like the gate; a topic of another project
  after it (422).

### Usage

The tokens agents used and how much of each plan is used (`usagelib.py`,
`routers/usage.py`). Read only; the hooks write the files, the server reads
them. Per chat `projects/<p>/chats/<agent>/usage.jsonl`, one line per API
message: `turn`, `at`, `id`, `tool`, `model`, `new` (read for the first
time, cache writes included), `cache_write`, `cache` (read again from
cache), `output` (thinking included), `thinking`, `ttl`, `helper` (the
helper agent's id, or ""), `effort` (the reasoning effort the reply ran
with: `none`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`; ""
when the log does not say, and on every line written before 2026-11-11;
see [logging.md](logging.md)), `limit?`, `compacted?` (on the turn's first
line after a context compaction); the last line of an id wins. Account
wide `.usage/limits.jsonl` (one line per limits reading: `at`, `tool`,
`account` (12 hex characters naming the tool's config folder:
`CLAUDE_CONFIG_DIR` of the status line, else `~/.claude`; Codex's
`CODEX_HOME`, else `~/.codex`), `model` (the status line's `model.id`;
Codex: the rollout's current model, else ""), `session` (the session's
first 8 characters, Codex's last 8; for diagnosis), `five_hour` and
`seven_day` as `{used, resets_at, window_minutes?}`, `plan`, `source`;
read incrementally, only the bytes appended since). The limits are the
account's, whatever the model: the readings of one (tool, account) are a
series, and `model` and `session` are data. A line is written for its
series when a window's `resets_at` is later than any written, when a
window's `used` is higher than the highest written for that `resets_at`,
when the plan changed, or when the series' last line is older than 5
minutes (a heartbeat); an equal or lower reading of the same reset is
skipped (an idle session's status line sends its last reading again).
Lines written before `account` existed read as `""`, one series of their
tool, given way to by any newer named one. And
`.usage/sessions/<tool>-<session>.json`: an open chat's context and prompt
cache, from Claude Code's status line. No money anywhere.

One meaning of the numbers: `new_output` is the MAIN agent's new + output
everywhere (totals, tools, models, chats, tasks, the line); helper agents
count into the turn that started them and are kept apart on every row as
`helpers {n, new_output, cache}`. Each message counts on its own day. A
model the tool did not name is `""`. A percentage is the nearest whole
number, a tie down; the ratio to the usual day is in tenths, a tie down; a
duration is floored (`1 h 5 min`, `1 d 13 h`). The cases are in
`testdata/usage/format-table.json`, which the Python and TypeScript tests
both read.

Test switch: with `SP_NOW=2026-11-01T14:48:00` (a local ISO moment) in the
server's environment every clock read of the usage code — the routes, the
turns of the sessions, the #usage block, the ETags' minute — uses that
moment. The golden root `testdata/usage/root` and its snapshots
`testdata/usage/expected/*` are read under it.

- `GET /api/usage?project=<code|all>&range=today|7d|30d` — the Usage page:
  `range`, `project`, `days` (YYMM-DD, oldest first), `limits` (as below),
  `usual` (`new_output`, `cache`, `share`, `days_used`: the median over
  the active days of the last 90 calendar days before today, at most the
  30 most recent; an even count takes the mean of the two middle days; the
  page and the block show "× your usual day" only from 3 days),
  `totals` (`new`, `output`, `cache`, `cache_write`, `thinking`,
  `rebuilt`, `new_output`, `share`, `turns`, `cost_usd`, `cost`,
  `unpriced`, `chats`, `helpers {n, new_output, cache}`; `new` holds
  `rebuilt`: an estimate of old context written to the cache again;
  `cost_usd` the row at API prices with the helpers, `cost {new, rebuilt,
  warm, output, helpers}` the same by kind, `unpriced` the tokens of
  models with no price), `by_cause` (`cause` expired | model | other,
  `rebuilt`, `cost_usd`, `events`: rebuilds over 20k tokens, `chats`),
  `analysis` (backend usageanalysis.py; Claude Code's own replies only,
  since the 5-hour window is Claude Code's: other tools' replies, an
  OpenCode chat on a Claude model included, are left out of every part;
  a percent is of one 5-hour window, and null where no rate was measured.
  `window_now` — the 5-hour window open now: `used`, `resets_at`,
  `read_at`, `pace_per_hour` over the last hour of readings, `runs_out_at`
  at that pace or `lasts`, `spent_usd` in the window so far; the page reads
  `used`, `resets_at`, `runs_out_at`, `lasts`. `units` — percent of the
  window per dollar at API prices, per model, measured over the last 30
  days in windows where one model made 85% of the dollars: `{models:
  [{model, pct_per_usd, low, high, windows, window_usd}], windows, mixed,
  days, fallback}`; `fallback` is the median over every window, used for
  a model with no window of its own (null with none); the server keeps
  `models` and `fallback` in `.usage/units.json` for the Stop hook's
  warnings. `mix` — where the range's use of the window went: `{total_pct,
  windows, helpers_n, parts: [{key, pct}]}`, `key` one of `helpers`,
  `resumes`, `rebuilds`, `over_500k`, `200k_500k`, `under_200k`, and
  `other` for a rest over 0.5; the parts do not overlap and each model is
  counted at its own rate. `prices` — what one occurrence of a pattern
  takes of the window, dearest first: `[{key, model?, each_pct, times,
  total_pct}]`, `key` one of `resume`, `helper`, `message` (per model,
  from 3 replies), `reply_over_500k`, `reply_200k_500k`,
  `reply_100k_200k`, `reply_under_100k`. `history` — the past 5-hour
  windows of the last 14 days, oldest first: `[{start, resets_at, peak,
  capped, usd, model, model_share}]` (`capped`: it reached 99%; `model` the
  one that made most of the dollars). `chats` — the 8 chats that took the
  most of the window, each model of a chat at its own rate, helpers
  included: `[{agent_id, title, model, pct, helpers_share, rebuilt_share,
  rebuilds, turns}]`. `resumes` — replies after a break over an hour that
  wrote the context again: `events, cost_usd, avg_context, avg_usd,
  window_pct, after_s, chats`. `context` — the main agent's replies by the
  size of the context they read: `{replies, bands: [{band, replies, share,
  cost_usd, usd_per_reply}]}`. The page reads `window_now`, `units`, `mix`
  and `prices`; the feed of insights reads `history`, `chats`, `resumes`
  and `prices`; the MCP `usage` tool gives all of it),   `api_prices` (`as_of`, `sources`, `models`: the newest price of the
  models in the range, dollars per million tokens, `missing`: models with
  none; a message is priced as of its own day), `by_tool` (`tool`, the same sums, `share`, `turns`, `helpers`
  and `models` with the same keys, `model` and `efforts` — `{effort: new
  input + output}` of the model's replies and its helpers', "" for the
  replies that named none; the parts add up to `new_output` plus the
  helpers' — which the page shows under the model's name when a reply named
  one), `chats` (top 40:
  `agent_id`, `project`, `title`, `tool`, `model` (the last the main agent
  used), `models` and `tools` (every one seen, helpers' included), the
  sums, `new_output`, `share`, `turns`, `helpers`, `helpers_n`,
  `task_id`), `chats_total` (before the cut), `tasks` (top 20: `id`,
  `title`, `project`, `status`, `done_at`, the sums, `new_output`,
  `share`, `helpers`, `chats`, `turns`, `models`, `tools`), `tasks_total`,
  `coverage` (`chats_recorded`; `chats_without_usage`: chats with an
  operator's turn in the range and nothing recorded; `chats_from_log`: of
  the chats recorded, those whose earlier turns were filled afterwards
  from the tool's own log (usagebackfill.py, meta.json `usage_backfill`);
  `unreadable`: notes —
  a file that could not be read, lines that were not JSON, lines without a
  time, bad limits lines). A turn belongs to one task at most: the task the
  operator named in that turn (a #now card first), else the #done stretch
  that holds it, else the task named last before it until a #done closes
  it; so the tasks never add up to more than the chats. ETag; the tag also
  follows the minute and the limits file.
- `GET /api/usage/limits` — `{limits: {tool: {five_hour, seven_day,
  read_at, read_at_text, age_min, stale, expired, plan, source, series,
  accounts_n, models_n}}, codex_poll: {found, exe, home, enabled,
  every_hours, last_attempt, last_success, next_attempt, cause,
  failures}}`. `codex_poll` is the background reading of Codex's limits
  (`codex app-server`, no chat, no tokens; settings `usage.codex_poll`,
  `usage.codex_poll_hours`): whether Codex is on this machine, when it
  was last read, and the cause when it could not be. Such a reading's
  `source` is `app-server`. `series` holds what each account holds,
  newest first: `[{account, model, five_hour, seven_day, read_at,
  read_at_text, age_min, stale, expired, plan, source, session}]` (`model`
  and `session` of the reading it was read at); the tool's own fields are
  the newest series entry's (what one reading answered before);
  `accounts_n` counts the accounts, `models_n` the models the series'
  lines named (information only). A series other than the newest whose
  every window passed its reset is left out. Within one window — the same series, window and
  `resets_at` — the percentage never goes down (an idle session's status
  line sends its last, older reading again), so a window holds its highest
  reading of its newest `resets_at`, and `read_at` is when the 5-hour value
  (else the weekly one) was read. A turn's `limit` is what the series of
  the newest reading from 30 minutes before the turn to a minute after
  held then, by the same rule. With several accounts the #usage block
  prints one part per account and the page one group per account, newest
  first, named `Claude Code · account 2403ec81`; with one account only the
  tool's name. A window is `{used,
  resets_at, in, expired, span_s, resets_text, expired_text}` or null when
  the tool did not give it: `used` is null when the reading had no number;
  `span_s` the window's length (Codex's `window_minutes`, else 18000 and
  604800); `in` the time to the reset (`1 h 52 min`, "" once passed);
  `resets_text` `16:40`, or `Thu 09:00` on another day and always for the
  weekly window; `expired`: the reset passed with no reading since, so the
  percentage no longer holds, and `expired_text` says so (`Reset at
  14:10. No reading since.`); `read_at_text` `14:40` (a weekday on another
  day); `stale`: older than 15 minutes. The page shows these strings as
  given.
- `POST /api/usage/limits/refresh` — the operator's page asks for
  Codex's limits now. `{refreshed: true}` at once, the reading runs in the
  background (the page reads the limits again a few seconds later);
  `{refreshed: false, why: "fresh"}` when the newest reading is younger
  than 15 minutes, `why: "absent"` when Codex is not on this machine. An
  agent's request is refused.
- `GET /api/usage/insights` — the feed of insights: `{items: [{id, at,
  kind, key, params, pinned, hidden_at}], hidden}`, pinned first, then
  newest first. Writes the day's messages first when the day has none: one
  ordinary message a day (`model`, `context`, `resume`, `helpers`, `chat`,
  `cheap`; the heaviest kind not shown in the last 7 days) and one `cap`
  for each 5-hour window that ran out in the last 3 days, at most two a day.
  Kept in `.usage/insights.json`; the texts are the page's. A file that
  cannot be read is never written over: the feed answers no items.
- `POST /api/usage/insights/{id}/pin` — `{pinned}`. `POST
  /api/usage/insights/{id}/hide` hides one. `POST /api/usage/insights/clear`
  hides every message that is not pinned. An agent's request is refused;
  409 when `.usage/insights.json` cannot be read (nothing is changed).
- `GET /api/usage/prices/material` — `{models_used, prices_now, as_of,
  pages, instructions}`: what an update of the API prices is written from
  (MCP `usage_prices_material`, the command #usage-price).
- `POST /api/usage/prices` — `{models: {model: {input, write_5m, write_1h,
  read, output, over_tokens?, over?}}, sources: [https url], note?}`: one
  update, appended to `.usage/api-prices.jsonl`. Answers `{at, changed,
  new_models, unchanged, warnings}`; a price outside 0–1000 is refused,
  and so is an `over` that is not an object (MCP `usage_prices_write`).
- `GET /api/usage/chat/{agent_id}?block=` — one chat: `agent_id`,
  `project`, `show` (the line after each reply is shown: the chat's
  `#usage-on`/`#usage-off`, else the setting `agent.usage_show`), `turns`
  (turn number → `{turn, at, tool, new, output, cache, cache_write,
  thinking, model, models, messages, ttl, helpers {n, new_output, cache},
  context_tokens, share, rebuild {cause, kind} | null, limit {five_hour?,
  seven_day?} | null, compacted, line}`). `line` is `→ 1.9k ↑ 512 ↓ (108k)`
  (new up, output down, cache in brackets) with its event words; `· 5-hour
  70%` when the 5-hour percentage as shown passed a ten. A rebuild is a
  turn whose first read of the cache fell below 20% of what the turn
  before left cached (its last message's cache + cache_write) while that
  was over 20k; the cause is Claude Code's own (within 2 minutes), else
  `cache expired: N min since the last turn` when the gap (rounded up)
  passed the last cache lifetime the chat asked for, else a model change,
  else `context compacted`, else `cause not recorded`. With `block=true`
  also `block`, the text `#usage` prints. 404 for an unknown chat or one
  with no chat folder. The tag follows the chat's usage, meta and
  status-line files, the limits and the settings. The turns of `GET
  /api/sessions/turns` and `GET /api/sessions/{id}` carry the same record
  as `usage`; their ETags follow the same files (`/api/sessions/turns` has
  one now, and reads each chat's usage once per request).

### The tour

- `GET /api/tour/scripts` — every saved script, in the operator's order.
- `POST /api/tour/scripts` — body: `script` (the whole thing, replacing any
  prior one). Answers: `saved`, `n`.
- `POST /api/tour/scripts/{script_id}/delete` — answers: `deleted`, `n`.
- `POST /api/tour/capture` — photograph the beats, one real page load each.
  Body: `beats`, `base` (a page on this computer; the studio sends its own
  address), `width`, `height`, `scale`, `color_scheme`, `reseed` (play the
  example project again first, about a minute). Every tour walks the example
  project, `shopfront`.
- `GET /api/tour/shots` — what has been photographed and where each subject
  sat. Answers: `shots`, `files`, `view`, `scale`, `at`.
- `GET /api/tour/shot/{name}` — one shot.

### Terminal

A real shell in Slightly Parallel's pages (termlib.py). Off until the operator
switches it on (setting `terminal.enabled`, one click in the drawer;
`SP_ENABLE_TERMINAL` forces it on). With tmux installed each terminal
runs on Slightly Parallel's own tmux socket and stays open after the page and the server close.
On Windows every terminal is plain: a ConPTY (pywinpty) the server holds,
running PowerShell 7, else Windows PowerShell, else cmd; it ends with the
server, the history routes below (tmux only) answer 409, and restore never
offers one.
Every route refuses a foreign `Origin` or a cross-site request.

- `GET /api/terminal/state` — `enabled`, `token` (only while on; the page
  passes it to the socket), `tmux`, `supported` (false only on Windows
  without the pywinpty package; the other routes then answer 501 saying what
  to install), `windows` (true on Windows: plain terminals only), and the
  settings: `keep`, `launch`, `agent`, `font_size`, and the `projects` a
  terminal may open in.
- `GET /api/terminal/sessions?project=` — every terminal: `id`, `label`,
  `kind` (shell · resume · start), `project`, `cwd`, `command`,
  `agent_id` (the agent the capture hook saw started in it), `task_id`, and
  its `state` — shell · working · waiting (an agent done answering: your
  turn) · running (another program, quiet) · ended — with the foreground `program`; `counts` by state.
- `POST /api/terminal/sessions` — open one: `kind`, `project`, and `cwd` ·
  `command` (shell), `agent` (resume: its chat's resume command, reused
  when already open), `task_id` (start: the agent of setting
  `terminal.agent` with the task as its first message). The operator's.
- `POST /api/terminal/sessions/{sid}/type` — `{text, enter}`: type into it.
- `GET /api/terminal/sessions/{sid}/pos` — where the pane stands in its
  history: `history`, `scroll`, `rows`, `cursor`. The page anchors a
  clicked row to an absolute line with it. tmux terminals only.
- `POST /api/terminal/sessions/{sid}/capture` — text out of the terminal,
  wrapped lines joined: `{mode: "screen"}` the visible screen,
  `{mode: "last"}` everything since the last Enter that crossed the
  socket, `{mode: "range", from, to}` the lines between two absolute
  ids. At most 20 000 lines (`truncated` says when). `{mode: "selection"}`
  asks tmux to send its active selection as an explicit clipboard copy.
  It returns `copied: false` when there is no selection. tmux only.
- `POST /api/terminal/sessions/{sid}/open` — `{path, line?, col?}`: open a
  path the terminal printed in the operator's editor (Settings › Terminal ›
  Open printed paths in; `auto` takes the first installed). A relative path
  resolves where the shell stands now. 404 when there is no such file, 409
  when no editor is chosen or installed. `GET …/state` names it as `editor`.
- `POST /api/terminal/sessions/{sid}/bottom` — leave the pane's scrolled-up
  copy mode; answers the new position.
- `POST /api/terminal/sessions/{sid}/rename` — `{label}`.
- `POST /api/terminal/sessions/{sid}/close` — end it (tmux too).
- `POST /api/terminal/sessions/{sid}/sleep` — stop what runs in it and keep
  its row (`state: asleep`, `wake`: what it will run): a chat's agent is
  resumed on waking, a server (`role: server`) runs its command again, a
  plain shell comes back empty.
- `POST /api/terminal/sessions/{sid}/wake` — bring it back under the same id.
  With `{shell: true}`, open an ended terminal with an empty shell and keep its
  original command for a later wake. A sleeping terminal refuses this mode with
  409. `GET …/state` advertises support as `open_shell`.
  A terminal's `role` is `chat`, `server` or `shell` (sent on opening, else
  worked out from its kind).
- `GET /api/terminal/restore` — `needed` and the `sessions` that ended
  without being closed or put to sleep because their tmux server is gone (a
  restart of the computer), each with the `wake` command it would run.
  `POST /api/terminal/restore` — `{ids?}`: bring them back; `results` holds
  `id`, `label`, `ok`, `error`, `command` per terminal.
- `GET /api/terminal/groups` — custom workspaces and tab groups: `id`, `name`,
  `color` (1–8), and `project` for groups inside a project.
  `POST /api/terminal/groups` `{name, color?, project?, tabs?}` makes one.
  With `project` and `tabs`, it adds the selected terminals on creation.
  `POST /api/terminal/groups/{gid}` `{name?, color?}` changes it,
  `POST /api/terminal/groups/{gid}/remove` removes it (its terminals return
  to their projects). `POST /api/terminal/sessions/{sid}/group` `{group}`
  moves a terminal into a group, `""` back to its project; `group` is also
  accepted on opening.
- `POST /api/terminal/groups/move` — `{project, group, tabs}` assigns a
  selection to a tab group in its project. An empty `group` clears their
  memberships. The whole selection must belong to the project.
- `POST /api/terminal/typing` — `{sid, keys}`: the operator typed that many
  keys into a terminal since the last report (the window sends it; the text
  is never sent). `GET /api/terminal/typing?day=YYYY-MM-DD` — `minutes` per
  project in which the operator typed, and `total`.
- `GET /api/terminal/tabs` — what the window's tab strip shows, per terminal
  id: `title` (the title its program set, OSC 0/2, as tmux keeps it; `""`
  for plain terminals and programs that set none), `agent_id` and `chat`
  (`null`, or `name`, `tool`, `tasks_done`, `tasks_all` — tasks named in
  its turns —, `branches` — `branch` links from it and the chats it
  started, helpers left out —, `ctx_pct`, `ctx_size`, `ctx_at` — Claude
  Code's context from its status line, `null` when not known —, `rhythm`:
  `period_min` (60) and `periods`, the last six clock hours oldest first,
  the last the hour now running, each `start`, `end`, `msgs` — the
  operator's messages and the agent's answers, from the turn stamps —,
  `commits` — the chat's repository, signed `Agent:` by it, or unsigned and
  naming one of its tasks or listed in its own turn stamps —, `tasks` — its
  tasks moved to done —, `tokens` — the main agent's new input + output; the
  tab's six dots, tk_d2e11125).
- `GET /api/terminal/agents` — `agents: {claude, codex, opencode}`: which of
  them this computer has (the "+" menu offers only those).
- `GET /api/terminal/resumable?project=` — `chats`: the newest chats of the
  project (at most 12) that a terminal can resume and no open terminal
  holds: `agent_id`, `name`, `tool`, `last_active`.
- `GET /api/terminal/branch/{agent_id}` — `command`, `project`, `cwd`,
  `name`: the command that opens a copy of the chat from where it stands
  (`claude -r <session> --fork-session`, `codex fork <session>`); 422 for a
  tool that cannot.
- `WS /ws/terminal/{id}?token=&project=&cols=&rows=` — the screen. Not an
  HTTP route and not in the OpenAPI document. Closed with 4000 when the
  terminal ended, 4500 when its shell did not start (the reason says why).

The terminal log (`backend/termlog.py`): how the terminal works, for
finding its bugs and slowdowns. Counts, sizes and times only — never what
was typed, pasted or printed. Kept under `<data root>/terminal/log/`.

- `POST /api/terminal/log` — a page's batch: `{page, rows, events}`. `rows`
  are minute counters (at most 20), `events` the Full stream as
  `[t_ms, kind, sid, a, b]` (at most 20 000); 2 MB at most. A wrong batch is
  refused whole (422) and writes nothing. Answers the mode in force
  (`mode`, `setting`, `full_until`) and how much was `kept`.
- `GET /api/terminal/log/mode` · `POST /api/terminal/log/mode`
  `{mode: off|light|full, hours?}` — read or switch it; Full turns back to
  Light after `hours` (2 by default, at most 24). The operator's.
- `GET /api/terminal/log/summary?day=YYYY-MM-DD` — a day for the Monitor:
  `totals` (frames, p50/p95/max, slow frames, stalls, errors, reconnects,
  findings, bytes), `hours` (24), `findings` (newest first), `by_kind`,
  `scroll` and `paste` paths, `mem`, `server` (tmux calls per command,
  writes, sends), `files`, `days` kept.
- `GET /api/terminal/log/report` — one JSON file for a bug report: versions,
  system, the terminal settings, today's and yesterday's rows, the last hour
  of the full log.

---

## MCP

`GET /api/schema` (version 2) is the whole write contract, machine-readable:
every lens, the `scan` lens included, with its `fields` (columns with enums
inlined, and the named text fields with what each holds), `text_fields` in
order, `headline`, what is `required`, what is `mutable`, and which fields
the server stamps. `architecture` holds the form's groups, types and ops.
`tools` lists the MCP tools as `[{name, summary}]`; the pages and the
refusal text read the list from there.

`GET /api/whoami?cwd=…` resolves the chat identity the capture hook
breadcrumbs per working directory, so local tools stamp `agent_id` and
`project` instead of asking the model to copy them. Answers: `agent_id`,
`project`, `session_id`, `age_min`, and the chat's projects: `home` (where a
write that names no project goes), `members`, `level` (task rights, 1–3).

Agents write in their member projects only (tk_d1d25a4d step 3). Every agent
write, through the MCP or over HTTP with `agents.mcp_only` off, is checked at
the gate: a body's `project` and every code in `projects` must be one of the
agent's projects, and a write on a task by its id (`/api/tasks/{id}/…`) must
be on a task of one; otherwise 403 with one line — «agent cc-… is not a
member of X; its projects: A, B. The operator adds it on the agent card» (or
«…; this task is X's. …»). An agent Slightly Parallel has no chat of is
refused with 403 on every agent write, a project named or not. Identity in
an agent's body besides `agent_id`/`actor` is 422 (see «Identity in an
agent's body» above). A `project` that is not text, or `projects` that is not text or a
list of texts, is 422. Writes on other rows by id (`update_entry`, notes,
publishing cards, topics) check the row's project the same way. The MCP
create tools (`write_entry`, `note_write`, `core_new`, `map_write`,
`architecture_page`) take an optional `project` (else the home) and answer
with `where`: «dc_… → X», «tk_… → X · lane ui»; standups stay in the home.

Both exist for the MCP translator (`python -m backend.mcp`): a stateless
stdio process that builds its tools from `/api/schema` and forwards every
call to this API with `X-SP-Via: mcp`. It never touches the CSVs, so
the one write authority keeps its locks and its gates. Agents write through
these tools only; the POST routes in this document are what the tools and
the operator's pages call. By purpose:

- entries: `write_entry {lens, fields}`, `update_entry {lens, id, changes}`
- tasks: `tasks`, `task_update`, `task_report`, `task_done` (with `proposals`, the
  next tasks offered after `#done`), `next_tasks`,
  `task_evidence_ask`, `task_evidence`, `task_work`, `task_story`
- kept messages: `interpret`, `skill_draft`, `artifact_write`
- entries made by mistake: `undo_find`, `undo_propose`, `undo_apply`,
  `undo_restore` (after the operator's `#undo` and `#undo-yes`)
- the Storyboard: `doc_version` (the finished text of a document whose
  pack the operator gave)
- what an entry is written from: `scan_material`, `standup_material`
  (and `standup_postpone`), `architecture_material`, `map_material`,
  `task_evidence_ask`
- the architecture: `architecture_status`, `architecture_page`, `map_write`
- messages between agents: `message {to, text, reply_to?}`, `messages`
  (the inbox; reading marks read)
- readers: `search`, `project`, `deck`, `doctor`, `usage` (the `#usage`
  text for this chat and the Usage page's numbers; from a chat the hook
  never saw, `block` is "" and the summary is the project asked, else all)

It also serves the contract, the schema, active rules and health as MCP
resources, and every command of the contract as an MCP prompt, built from
the contract's `command:` lines. A wrong field name or a wrong vocabulary
value is refused inside the translator, with the names or values the lens
does take, before any request exists. When the server is down at startup the
translator waits for it on the first call instead of exiting.

Setup wires the translator into every observed project: `.mcp.json` (Claude
Code), with the Cursor hooks `.cursor/mcp.json` (the same shape, the file
Cursor reads) and, with the OpenCode plugin, `opencode.json`; the Codex entry
(`[mcp_servers.slightly-parallel]`) goes into `~/.codex/config.toml` with the notify
hook. Existing servers in those files are kept.

---

## Storage

```
data_root/
├── <entity>.csv                  # index rows, append-only through the API
├── <entity>_details/*.md         # the detail documents md_ref points at
├── snapshots/                    # what each scan checkpointed
├── kept_versions/<id>.md         # interpretations of kept entries, versioned
├── task_events.csv               # append-only task history
├── task_notes.csv                # story notes on tasks
├── task_evidence.csv             # the agent-done loop's evidence
├── task_links.csv                # blocks · relates · parent
├── story_requests.csv            # press-release requests (sr_)
├── story_images.csv + task_story/<task>/   # images with a piece, and the prompts sent
├── calendar_entries.csv          # the operator's dates (ce_)
├── milestones.csv + milestone_tasks.csv    # outcomes (ms_) and their tasks (mt_)
├── architecture.csv              # the log of what each scan changed
├── integrations.csv              # where each set was written
├── boards.json · sets.json       # multi-project boards, rule sets
├── examples.json                 # which example entries are in or out
├── agent_links/                  # the hand-drawn links between lanes
├── standup_state.json · scan_marks.json    # claims, postponements, uncommitted marks
└── projects/<code>/
    ├── architecture/vNNN.md      # the architecture page, in versions
    ├── map/vNNN.json             # the map of the program, in versions
    ├── artifacts/<name>/         # the folders agents wrote for #artifact
    ├── log.md                    # the project's own notes
    └── chats/<agent>/            # meta.json + chat.md per agent chat
```

CSV ingestion is **header-aware**: the backend reads each file's actual
header and maps legacy column names (`date` → `created_date`, `goal_id` ↔
`related_goal_id`) onto one canonical schema, synthesising missing columns.
An older data root loads without conversion.

---

Checked against /openapi.json on 2026-11-20: 391 routes, 0 missing, 0 stale.
Re-run it with `backend/.venv/bin/python scripts/check_api_doc.py`. The 391
is route shapes: `/api/tasks/{item_id}` and `/api/tasks/{task_id}` are one
shape, as are `/api/prompts/{item_id}` and `/api/prompts/{key}`.
