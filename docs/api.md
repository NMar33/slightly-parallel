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
- **Agents write through MCP** — a POST whose `actor` or `agent_id` names an
  agent is accepted only with the header `X-SP-Via: mcp`, which the MCP
  translator sets on every call; otherwise 422, naming the tools. The
  operator's pages send a house actor and pass. Setting `agents.mcp_only`
  turns the gate off.

---

## Reading

Derived and aggregate reads. Nothing here appends to a ledger except the two
noted writes.

- `GET /api/health` — liveness plus data-root diagnostics (`degraded`,
  `load_errors`).
- `GET /api/snapshot` — the Overview payload: KPIs, per-project summaries
  with task counts, recent chats and decisions, open tasks in play, every agent.
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
  profile: the roster in one read.
- `GET /api/agents/{agent_id}/profile` — everything one agent left behind.
- `POST /api/agents/{agent_id}/group` — body: `group` (empty removes).
  Answers: `agent_id`, `agent_group`.
- `POST /api/agents/{agent_id}/rename` — body: `name`, stored as
  `agent_name` in the agent's `meta.json`. Answers: `agent_id`, `agent_name`.
  Both of these are presentation only; the ids never change.
- `GET /api/chat/{agent_id}?range=a-b` — a raw `chat.md` line slice.
- `GET /api/sessions?project=` — the chats, newest first. Each row carries `chat_end_line`, the chat's last line in chat.md, which grows with every captured line (a page's cue to fetch that chat's turns again). Read from the
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
  file entry.

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
| `/api/decisions` · `/api/decisions/{id}` · `/api/decisions/{id}/update` | `source`, `related_goal_id` | `tags`, `weight` | — |
| `/api/files` · `/api/files/{id}` · `/api/files/{id}/update` | `trigger_lens` | `files_ignored_n`, `files_important_n` | `paths` (see below) |
| `/api/goals` · `/api/goals/{id}` · `/api/goals/{id}/update` | `status`, `parent_goal_id`, `sprint_id`, `root_only` | `confidence_pct`, `retro_outcome`, `sprint_id`, `status`, `success_comment`, `time_est` | `children`. **Retired**: the product no longer writes goals; the routes stay so pre-task data still reads, and sprints still join the rows they have |
| `/api/ideas` · `/api/ideas/{id}` | `tag` | — | `body`. Legacy reader — the library retired in favour of tasks |
| `/api/notes` · `/api/notes/{id}` | `tag` | — | `body`. Legacy reader |
| `/api/problems` · `/api/problems/{id}` · `/api/problems/{id}/update` | `tag`, `severity`, `status`, `search` | `resolved_date`, `severity`, `status`, `tags` | see **Kept messages and skills** |
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
| `/api/visions` · `/api/visions/{id}` · `/api/visions/{id}/update` | `tag`, `category`, `impact`, `search` | `category`, `effort`, `impact`, `tags` | see **Kept messages and skills** |

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
- `POST /api/tasks/{task_id}/update` — body: `title`, `description`,
  `status`, `turn` (which round to rewrite), plus the mutable columns
  (`assignee`, `priority`, `lane`, `sprint_id`, `remember`, `today_on`,
  `stack_id`, `resurface_on`, `resurface_to`, `resurface_every_days`, …).
  Status is the operator's; an agent that sets it is refused.
- `POST /api/tasks/{task_id}/turn` — the next round of instruction. Body:
  `text`, `actor`, `created_date`, `created_time`. Answers: `task`, `turn`,
  `turns`, `description`, `ref`.
- `GET /api/tasks/{task_id}/events` — every field change appended by
  `/update`, oldest first.
- `GET /api/tasks/{task_id}/work` — what the repository saw in the turns
  that named this task. Answers: `task_id`, `work`.
- `GET /api/tasks/{task_id}/mentions` — every captured turn naming this
  task, newest first. Copying a task puts its id in the text (`tk_… · Title`)
  and the chat reading scans every turn for `tk_[0-9a-f]{8}`, so
  mentions cost nothing extra and need no ledger.
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
  instructions for the evidence the report owes.
- `GET /api/tasks/{task_id}/evidence` — the task's evidence with git's
  account of the same work beside it. Query: `path`, `paths`, `changes`,
  `start_here`. Answers: `task_id`, `evidence`, `missing`, `work`.
- `POST /api/tasks/{task_id}/evidence` — body: `agent_id`, `items`.
  Answers: `task_id`, `saved`, `existing`.
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
  `ext`). Answers: `note`, `images`, `request_id`.
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

A message tagged `#vision`, `#rule`, `#problem`, `#skill` or `#artifact` is
adopted into its ledger on the way past the next list or detail read. The
kept text stays verbatim; the *interpretation* is what an agent or the
operator writes about it, as a new version under `kept_versions/`.

- `POST /api/visions/{item_id}/interpretation`
- `POST /api/rules/{item_id}/interpretation`
- `POST /api/problems/{item_id}/interpretation`
- `POST /api/artifacts/{item_id}/interpretation`
  — all four: body `text`, `note?`. Answers: `metadata`, `kept` (the
  versions). 422 if the entry was posted rather than kept, since then its
  text belongs to `update_entry`.
- `POST /api/problems/{item_id}/rule` — the operator writes a rule on the
  basis of a problem. Body: `text`, `title?`. Answers: `metadata`, `kept`.
- `GET /api/examples/state` — the example vision, rule, problem and skill
  ids: `present`, `removed`, `all`.
- `POST /api/examples/remove` — take the examples out. Answers: `removed`.
- `POST /api/examples/restore` — put them back. Answers: `added`.
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
- `GET /api/architecture/page/material?project=` — what the next version is
  written from (MCP `architecture_material`). Answers: `project`, `facts`,
  `current_page`, `check_again` (claims not found or changed since), `next`,
  `instructions` — the contract part `architecture-page`.
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
- `GET /api/map/material?project=` — what the next version is written from
  (MCP `map_material`). Answers: `facts`, `current_map` with its problems,
  the vocabulary, `model` (Settings › Agents), `next`, `instructions` — the
  contract part `map`.
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
- `GET /api/capture/health` — is capture working (capturewatch.py): `missed`,
  the active Claude Code sessions in folders registered in Setup whose latest
  messages Slightly Parallel did not record (or never saw); `errors`, hook failures of
  the last day (`<data root>/.capture/errors.jsonl`); `ok` when neither.
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
- `GET /api/scans/material?project=&agent_id=` — MCP `scan_material`: what a
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
`#problem solved`). The hook also keeps small copies of server facts — the
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
  use count. Harvests on the way past.
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
  `data_projects`, `integrations`, `adapters`, `codex`.
- `POST /api/setup/data-root` — switch the data root: persisted to `.env`
  and hot-swapped in the running app. Body: `path`. Answers: `data_root`,
  `env_file`, `restart_required`.
- `POST /api/setup/integrate` — write or refresh the integration block in a
  target project. Body: `project_code`, `project_dir`, `notes`, `dry_run`,
  `write_agents`, `write_claude_bridge`, `write_claude_hooks`,
  `write_codex_hooks`, `write_mcp`, `write_opencode_plugin`. Answers:
  `project_code`, `project_dir`, `dry_run`, `results`.
- `POST /api/setup/codex` — install or remove the global Codex notify hook.
  Body: `action`, `dry_run`. Answers: `action`, `file`, `file_action`,
  `line`, `status`.
- `POST /api/setup/forget` — disconnect: drop the registry row and undo
  every file Setup wrote. Body: `project_code`, `path`. Answers:
  `forgotten`, `path`, `agents_md`, `claude_md`, `hooks`, `sets`.
- `POST /api/setup/delete-data` — archive everything Slightly Parallel holds for a
  project into `.trash/`. Body: `project_code`, `confirm` (must repeat the
  code).

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
  (`remind`/`auto`/`manual`), the auto spans counting now, the away notices.
- `POST /api/time/auto/beat` — `{project, task_id?}`: a page says someone is
  working on this project now (sent every 20 s while there is input).
- `POST /api/time/auto/mode` — `{project, mode}`.
- `POST /api/time/auto/away/{entry_id}` — `{action}`: `count` (the away stretch
  counts after all), `resume`, `stop`, `dismiss`.
- The entries themselves are the `time-entries` lens (see **Entries**).

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
Every route refuses a foreign `Origin` or a cross-site request.

- `GET /api/terminal/state` — `enabled`, `token` (only while on; the page
  passes it to the socket), `tmux`, and the settings: `keep`, `launch`,
  `agent`, `font_size`, and the `projects` a terminal may open in.
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
  ids. At most 20 000 lines (`truncated` says when). tmux only.
- `POST /api/terminal/sessions/{sid}/open` — `{path, line?, col?}`: open a
  path the terminal printed in the operator's editor (Settings › Terminal ›
  Open printed paths in; `auto` takes the first installed). A relative path
  resolves where the shell stands now. 404 when there is no such file, 409
  when no editor is chosen or installed. `GET …/state` names it as `editor`.
- `POST /api/terminal/sessions/{sid}/bottom` — leave the pane's scrolled-up
  copy mode; answers the new position.
- `POST /api/terminal/sessions/{sid}/rename` — `{label}`.
- `POST /api/terminal/sessions/{sid}/close` — end it (tmux too).
- `WS /ws/terminal/{id}?token=&project=&cols=&rows=` — the screen. Not an
  HTTP route and not in the OpenAPI document.

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
`project`, `session_id`, `age_min`.

Both exist for the MCP translator (`python -m backend.mcp`): a stateless
stdio process that builds its tools from `/api/schema` and forwards every
call to this API with `X-SP-Via: mcp`. It never touches the CSVs, so
the one write authority keeps its locks and its gates. Agents write through
these tools only; the POST routes in this document are what the tools and
the operator's pages call. By purpose:

- entries: `write_entry {lens, fields}`, `update_entry {lens, id, changes}`
- tasks: `tasks`, `task_update`, `task_report`, `task_done`,
  `task_evidence_ask`, `task_evidence`, `task_work`, `task_story`
- kept messages: `interpret`, `skill_draft`, `artifact_write`
- the Storyboard: `doc_version` (the finished text of a document whose
  pack the operator gave)
- what an entry is written from: `scan_material`, `standup_material`
  (and `standup_postpone`), `architecture_material`, `map_material`,
  `task_evidence_ask`
- the architecture: `architecture_status`, `architecture_page`, `map_write`
- readers: `search`, `project`, `deck`, `doctor`

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

Checked against /openapi.json on 2026-10-09: 270 routes, 0 missing, 0 stale.
Re-run it with `backend/.venv/bin/python scripts/check_api_doc.py`. The 270
is route shapes: `/api/tasks/{item_id}` and `/api/tasks/{task_id}` are one
shape, as are `/api/prompts/{item_id}` and `/api/prompts/{key}`.
