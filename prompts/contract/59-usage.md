---
key: usage
section: 4
title: Usage
enabled: true
command: #usage | The hook answers: it prints this chat's tokens, the plan limits and the project's day, and the message does not reach you. Add nothing. In Codex and OpenCode the notice carries the text: give it as it is, in a code block
command: #usage-on | The hook answers: each reply in this chat shows its tokens from now on. Add nothing
command: #usage-off | The hook answers: the replies in this chat no longer show their tokens; they are still recorded. Add nothing
command: #usage-price | Update the API prices the Usage page counts dollars with: say which pages you are going to, a helper agent reads them, then usage_prices_write (the skill update-usage-prices)
brief: **Usage prices** (`#usage-price`). The operator asks; you say in one line which pages you are going to, a helper agent reads the providers' own pricing pages (`usage_prices_material`) and writes the prices (`usage_prices_write`), and you say what changed. Never on your own. **Usage** (`#usage`, `#usage-on`, `#usage-off`). The hook answers these itself; in Claude Code the message does not reach you. Add nothing. When it does reach you, the notice says so: in Codex and OpenCode it carries the #usage text, which you give as it is, in a code block; in a message with other text, the hook printed the text already and you add nothing about it. Tokens are recorded for every reply in any case; `#usage-on` and `#usage-off` only show or hide the line after each reply (`→ 1.9k ↑ 512 ↓ (108k)`: new input, output, cache in brackets). Asked about tokens or limits in words, call `usage {}` and give its `block` the same way. The Usage page is `/usage` on the server.
---

**Usage — the tokens of each reply and the plan limits.** The hooks record,
for every reply, the tokens each API message used, from the tool's own log:
`new` (read for the first time, cache writes included), `output` (written,
thinking included) and `cache` (read again from cache). Helper agents count
into the turn that started them and are shown apart. The plan limits come
from Claude Code's status line and from Codex's log. Nothing here is money.

- `#usage` — the hook answers with this chat's turns and tokens, its context
  and cache, the plan limits of Claude Code and Codex, and the project's day
  against the usual one. In Claude Code the message stops at the hook and
  you never see it. In Codex and OpenCode the notice carries the text: give
  it as it is, in a code block, and add nothing but one line when something
  stands out (a cache rebuild, a limit over 80%). In a message with other
  text the hook printed the text already: do what the rest of the message
  asks and add nothing about it.
- `#usage-on` / `#usage-off` — the hook shows or hides, for this chat, the
  line after each reply: `→ 1.9k ↑ 512 ↓ (108k)` is new input, then output, then cache in
  brackets; `· cache expired` (or why else the cache was built again) on a
  rebuild, `+ helpers 300k` when helpers ran, `· 5-hour 70%` when the 5-hour
  limit passed a ten. The setting "Show usage after each reply" is the
  default; tokens are recorded either way. Add nothing.
- `usage {project?, range?}` — when the operator asks about tokens or limits
  in words: `block` is the same text as `#usage` (give it the same way),
  `summary` the numbers of the Usage page over `range` (today, 7d, 30d).
- The Usage page (`/usage`) shows the plan limits, the totals against the
  usual day, the tools and models, and the chats and tasks that used the
  most. The chat viewer shows the line on each reply.

Never: work out a price, guess a number the tool did not give (it is `—`),
or say a limit counts tokens in a fixed way.
