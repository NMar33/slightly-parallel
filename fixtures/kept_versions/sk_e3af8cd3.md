---
id: sk_e3af8cd3
kind: skill
---

## Version 1 · 2610-20 14:36 · edited
> Built into Slightly Parallel

---
name: sp-checkup
description: "The operator typed #sp, maybe with what worries them: check whether Slightly Parallel works for this chat and folder — recorded messages, MCP, hooks, contract, skills, data, backups, the server's memory and errors — and report what works and what is a concern, without filler. Use when the [slightly-parallel] #sp notice appears, or the operator asks whether Slightly Parallel is working."
---

**Is Slightly Parallel working — `#sp`.** The operator asks whether
Slightly Parallel works for this chat and this folder, or names what worries
them (`#sp the messages are not recorded`). The server checks; you report
and, for a worry, look further.

1. Call the MCP tool `checkup`. It answers `verdict`, `counts` and
   `findings`, each with `status` (`ok`, `note`, `concern`, `unknown`),
   `title`, `evidence` and `next`. The call coming through proves MCP from
   this chat. When the tool is missing or refused, say so first, then read
   `GET <server>/api/checkup?cwd=<this folder>` (the server's address is in
   AGENTS.md), else run `python <app folder>/sp.py check`.
2. Answer in this shape, in the operator's language, and nothing else:
   - the verdict in one line, with the counts;
   - each `concern`, then each `unknown`: **title**: evidence · why it
     matters to the operator, in a few words · the next step;
   - `note`s in one line;
   - one line: what was checked and is fine, by area.
   Use the findings' numbers as they are. Never call something fine that
   came back `unknown`: "installed" is not "loaded", and only this call
   proves MCP.
3. With text after the tag: after the answer, look into that worry. Match
   it to an area — not recorded → capture and this chat; slow or memory →
   the server's memory and slow requests (`python sp.py report`, Monitor ›
   Server); a command does nothing → hooks, contract, skills; data missing
   or wrong → data and backups (Internals › Data check). Read logs, pages
   and files as you need. Say what you found and what you would change.
4. Change nothing without the operator's yes: no restart, no
   re-integration, no setting, no file. Ask in one line, naming the action
   (`python sp.py restart`, Setup › Re-integrate this folder); do it after
   the yes. Integrating a folder is the operator's own step on the Setup
   page.

A folder that is not connected comes back as a concern: say in two lines
what Slightly Parallel would record here and that Setup integrates it.

Check: every concern and unknown from `checkup` is in the answer with its
next step; nothing `unknown` was called fine; nothing was changed without a
yes.

Mistakes to avoid: judging health yourself instead of reporting the
findings; padding ("everything looks great!"); calling installed skills
working; restarting or re-integrating before the operator says yes; long
explanations of what Slightly Parallel is to someone already using it.

## Version 2 · 2610-20 15:59 · edited
> Built into Slightly Parallel

---
name: sp-checkup
description: "The operator typed #sp, maybe with what worries them: check whether Slightly Parallel works for this chat and folder — recorded messages, MCP, hooks, contract, skills, data, backups, the server's memory and errors — and report what works and what is a concern, without filler. Use when the [slightly-parallel] #sp notice appears, or the operator asks whether Slightly Parallel is working."
---

**Is Slightly Parallel working — `#sp`.** The operator asks whether
Slightly Parallel works for this chat and this folder, or names what worries
them (`#sp the messages are not recorded`). The server checks; you report
and, for a worry, look further.

1. Call the MCP tool `checkup`. It answers `verdict`, `counts` and
   `findings`, each with `status` (`ok`, `note`, `concern`, `unknown`),
   `title`, `evidence` and `next`; each that is not `ok` also has its
   `reason` and `recipe`, and the answer has the `rules` every recipe keeps. The call coming through proves MCP from
   this chat. When the tool is missing or refused, say so first, then read
   `GET <server>/api/checkup?cwd=<this folder>` (the server's address is in
   AGENTS.md), else run `python <app folder>/sp.py check`.
2. Answer in this shape, in the operator's language, and nothing else:
   - the verdict in one line, with the counts;
   - each `concern`, then each `unknown`: **title**: evidence · why it
     matters to the operator, in a few words · the next step;
   - `note`s in one line;
   - one line: what was checked and is fine, by area.
   Use the findings' numbers as they are. Never call something fine that
   came back `unknown`: "installed" is not "loaded", and only this call
   proves MCP.
3. With text after the tag: after the answer, look into that worry. Match
   it to an area — not recorded → capture and this chat; slow or memory →
   the server's memory and slow requests (`python sp.py report`, Monitor ›
   Server); a command does nothing → hooks, contract, skills; data missing
   or wrong → data and backups (Internals › Data check). Read logs, pages
   and files as you need. Say what you found and what you would change.
4. To fix a finding, follow its `recipe` and the `rules`: run its
   **Confirm** steps (reading only); when what you see contradicts it,
   stop and say what you saw. Its **Who** says who acts: *operator* — say
   where to click, never do it yourself; *agent, after a yes* — ask in one
   line, naming the action and what it touches (`python sp.py restart`),
   do that one action after the yes, then its **Verify** step and `#sp`
   again. Change nothing else: no restart, re-integration, setting or file
   without its own yes. A recipe for any reason: `GET
   <server>/api/checkup/fix/<reason>`.

A folder that is not connected comes back as a concern: say in two lines
what Slightly Parallel would record here and that Setup integrates it.

Check: every concern and unknown from `checkup` is in the answer with its
next step; nothing `unknown` was called fine; nothing was changed without a
yes.

Mistakes to avoid: judging health yourself instead of reporting the
findings; padding ("everything looks great!"); calling installed skills
working; restarting or re-integrating before the operator says yes; long
explanations of what Slightly Parallel is to someone already using it.
