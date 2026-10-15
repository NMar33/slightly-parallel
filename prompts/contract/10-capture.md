---
key: capture
section: 1
heading: ## 1. Capture and signals
title: Capture and signals
enabled: true
---

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
- **kept notice** — the user tagged the message `#vision`, `#rule` or
  `#problem`: the server keeps it; write its interpretation with
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
