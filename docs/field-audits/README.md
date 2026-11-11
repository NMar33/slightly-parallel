# Field audits

Slightly Parallel sits above the operator's other projects: it records how
he really works in them. A field audit reads that record and the projects'
folders to find patterns, anomalies and what to improve, from real work
rather than from what the product was designed for. Task: tk_1e748fed.

Each round below says what was looked at, how, and what came out. To run
one again, use "How to repeat" at the end.

## Rounds so far

### 2611-11 — entry points, in two projects (record: 2611-11-entry-points.md)

Asked: what does the operator open to look at results, in the writing
tracker (`103-2604-Writing-Tracker`) and the AI linter (`106-2611-offkey`)?

Done: a helper agent on Opus, read only, read each project's folder, its
recorded chats in the data folder (helpers left out), the Claude Code
transcripts for those folders, the tasks and entry points through the
server, and which ports were listening (`ss -ltnp`).

Found:
- He had built entry points by hand three times, outside Slightly
  Parallel: `00-entrypoints/2605-entrypoints.md` (start commands, URLs, a
  screenshot each), `00-agents/ENTRYPOINT.md` (a log over projects) and
  `00-agents/103-2604-bewrite.md` (a navigator still in use: permanent ways
  in on top, dated blocks of what was done and what is next). offkey has a
  handoff document of the same kind. The product's Entry points page held 9
  records, 8 without a topic.
- Every local page was down: each dev server stops when the chat that
  started it ends. The start command is the field that matters most.
- offkey has three working copies; the project in Slightly Parallel points
  to a stale one, his drafts are in all three, and an agent once worked in
  the wrong one.
- The linter's chats (ai-linter 2.0 to 9.0) are recorded under the writing
  tracker, not under offkey.

### 2611-11 — helper agents (tasks tk_3895dc98, and the archive request ud_10da8e36)

Asked: why the Entry points page was full of fragments.

Done: grouped the entry points by the agent that made them; read the first
line of each Codex session file (`~/.codex/sessions/**/rollout-*.jsonl`) and
the `entrypoint` field of Claude Code transcripts; counted the entries
every helper chat had made, by how they were made (`source`).

Found:
- 21 of 30 entry points came from `codex exec` runs: the prompts an agent
  sent to Codex quoted the command list, and the hook took the words as
  commands. Across all kinds, helper chats had made 268 entries (problems,
  visions, rules, skills, prompts, artifacts, tasks); none through MCP on
  purpose. They are archived, each can be restored.
- Three of the operator's tasks had been moved to done by a `#done` in a
  helper's prompt.
- 88 of the chats on the agents board were helpers: 986 `codex exec`
  sessions on this machine against about 15 interactive ones.

### 2611-10 — usage, from the operator's own chats (task tk_ffb836bd, tk_b1547a00)

Asked: what uses the operator's plan limits.

Done: a helper read 14 days of `usage.jsonl` per chat, the plan limit
readings in `.usage/limits.jsonl` and the transcripts; set the rise of the
5-hour limit against the dollars spent between two readings; measured what
a chat's context is made of from the difference between two replies'
context sizes.

Found: a message on Fable used about 11 times the limit of one on Opus, and
every 5-hour limit that ran out was mostly Fable; replies in chats over
500,000 tokens took about 40% of the limit; returning to a long chat after
an hour cost about 4% of the limit each time; the operator's own messages
are about 4% of a long chat's context. These became the Usage page's
analysis and the warnings under a reply.

### 2611-10 — the paid agent runs (round 4 of the code audit)

Asked: what the weekly runs with real agents had shown.

Found: Claude Code on Windows had failed `#task` twice (10-19, 10-26), and
both times it was read as the agent's mistake. The cause was the product:
tags sent as a list were refused with a message that listed the same tag as
allowed. Fixed in round 4.

## What the rounds taught

- Look at what the operator built for himself around the product. The hand
  navigator in the writing tracker said what Entry points should be better
  than any design note.
- Group by who made it. Sorting entries by agent showed at once that the
  junk came from helpers.
- Read what the tools write, not only what the product stores: the Codex
  session's first line and the Claude Code transcript held the facts
  (`codex_exec`, `sdk-cli`, the effort per reply) the product did not keep.
- A failure of a real agent is a product bug until shown otherwise.
- Check what is running now, not only what is configured.

## How to repeat

1. Pick the question and one to three projects. Name the folders.
2. Sources, read only:
   - the project folder; files the operator keeps by hand (`00-*`,
     `README`, notes, handoff docs) first;
   - its chats: `<data root>/projects/<code>/chats/*/` (meta.json, turns);
     leave out chats whose meta.json has `"helper": true`, or count them
     apart;
   - the tools' own logs: `~/.claude/projects/<folder with / as ->/*.jsonl`,
     `~/.codex/sessions/**/rollout-*.jsonl` (first line: `originator`,
     `source`, `cwd`);
   - the server, GET only: `/api/tasks?project=`, `/api/entrypoints?project=`,
     `/api/artifacts?project=`, `/api/usage?range=30d`;
   - the data folder's CSV files, grouped by `agent_id` and `source`;
   - what is running: `ss -ltnp`.
3. Give the reading to a helper agent on Opus, read only, with the question,
   the folders and the sources above; ask for a table per project with the
   evidence for each row and the operator's own words where he talks about
   it, then the anomalies, then questions for the operator.
4. Write the round here: asked, done, found. Keep the helper's full record
   beside this file. Turn findings into tasks; ask the operator before
   changing or archiving anything.
