# How the product's text is written

Every text a person reads in the app: labels, buttons, tooltips, toasts, empty states,
placeholders, dialogs, page taglines, guides, the tour. Drawn from the author's choices over
115 texts. The standard, in the author's words: **"Windows XP wording. Simple, short,
respectful, concise."** The Russian interface follows the same rules.

## The rules

1. **Say what the control does or what the thing is.** Read the code behind the text first.
   A button names its action ("Remove from today", "Clear filters"). A title names the content
   ("Daily progress", "Changes since the last scan").
2. **Short by default; longer only where the reader needs it to decide.** A tooltip or a label
   is a few words. A dialog that makes someone choose says what happens under each choice, in
   full plain sentences (`Choose the backlog or another running block below, and they are moved
   there`). About four in ten of the chosen texts were the longer, context-carrying option.
3. **No figures of speech.** No metaphors (a sprint is not "a bet", a chart is not "the river",
   a task does not "live" or "breathe"), no aphorisms ("not now, not never"), no slogans.
4. **Things do not act like people.** Not "finished work waits on your verdict", not "the step
   moved on", not "the page knows". Say the state: "In review", "Next in stack".
5. **Say what happens, not what does not.** Not "the tasks stay where they are", but "Removed 3
   tasks from today's plan."
6. **No chat.** No questions to the reader ("What needs doing?", "where do they go?"), no
   cheer, no "you'll love".
7. **No judgement of the user's work.** Not "probably drop", but "low value".
8. **The user's words, not the system's.** Not "captured turn", "lens", "ledger", "L1–L4",
   "MCP" in a page the operator reads, but "chat", "page", "list". A term the product does use
   (scan, standup, sprint, task) stays, the same word everywhere.
9. **Placeholders say what goes in the field**: "Title shown on the card", "Required: what
   happened, in your own words".
10. **Keep every fact that changes a decision.** Short never means dropping the one thing a
    person needs (a limit, a required field, what is irreversible).

## Forms

| kind | form | example |
|---|---|---|
| button | verb + object, no period | `Add a next step` · `End this block and save the retro` |
| tooltip | a short phrase or imperative, no period | `Ctrl-click a card to add it to Today` · `Mark as important` |
| toast | past-tense fact, period | `Removed 3 tasks from today's plan.` |
| empty state | what is absent, or the one action | `No chats mention this task.` · `Nothing to review` · `Appears after the first #scan.` |
| placeholder | what goes in | `Write the note here` |
| title / tagline | what the content is | `Rules agents follow, written after something went wrong` |
| dialog | plain sentences: what this does, what to choose, what follows | see rule 2 |
| guide | one paragraph, how to use the page, under 600 characters | `Drag a task onto a day to set its due date. Drop one here to clear it.` |

## Before and after

| before | after |
|---|---|
| Drop from today (the task stays where it lives) | Remove from today |
| Today cleared — {n} tasks stay where they are | Removed {n} tasks from today's plan. |
| The step before this one moved on — this is the stack's front now · {date} | Next in stack · {date} |
| then… (stack a next step behind it) | Add a next step |
| low impact + L — probably drop | low impact + L: low value |
| low impact + S — filler for a quiet hour | low impact + S: when time allows |
| Priority says when; these say why: | Priority sets the order. These describe the value. |
| Drop a card here to check it again in a few weeks — not now, not never | Drop a card here to review it later. |
| The value, in the moment it is clear… | Write the note here |
| draft kept locally — closing this window will not lose it | Draft saved |
| not named in any captured turn yet | No chats mention this task. |
| What needs doing? | Title shown on the card |
| A sprint is a bet: name the block, bet the days, budget your hours. Three run at most. | This creates a sprint, a named block of work with a length in days and an optional budget of your hours. Give it a name, pick the days, tick any backlog tasks it should carry, and confirm. |
| Settle the bet | End this block and save the retro |
| nothing new — the record is exactly as you left it. | No changes since your last visit. |
| Nothing needs you — no open problems, nothing in review, nothing stalled. | Nothing to review |
| finished work waits on your verdict | In review |
| Loosen the chips, or clear the filter. | Clear filters |
| the river · what the work has been doing, day by day | Daily progress |
| {n} tasks are still open — where do they go? | {n} tasks on this block are not done. Choose the backlog or another running block below, and they are moved there. |
| The daily rhythm — one entry per agent per day. | Each agent posts one entry a day. |
| The living playbook — lessons promoted into rules. | Rules agents follow, written after something went wrong |
| Every decision, with its rationale, in one ledger. | Choices agents logged, with the reason and the rejected options |
| This one lives on the secretary page; it is shown here, not edited here. | Edit this event on the Calendar page. |

## Before you change a text

- Read the code behind it: what the control does, what the API answers. A rewrite that is
  wrong is worse than a clumsy one.
- A test may assert the text: change the test with it.
- Change words, never behaviour.
