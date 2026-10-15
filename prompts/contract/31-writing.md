---
key: writing
section: 3
title: How to write it
enabled: true
---

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
