---
key: standup
section: 4
title: Standup
enabled: true
command: #standup | Write the standup for yesterday now (also offered on the first message of a day)
brief: **Standup** (`#standup`, or the `[slightly-parallel] No standup for …` notice). One per project per day, from every chat of that day. Ask the operator: write it now, or postpone. A helper agent calls `standup_material {claim: true}`, which carries the instructions, and writes it. The skill `daily-standup` holds the steps.
---

**Standup — one per project per day.** It covers every chat of one day
and is written the next time anyone works on the project. The
`[slightly-parallel] No standup for …` notice tells the first agent of the day; the
skill `daily-standup` has the steps: ask the operator (write it now, or
postpone — `standup_postpone {date, hours}`, 4 hours by default, and
nobody is asked about that day again until then), then a helper agent on
the model the notice names reads the
day with `standup_material {claim: true}` and writes it with
`write_entry {lens: "standup"}`. `#standup` asks for it by hand.

**Who reads it, and how.** The operator runs several projects at once. The
next morning they open the standup to understand, in a few minutes, what
happened yesterday in this project, as if someone who was there told them.
Write it as section 3 says: plain sentences, facts, no filler. Read every
chat to its last message first: what the operator already decided is
reported as decided, not as an open question.

`standup_material` carries every message of the day whole (or clipped, when
the operator chose it), the commits each turn made, **`numbers`** counted by
Slightly Parallel (messages, chats, agents, tasks made and finished, commits,
files, lines, minutes, decisions logged), **`tasks_changed`** (every change
to a task that day) and **`previous`**, the last standup before this day.
The page shows the numbers, the tasks and the agents of the day beside the
standup: do not count anything yourself and do not list them again.

- `summary` — one sentence, 30 words at most: what the day did, as facts
  about the product.
- `story` — the day told, one to three paragraphs: what the work set out to
  do, what happened, what came out, what got in the way, how it ended. The
  most important first; a heavy day gets more, a quiet day three sentences.
  Pick up from `previous` where it connects ("the rename begun on Tuesday is
  done"). Say why a change matters when the chat says it. Numbers only where
  they mean something. Trouble plainly. A chat that changed nothing in the
  product gets one sentence or none.
  The operator knows the product and its own words — scan, standup, task,
  `#map`, the board: use them as they are and do not explain them (this
  replaces section 3's rule on defining terms, which is for a reader new to
  the product). Explain only a thing the day itself introduced, once, in
  plain words. Open each paragraph with a fact — what a user or an agent can
  do now, or what broke — never with a frame such as "The night went to …",
  "The day was about …", "X left loose ends".
  Not: "The night went to the scan, the entry that records what a chat
  changed. Its window now starts at the same agent's last scan."
  But: "A scan now covers only its own chat's work: the commits since that
  agent's last scan, plus what was changed and not committed."
  Not: "The task window work left loose ends."
  But: "The task window shows the evidence an agent attached; the operator
  decided that a task closes only with evidence."
- `deviation` — what a user would have seen broken, work that was redone,
  a correction from the operator: one item each, with the cause and the
  state now. Nothing of the kind: leave it empty.
- `movement` — every outcome of the day a user or an agent can see, one
  item each, most important first, 35 words at most each. **Each item
  begins with its kind and a colon:** `New:` · `Changed:` · `Fixed:` ·
  `Architecture:` · `Cleanup:` · `Decided:`. No limit on the number: a day
  of twenty commits has as many items as it had outcomes. Give a task as
  its title, then its id, and only on its own work. Write a state only when
  the item is not finished: what is left, and who it waits on.
- `decisions` — every choice made that day, in a chat or in the decisions
  log: `"<what was chosen> — <the reason> · <operator or agent>, <HH:MM>"`.
  Only choices the material shows being made.
- `forgotten` — strict: something the operator asked for, or an agent
  promised, that the same chat never came back to. Work that moved on to
  another subject is not forgotten. When unsure, leave it out. The page
  shows this list folded.
- `detail` — three short parts, each may be empty. **Needs an answer:**
  each question left with the operator that is still open, with only the
  options given. **Next:** what the last messages say happens next.
  **State:** were the tests run, is the work pushed, what is started and
  not finished, what the operator must do in a running chat.
- `for_date` — the day it covers, `YYMM-DD`.

Leave out: how the work was done (helper agents, tools, test counts), and
what the operator said themselves.

```json
{"lens":"standup","fields":{
  "for_date":"2609-20",
  "summary":"Agents write every entry by field name, and a request can no longer pass as the operator by naming both.",
  "story":"The day finished the move from numbered levels to named fields. Each kind of entry now has its own names, such as a decision's alternatives, and the contract and the skills say them. On the way an agent found that a raw request naming both the operator and an agent was treated as the operator's; the server now treats it as the agent's.\n\nThe task window crashed once on evidence that listed a missed file. It was fixed the same hour.",
  "deviation":["The task window crashed when evidence listed a missed file. The panel expected file names and got records. Fixed."],
  "movement":[
    "Changed: Evidence upgrade (tk_0e571cfa): typing #evidence now sends the agent the operator's own saved prompt, the same as a done-report does.",
    "Fixed: A raw request naming both the operator and an agent passed as the operator. The server now treats it as the agent's."],
  "decisions":["Agents write every entry by field name; the numbered levels stay only as storage — the pages show different things per kind · operator, 14:10"],
  "forgotten":[],
  "detail":"**Needs an answer:** push the day's commits, or wait.\n**Next:** build the chosen page layouts.\n**State:** tests pass; not pushed."}}
```
