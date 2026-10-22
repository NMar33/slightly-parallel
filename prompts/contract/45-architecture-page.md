---
key: architecture-page
section: 4
title: Architecture page
enabled: true
command: #page | Write the next version of the project's architecture page: architecture_material, then architecture_page (the skill keep-the-architecture-page)
brief: **Architecture page** (part of `#architecture`, and at the end of a `#scan`; `#page` still asks for it alone). One page per project: what it is, what it does now, what it is made of and what is owed, as claims with their evidence, for a team lead who was not in the chat. Call `architecture_material`: it returns the computed facts, the current page and the instructions. Write the next version with `architecture_page {text, note}`. The skill `keep-the-architecture-page` holds the steps.
---

**Architecture page — `architecture_material`, then `architecture_page {text, note}`** (`#page`, and the
last step of a `#scan`). The architecture form says what one scan changed. The page says what the
project **is**. One page per project, kept in versions. You write the next version: you keep what is
verified, correct what is wrong and add what you touched. It is never rewritten from nothing.

The reader is a team lead who opens this project after a month away, or for the first time. They
were not in any chat and know nothing about its files. From the page alone they must be able to answer:

1. What is this, is it alive, and what is being made right now?
2. What exists today that a person can use, read, run or send — and how sure are we that it works?
3. What is it made of, and what are the ways in and out?
4. What is owed: dates, unfinished work, broken things, people waiting?

The project can be anything: a web service, a mobile app, a data analysis, a research archive, a
book, a folder of official documents. Describe the project that is there.

### What you are given

`architecture_material` returns **computed facts** (today's date, whether the folder is active, its
size, every top-level folder with its size and last change, the newest files, the recent commit
subjects, nested repositories, build files, where Slightly Parallel keeps this project's data, open tasks and
recent decisions), **the current page** with each claim the server could not find or whose file
changed since, and these instructions. A program computed the facts: trust them over any document
and do not recount them.

### The next version

- **Keep** every claim whose evidence still holds. A claim the server marks "changed since" is
  opened again; one marked "not found" is corrected or removed.
- **Go where the page is thin**: what it lists under "Not read" or "Searched and not found",
  sections that say "None found", people and dates it mentions in passing, folders the facts show
  as large or recently changed that it does not mention.
- **You were there.** What you built, fixed or learned in this chat is first-hand: `seen:` is
  what you ran or changed. Say so.
- **Correct** what is wrong, and close the page with one line: "Corrected in this version: …".
- Over the word budget: shorten old material first.
- `note`: one line on what this version changed.

### How to work

- Read the computed facts first. **The newest things tell you what is alive — not what matters most.** The most important thing a project has is the one most work went into, or the one its own index calls the main one; it can be months old.
- **The newest things tell you what is alive.** Group the recent commit subjects and newest files into 2 to 4 threads of work: that is the live work. Folders unchanged for months are old material.
- **Code and the newest file win.** A README or plan older than the recent commits is a claim about the past. When it disagrees with the code, a newer file or a recent commit subject, the newer one is right, and the disagreement itself is an owed item ("README still says X").
- Explore the folder, read-only. Open up to about 45 files. HTML, TeX, Markdown, notebooks and source code are text: read them. Only images, PDFs, archives and office files are binary.
- **A project made of documents is described by what the documents say, not by their names.** Open every document. In a long one, read its list of contents, then every section named deadlines, plan, checklist, not checked, open questions, errors or changes. Each document's item says what it concludes or tells its owner to do, and whether it has a built-in tool (a calculator, a form).
- **Rebuilding.** For an output built from sources (a PDF from TeX, an app from code), list the inputs the source names and check each one is in the folder. A missing input is an owed item. Go to the folders the facts show as alive, and to any file the project itself calls index, status, log, plan or to-do. A file named as the end of a sequence (results, comparison, verdict, report) must be opened before you write about that sequence.
- **Opened or not.** You describe only what you opened. The rest goes under "Not read" by name, with no description.
- **Found or not.** Before you write that something is missing, search the whole folder for it, hidden and nested folders too.

### Every item is a claim with its evidence

Each item in sections 3, 5, 6 and 7 has this shape, on one or two lines:

`name — what it is, in up to 12 words · where: <path> · seen: <how you know> · made by: <person | agent run | script | unknown> · checked by: <nobody | automated tests | agent | person | unknown>`

- **seen** is what you did or what you read: "ran the tests, 449 passed" · "result file `x.md` dated 2026-05-29 says …" · "opened, 3 of 5 sections written" · "commit subject 2026-09-20" · "per README of 2026-08-14, not checked". A claim with no evidence is not written.
- A state word (sent, published, released, hosted, final) is written only with the check that proves it (a tag, a remote URL, a line in a file). Otherwise: "claimed in `<file>`, not verified" or "not recorded".
- Leave out "made by" and "checked by" only where they are truly the same for the whole page, and then say it once at the top of the section.
- No caveats about your own limits inside items. They go in section 10.

### How to write

- Name the concrete thing in plain words. One fact per sentence, 25 words at most. **One fact, one place.**
- A slot or heading with nothing real to say: one line "None found — looked in X", never filler. Never "depends on: nothing", never an item that restates its own name as its reason.
- Translate quotes in another language inline. Say the working language of the project once.
- No metaphors, no slogans, no praise. Things do not act like people. No counts of lines or files as the content of an item. A number inside a claim is one you counted yourself or quote with its source; otherwise leave it out.
- Private persons' details (full names of private people, document numbers, addresses, birth dates) are never copied. **Say whose situation the project serves, by role**: "a couple: one a returning citizen, one a permanent resident". Roles and first names the project itself uses are fine.
- 1,200 words at most, the evidence included. Over budget: cut old material first, then the least important items.

### The layout

#### 1. What it is
Two sentences: what the project is and for whom. **Kind:** one of service · app · tool · analysis · research archive · writing · documents for a decision · other (say which). **Standing:** copy the computed standing, then one sentence on what the last real work was. **Made how:** one line — by whom and with what (a person, agents, scripts), as far as the files show.

#### 2. The live work
The 2 to 4 threads you found in the newest commits and files. For each: what is being changed, the target in the project's own words if one is stated (quote, with where), how far along, and what would show it done. Dormant or finished project: the last thread, and where the newest dated note says things stand, in the owner's own words.

#### 3. What it does or has produced
What a person can use, read, run or send today, as claims. At most 12, the most important first. For software: capabilities, as the user would say them, each with the route, command or screen. For research and analysis: results, models, publications and public links. For writing: the pieces, each with how it was made and who has read it. For documents: each output, and whether it can be rebuilt from what is in the folder.

#### 4. How the main thing works
The core mechanism of the most important item in section 3, as 3 to 6 steps in the project's own terms, as it works **now** (from code and the newest files, not an old description): what comes in, what happens to it, what comes out, and the part that does each step. For documents: how they are produced and what makes them trustworthy (sources, confidence marks, checks).

#### 5. Ways in and out
Every way a person, a program or an agent gets something into or out of the project: screens, commands, an API, tools offered to agents, hooks, files read or written, release channels, places it is published. As claims. For a project with none beyond opening files: one line saying so.

#### 6. What it is made of
The parts a person would point at, that sections 3 to 5 did not already name. At most 10, as claims without the state. For software add **Built and run:** repository and remote, what it is built with (the three or four things the design leans on), how it is built and tested, where it runs and which release stage it has reached, and **where its real data lives** as opposed to demo or test data (the computed facts say, when Slightly Parallel knows). Close with **Old material:** one line — how many folders, what they are, how big, unchanged since when.

#### 7. Rules the project keeps
Standing rules and limits the project states about itself, each with where. At most 6.

#### 8. People
`who (role) — last thing they said or asked (date) · last thing done for them (date) · told or not`. Only people the files show. "Told" only when a message in the folder shows it; otherwise "not recorded". "Not told" and "not recorded" items also go to section 9.

#### 9. What is owed
At most 10, in this order, each with where it is stated and **still true on <today>: checked how**:
1. Dated obligations from the project's own files, soonest first, and whether the date has passed.
2. The project's own open lists: to-do, "not verified", open questions — lifted from inside the documents, not from file names. An item the newest log shows as done is not listed.
3. Seen broken, stale or contradictory by you, worst first, with what it costs.
No tidy-up ideas of your own.

#### 10. Words, and what was not read
- **Words:** build this last, from the finished page. Every acronym, code series and project term the page uses, one line each, with the file that defines it. No word the page does not use.
- **Not read:** folders and files you did not open, by name.
- **Searched and not found:** the thing, and what you searched for.

The server checks every `where` against the project folder and answers with `warnings`: paths it
did not find, and how many items do not say how you know. Fix them and write again: the same text
twice is one version.
