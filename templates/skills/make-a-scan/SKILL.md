---
name: make-a-scan
description: "Write a Slightly Parallel scan: what this chat changed in the project since its last scan, committed or not, then the file entry and the architecture form the scan triggers. Use only when the operator types #scan. Never on your own."
---

A scan is a checkpoint the operator asks for. It is three entries, written
in this order. You may offer a scan after shipping or before a risky
change. The operator decides.

1. **Get the material.** Call `scan_material`. The answer holds your last
   scan of the project, this chat's commits since it (`window` says how it
   was drawn), the files with line counts, the uncommitted files, the
   `counters` already counted, and the `instructions` for all three
   entries. Follow those instructions: they are the operator's current
   ones. `others_commits_n` are commits made outside this chat since your
   last scan: not yours to describe. `touched` lists the files this
   chat's tool calls changed (its helpers' too), git or no git. Without a
   repository `changed` adds the files found changed in the folder during
   this chat's turns — a shell command's edits, and anyone else's: keep
   only what this chat did. The file entry's `paths` come from the two. An uncommitted
   file with `mine: false` was changed by someone else in the same
   folder: leave it out. With no commits
   of your own, nothing uncommitted and nothing touched, tell the operator
   there is nothing to scan, and stop. Commits under `already_described` are work the last scan covered
   before it was committed: leave them out.
2. **Write the scan** — `write_entry {lens: "scan"}`. Copy the counters
   from the answer as they are. Keep the scan's id from the reply. The
   fields and their budgets are under *Checkpoint* below.
3. **Write the file entry** — `write_entry {lens: "file"}`, with the
   scan's id as `trigger_id`. The fields are under *File entry* below.
4. **Write the architecture form** — `write_entry {lens: "architecture"}`,
   with the scan's id as `trigger_id`. The eight groups are under
   *Architecture* below.
5. **Update the architecture page** when the scan changed what the project
   is, does or owes: call `architecture_material`, then write the next
   version with `architecture_page`. The skill `keep-the-architecture-page`
   holds the steps. A scan of small fixes changes nothing on the page: skip it.
6. **Tell the operator** the scan's summary line, in one sentence.

{{part:scan}}

{{part:file-entry}}

{{part:architecture}}

{{writing-rules}}

Check: the reply to the scan carries `warnings` until the file entry and
the architecture form exist. Read the scan again with its id: no warnings
means all three are there. Open Scans in Slightly Parallel: the row shows what
landed.

Mistakes to avoid: writing a scan nobody asked for; counting the lines
yourself; a delta per file where it should be one per change a user or an
agent can see; stopping after the scan with the other two entries owed;
file names and commit hashes in the scan's text.
