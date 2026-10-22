---
id: sk_69d2bfe3
kind: skill
---

## Version 1 · 2609-18 14:08 · edited
> Built into Slightly Parallel

---
name: make-an-artifact
description: "Make an artifact: a folder Slightly Parallel shows on the Artifacts page — a dataset, a document, a page or an app. Use when the operator types #artifact or asks to keep a result as an artifact."
---

An artifact is a folder under the Slightly Parallel directory. You write it with
your own file tools, then make its record with one MCP call.

1. Read the `[slightly-parallel] #artifact` notice. It gives the id (`ar_…`) and the
   path `<data_root>/artifacts/<project>/`. Pick `<name>`: lowercase
   letters, digits and single hyphens.
2. Write the folder at `<data_root>/artifacts/<project>/<name>/`.
   - `ARTIFACT.md` on top: a `---` block with `name`, `kind` and
     `description`, then a short text on what is inside and how to use it.
   - The files beside it. Any size.
3. Give the kind what it needs.
   - `dataset`: `*.jsonl` or `*.csv` files with a header; explain the
     fields in `ARTIFACT.md`.
   - `document`: one `*.md` file.
   - `page`: `index.html` with styles and scripts inline.
   - `app`: the sources only, no `node_modules`, `dist` or `build`, and a
     `run:` line in the `---` block that starts it.
   - `other`: whatever it is, described.
4. Call the MCP tool `artifact_write {id, name, kind, description}`. The
   server checks the folder, refreshes the `---` block, and the artifact
   appears on the Artifacts page. If it refuses, the answer names what is
   wrong: fix it and call again.
5. After editing the folder later, call `artifact_write` again with the
   same id. That is the update.

Check: `GET /api/artifacts/<id>` answers with `artifact.exists: true` and
the files you wrote.

Mistakes to avoid: writing the folder anywhere but under `artifacts/`;
copying dependencies or build output into an app; leaving `description`
empty; sending the files through the tool — the tool takes the record
only, the folder is written by you.

## Version 2 · 2609-18 15:08 · edited
> Built into Slightly Parallel

---
name: make-an-artifact
description: "Make an artifact: a folder Slightly Parallel shows on the Artifacts page — a dataset, a document, a page or an app. Use when the operator types #artifact or asks to keep a result as an artifact."
---

An artifact is a folder under the Slightly Parallel directory. You write it with
your own file tools, then make its record with one MCP call.

1. Read the `[slightly-parallel] #artifact` notice. It gives the id (`ar_…`) and the
   path `<data_root>/projects/<project>/artifacts/`. Pick `<name>`: lowercase
   letters, digits and single hyphens.
2. Write the folder at `<data_root>/projects/<project>/artifacts/<name>/`.
   - `ARTIFACT.md` on top: a `---` block with `name`, `kind` and
     `description`, then a short text on what is inside and how to use it.
   - The files beside it. Any size.
3. Give the kind what it needs.
   - `dataset`: `*.jsonl` or `*.csv` files with a header; explain the
     fields in `ARTIFACT.md`.
   - `document`: one `*.md` file.
   - `page`: `index.html` with styles and scripts inline.
   - `app`: the sources only, no `node_modules`, `dist` or `build`, and a
     `run:` line in the `---` block that starts it.
   - `other`: whatever it is, described.
4. Call the MCP tool `artifact_write {id, name, kind, description}`. The
   server checks the folder, refreshes the `---` block, and the artifact
   appears on the Artifacts page. If it refuses, the answer names what is
   wrong: fix it and call again.
5. After editing the folder later, call `artifact_write` again with the
   same id. That is the update.

Check: `GET /api/artifacts/<id>` answers with `artifact.exists: true` and
the files you wrote.

Mistakes to avoid: writing the folder anywhere but under the project's `artifacts/`;
copying dependencies or build output into an app; leaving `description`
empty; sending the files through the tool — the tool takes the record
only, the folder is written by you.

## Version 3 · 2609-22 19:21 · edited
> Built into Slightly Parallel

---
name: make-an-artifact
description: "Make an artifact: a folder Slightly Parallel shows on the Artifacts page — a dataset, a document, a page or an app. Use when the operator types #artifact or asks to keep a result as an artifact."
---

An artifact is a folder under the Slightly Parallel directory. You write it with
your own file tools, then make its record with one MCP call.

1. **Read the `[slightly-parallel] #artifact` notice.** It gives the id (`ar_…`) and
   the folder the artifact goes in. Pick `<name>`: lowercase letters,
   digits and single hyphens.
2. **Write the folder**, then **make the record** with
   `artifact_write {id, name, kind, description}`. The four steps and what
   each kind needs are below.
3. **Tell the operator** in one sentence what the artifact holds and where
   it is.

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

Check: `GET /api/artifacts/<id>` answers with `artifact.exists: true` and
the files you wrote.

Mistakes to avoid: writing the folder anywhere but under the project's `artifacts/`;
copying dependencies or build output into an app; leaving `description`
empty; sending the files through the tool — the tool takes the record
only, the folder is written by you.

## Version 4 · 2610-06 19:49 · edited
> Built into Slightly Parallel

---
name: make-an-artifact
description: "Make an artifact: a folder Slightly Parallel shows on the Artifacts page — a dataset, a document, a page or an app. Use when the operator types #artifact or asks to keep a result as an artifact."
---

An artifact is a folder under the Slightly Parallel directory. You write it with
your own file tools, then make its record with one MCP call.

1. **Read the `[slightly-parallel] #artifact` notice.** It gives the id (`ar_…`) and
   the folder the artifact goes in. Pick `<name>`: lowercase letters,
   digits and single hyphens.
2. **Write the folder**, then **make the record** with
   `artifact_write {id, name, kind, description}`. The four steps and what
   each kind needs are below.
3. **Tell the operator** in one sentence what the artifact holds and where
   it is.

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

Check: `GET /api/artifacts/<id>` answers with `artifact.exists: true` and
the files you wrote.

Mistakes to avoid: writing the folder anywhere but under the project's `artifacts/`;
copying dependencies or build output into an app; leaving `description`
empty; sending the files through the tool — the tool takes the record
only, the folder is written by you.

## Version 5 · 2610-06 20:00 · edited
> Built into Slightly Parallel

---
name: make-an-artifact
description: "Make an artifact: a folder Slightly Parallel shows on the Artifacts page — a dataset, a document, a page or an app. Use when the operator types #artifact or asks to keep a result as an artifact."
---

An artifact is a folder under the Slightly Parallel directory. You write it with
your own file tools, then make its record with one MCP call.

1. **Read the `[slightly-parallel] #artifact` notice.** It gives the id (`ar_…`) and
   the folder the artifact goes in. Pick `<name>`: lowercase letters,
   digits and single hyphens.
2. **Write the folder**, then **make the record** with
   `artifact_write {id, name, kind, description}`. The four steps and what
   each kind needs are below.
3. **Tell the operator** in one sentence what the artifact holds and where
   it is.

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

Check: `GET /api/artifacts/<id>` answers with `artifact.exists: true` and
the files you wrote.

Mistakes to avoid: writing the folder anywhere but under the project's `artifacts/`;
copying dependencies or build output into an app; leaving `description`
empty; sending the files through the tool — the tool takes the record
only, the folder is written by you.
