---
name: daily-standup
description: "Write the project's standup for yesterday from every chat of that day with a helper agent, and offer to map the program with a second helper. Use when the [slightly-parallel] notice says there is no standup for a day, or when the operator types #standup."
---

One standup per project per day. It covers every chat of that day and is
written the next time anyone works on the project. You do not write it
from memory: a helper agent reads the day's messages.

1. The `[slightly-parallel] No standup for <date> …` notice gives the date, how many
   messages there were, and the models Settings name. If the notice says
   to ask, say before other work what you want to start, and give the
   choices as numbers, so the operator answers with one:

   > Yesterday (<date>) has no standup: <N> messages in <M> chats.
   > I want to start two helper agents: one writes the standup, one maps
   > the program (it reads up to 40 files).
   > 1 · write and map — standup on <standup model>, map on <map model>
   > 2 · write only, on <standup model>
   > 3 · postpone
   > Another model for either: haiku, sonnet or opus.
   > The helper reads every message whole (about <N>k characters); say
   > "clipped" for the start and end of each (about <M>k).

   Wait for the answer. The models and the sizes come from the notice; the
   operator's word replaces them for this run. Leave out the
   map when the project is not a program.
   - 1 or 2: go to step 2. With 1, also start the map helper, as the
     skill `map-the-program` says from its step 2, on the map model.
   - 3, or later: call `standup_postpone {date, hours}` (4 hours when the
     operator names no time). Nobody is asked again until then.
2. Start the standup helper on its model (in Claude Code: the Agent tool
   with `model`). Give it this whole prompt and nothing else:

   > Write the Slightly Parallel standup for <date>. Call the MCP tool
   > `standup_material {date: "<date>", claim: true}` (add `clip: true`
   > only when the operator chose clipped messages). If the answer says
   > the standup is written, or another agent has claimed it, stop and say
   > so. Otherwise follow the `instructions` in the answer exactly, using
   > only the `chats` in the answer as your material. Then call
   > `write_entry {lens: "standup", fields: {summary, story, deviation,
   > movement, decisions, forgotten, detail, for_date: "<date>"}}`. Reply
   > with the summary line only.

   If your tool has no helper agents, do the same steps yourself.
3. When the helpers are done, tell the operator the standup's summary
   line, and the map's version and row count, each in one sentence, and
   go on with their request.

The instructions for the text come with the material, from the server, so
they are the operator's current ones. Do not paraphrase them to the helper.
The contract's own text on the standup, with the fields and their budgets,
is below — read it when you write the standup yourself.

{{part:standup}}

Check: open Standups in Slightly Parallel. The day shows one standup. A refusal from
`write_entry` names what is wrong: fix it and write again.

Mistakes to avoid: writing the standup yourself from what you remember of
one chat; asking again after the operator said later; starting a second
helper when the answer says another agent has claimed the day.
