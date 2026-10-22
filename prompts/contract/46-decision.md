---
key: decision
section: 4
title: Decision
enabled: true
command: #decision | Log the decision just made (also offered on `decision_hint`)
brief: **Decision** (`#decision`, or on your own when a piece of work is done). Log each point where a choice was made, if the product would be different had it gone the other way. One `write_entry {lens: "decision"}` each, with a `weight`: minor, normal or major. The skill `log-a-decision` holds the steps.
---

**Decision — `write_entry {lens: "decision"}`** (`#decision`, or on your
own when work is done). Logging a decision is cheap: do it often, and keep
it short.

**Find them.** When a piece of work is done, list each point where the
operator chose between options, or you reversed earlier work, or you
picked one way where another was open. Look at your own work too, not only
at what the operator answered. Log one only if the product would be
different had it gone the other way: what users or agents can do, what is
safe, or what gets built next. A wording
change, a layout tweak, a bug fix, or doing what was asked the way it was
asked is not a decision. For one day of work expect two to six.

**Weigh each** — `weight`:

- `minor` — local and cheap to undo: a name, a default, where something
  lives. At most three per task; drop the rest.
- `normal` — shapes a feature or a page; undoing it costs hours.
- `major` — touches stored data, the rules agents follow, security, or
  several features; undoing it costs a migration or a rewrite.

One decision per entry, written as section 3 says:

- `decision` — one sentence, 20 words at most: what was chosen, as a
  statement of how it is now. No list inside it. `why` does not repeat it.
- `why` — one or two sentences, 40 words at most: the reason, in terms of
  what a user or an agent can or cannot do. End with the state in a few
  words: live · built, not checked · planned. For `major`, add "Undo it
  if …" only when you know what would change it.
- `alternatives` — for `normal` and `major`, only options a person in the
  chat proposed or asked about: `"<option> — rejected: <reason given>"`.
  Nobody proposed one: leave it empty. Never invent one.
- `excerpt` — for `major` only: the two to five lines of chat where it was
  decided, in English. A field with nothing to say is left out, not filled
  with "none".

```json
{"lens":"decision","fields":{
  "decision":"A task's evidence stores its file list with the task, not in the project's file ledger.",
  "weight":"normal",
  "why":"The file heatmap sums each file per day, so a second copy would count one edit twice. Live.",
  "alternatives":["write the files into the file ledger too — rejected: double counting in the heatmap"]}}
```
