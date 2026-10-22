---
key: artifact
section: 4
title: Artifact
enabled: true
command: #artifact <what> | Write the folder under the project's artifacts/, then make its record with artifact_write (Artifact, section 4)
brief: **Artifact** (`#artifact`). The operator wants a result kept in one place and shown on the Artifacts page: a dataset, a document, a page or an app. Write the folder yourself at `<data_root>/projects/<project>/artifacts/<name>/`, then make its record with `artifact_write {id, name, kind, description}`. The skill `make-an-artifact` holds the steps.
---

**Artifact — `#artifact`.** The operator wants a result kept in one place
and shown on the Artifacts page: a dataset, a document, a page, an app.
The server keeps the message and the hook names the id and the path. You
write the folder yourself, with your own file tools, then make the record
with one call. The skill `make-an-artifact` holds the steps.

1. Write the folder at `<data_root>/projects/<project>/artifacts/<name>/`. The
   notice gives the first two parts; `<name>` is lowercase letters, digits
   and single hyphens. Put `ARTIFACT.md` on top: a `---` block with `name`,
   `kind` and `description`, then a short text on what is inside and how
   to use it. Put the files beside it. Any size.
2. Give the kind what it needs. `dataset`: one or more `*.jsonl` or `*.csv`
   files with a header, and the fields explained in `ARTIFACT.md`.
   `document`: one `*.md` file. `page`: `index.html` with its styles and
   scripts inline. `app`: the sources only — no `node_modules`, no `dist`
   or `build` — and a `run:` line in the `---` block that starts it.
   `other`: whatever it is, described.
3. Make the record: `artifact_write {id, name, kind, description}`. The
   server checks the folder is there and holds files, refreshes the
   `---` block, and the artifact appears on the page. The answer names
   what is wrong when it refuses.
4. After editing the folder, call `artifact_write` again with the same
   id. That is the update.

The folder is the artifact. Slightly Parallel reads it as it is; nothing is copied.
