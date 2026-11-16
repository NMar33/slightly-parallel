# Next tasks after #done

After the operator closes a task with `#done`, the agent may offer up to
three next tasks: only steps without which the finished task does not do
what it was for ("the site is deployed, www has no DNS record"; "the task
asked for Linux and Windows, it ran on Linux only"). An improvement, a
"worth thinking about" or a retelling of the work is not one. More than
three such steps means the task is not finished: the agent says so instead.
No such step: no offer, which is the normal case. The rule is in
`prompts/contract/55-done.md` and the skill `finish-a-task` (step 6).

## The steps

1. The agent calls `task_done` as before, then again with `proposals`
   (`[{title, line}]`, at most three). The server compares each with the
   project's open tasks and answers `similar` for each, and `show`: the line
   the agent gives the operator, numbered as recorded,
   `Make these tasks? 1) … 2) …`. A proposal whose similar task is the same
   thing is left out by calling again with the rest.
2. The operator answers in their next message: numbers, "yes"/"all", or
   anything else.
3. The agent calls `next_tasks {numbers}`. The server reads the operator's
   next message from chat.md (only the capture hook writes it): numbers
   alone there must be the numbers sent; "yes" or "all" alone means every
   one; a message with a command (`#now …`, `#done`) or a question chooses
   nothing; other text must contain each number sent ("1 and 3, not 2" →
   the agent sends `[1, 3]`). The server proves the operator wrote the
   numbers, not what they meant by them.
4. Chosen proposals become tasks in the `agent` column, tag `ag_followup`,
   in the offer's project. They do not pass the `#task` gate, which reads
   the operator's latest message as a command (a later `#now` there would
   have put them in doing). Each is stamped with the answer's time, so a
   retry mints the same id and finds it.

Why the agent's call and not the hook: the hook would read the offers on
every message for an event of a few times a day; "numbers only" misses
"make 2" and "1 and 3, not 2"; and the agent has to answer the operator
anyway. The server still checks the operator's own words.

## The record

`next_tasks.csv` in the data folder, one row per offer: the `#done` turn and
the tasks it closed, the turn the offer was made at, the proposals with
their similar tasks and scores, `state` (offered · made · skipped), the
answer's turn and kind, the numbers chosen and the task ids made.
`GET /api/next-tasks` lists them; an offer nobody answered through the
tool shows the numbers the operator did write (`answer_in_chat`). This is
what the two-week check (tk_13318a92) reads: offers per `#done`, how many
were taken, and whether a taken task had a similar open one.

## The similarity search

`backend/similarlib.py`. Words: lower case, ids, commit hashes and numbers
out, English and Russian stop words out, a Russian ending cut off, each
word cut to five letters. A task's text: its title and the first twelve
words of its description's first line. Score: BM25 over the project's open
tasks, divided by the summed rarity of the proposal's words, with twenty
more empty documents counted into the rarity so a board of three tasks
does not make every shared word common. At most three tasks at 0.40 or
more. Pure Python: no SQLite FTS5, which not every Python build carries.

Measured on 2026-11-11 on the operator's merkhet board (161 open tasks,
title and first line, read only). The labelled set is
`backend/tests/fixtures/similar_tasks.json` (titles only).

| set | found | note |
|---|---|---|
| 30 re-worded proposals (25 English, 5 Russian) | 28 | the 2 misses are Russian re-wordings of English tasks; written with the titles in view, so optimistic |
| 11 real pairs filed twice | 6 | of 9 a project can find; the others are English↔Russian and another project |
| 25 unrelated proposals | 2 with a hit | both related, not the same ("token after a backup restore" → "backup restore takes no locks") |

Lower (0.35) finds one more real pair and doubles the wrong hits; the
description's whole first line instead of twelve words gave 8 of 25
unrelated proposals a hit. Decisions use the same score, at most one named:
on 65 real decisions, 4 got a warning, from 1 real pair and 2 related pairs.
That is weak, and it is a warning only.
