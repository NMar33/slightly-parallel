# Publish — what shipped, worth telling

The operator types `#publish` in a chat. The server keeps the message as a
**card** (`pu_…`) and the message stays on it as its source. The tag is an
instruction to the agent of that chat: the hook names the card and the agent
writes it in the same turn with the MCP tool `publish_write`:

- `#publish <text>` — the operator's text is the card's text, as is;
- `#publish about X`, "describe the timezone fix" — the agent writes the text
  from what was done;
- either way the agent writes the **context**, a block under the text (what
  was done, for whom, before and after, numbers), and attaches what belongs
  to the card: tasks (any project, by id), notes, commits (sha + repository),
  files (a local path: the file is copied onto the card), screenshots and
  links.

Each write of the text or the context is a version, with who wrote it. The
agent never rewrites the operator's text unless asked.

**Stored, not computed.** A card carries what was attached to it and nothing
else: the server does not take a task from the chat, nor a task's commits,
files or evidence images. A `tk_…` pasted inside the message attaches nothing.

**A card lives with the work.** `#publish pu_… <more>` from any chat of the
project adds the message to that card instead of making a new one; the agent
writes only what it asks for. When a chat types `#publish` again within an
hour of its last card, the hook names that card and the agent appends to it
(folding the new card in with `merge`) unless it is a different story. On the
page the operator merges any card into another, and takes a merge back.

The Publish page (`/publish`): the cards on the left, the **documents** the
operator makes on the right (a release note, a post, a video script — tabs),
each in **versions**. A card is placed into a document's current version with
one key or a drag; the text can be edited on the card and inside each
document (the item's text); every card shows its sources, text, context and
attachments, and its life: the original, its edits, and the documents and
versions it went into.

## Storage

- `publish.csv` + `publish_details/<…>.md` + `kept_versions/pu_….md` — the
  kept kind `publish` (keeplib): the message as typed, the text's versions
  (`interpret`; `by_agent` for an agent's write).
- `publish_context/<card>/context.md` — the context's versions (the same
  document format).
- `publish_writes.csv` — `id, card_id, part (text|context), n, at, actor, note`:
  who wrote each version.
- `publish_attachments.csv` — `id, card_id, kind, title, target, at, actor,
  removed_at, source, size`. Kinds: `image` (target: its file under
  `publish_images/<card>/`), `link` (the URL), `file` (its copy under
  `publish_files/<card>/<id>/`; source: the path it was copied from; size),
  `task` (tk_…), `note` (nt_…), `commit` (target: the sha; source: the
  repository; title: subject and date).
- `publish_sources.csv` — `id, card_id, from_card, project, agent_id,
  session_id, turn, at, text, actor, removed_at`: a message appended with
  `#publish pu_…` (id: the turn's keep id; from_card empty), or a card merged
  into this one (from_card; the merged card leaves the feed while the row
  stands).
- `publish_docs.csv` — `id, project, name, created_at, actor, archived_at`.
- `publish_versions.csv` — `id, doc_id, n, at, actor, note`.
- `publish_items.csv` — `id, doc_id, version_n, card_id, text, position, at, actor, removed_at`.

**Migration (once per data root, `publish_migration.json`).** Before this
change the server computed a card's task at every read (the `tk_` ids in the
message, else the last task named in the chat). At the first start the task
it would have shown is kept as a stored link (actor `migration`) only when
the task is of the card's own project; one of another project is dropped.
Commits, files and evidence images that came from the task are not kept.
`publish.csv` and `publish_attachments.csv` are copied first to
`publish-migration-<stamp>/` in the backup folder. A data root with no cards
gets the marker too, so a later card never gets a guessed task.

## Routes (routers/publish.py)

`GET /api/publishing?project=` → `{project, cards, docs}` (every route of the
page is under `/api/publishing/…`; `/api/publish` is the kept entity's own
lens list)

- `cards[]`: `id, project, agent_id, session_id, source_turn, at` (ISO),
  `message` (as typed, the tag taken out), `sources[]` (`id, kind
  (kept|appended|merged), at, agent_id, turn, text, from_card`), `text` (the
  last version, else the message), `versions[]` (`n, at, text, note, by`),
  `context`, `context_versions[]`, `rev` (text and context versions
  together: the `base` a write names), `tasks[]` (`id, title, status,
  project, attachment_id`), `notes[]`, `commits[]` (`sha, subject, at, repo,
  attachment_id`), `files[]` (`id, name, path, size, url`), `images[]`,
  `links[]`, `cores[]` (the attached tasks' cores), `merged_from[]`,
  `placements[]`, `archived_at`. Newest first; a merged card is not listed.
- `docs[]`: `id, project, name, created_at, archived_at, current`,
  `versions[]` (`n, at, actor, note, items[]` with `id, card_id, text,
  position, changed`).

`GET /api/publishing/cards/{id}` → the card (a merged card's id answers the
card it went into), plus `history[]`: `kept` · `appended` · `merged` ·
`written` · `edited` · `context` · `placed` · `removed from`, oldest first.

Writes (JSON bodies; `actor: "operator"` or the operator cookie, or an agent
through MCP where said):

- `POST /api/publishing/cards/{id}/write` `{text?, context?, note?, base?,
  tasks?, notes?, commits?: [{sha, repo?}], links?: [{title, url}], files?:
  [{name, title, source, data_base64}], images?: [{title, ext, data_base64}],
  merge?}` → `{id, rev, wrote, attached, card, page, reply}`. The agent (MCP
  `publish_write`, which reads `files` and `images` from their `path`) or the
  operator. The id may be a card, an appended message's id, or a merged card.
  Everything is checked before anything is written: a task or note that does
  not exist, a commit the repository does not hold (repo left out: the
  project's registered one), a link that is not http(s), a file over 25MB, a
  stale `base`, an agent of another project. `merge` folds a card in (an
  agent: only a card of its own chat). The same attachment again is the
  existing one; an attachment the operator removed comes back.
- `POST /api/publishing/cards/{id}/attach` — the older door (MCP
  `publish_attach`, forwarding to `publish_write`; the page's drop and paste):
  attachments only → `{attached, card}` (201).
- `POST /api/publishing/cards/{id}/text` `{text, note?}` → `{card}`: the
  operator's version of the text.
- `POST /api/publishing/cards/{id}/merge` `{into}` → `{card}`: the operator
  folds this card into another of the project.
- `POST /api/publishing/sources/{id}/remove` → `{removed, card_id,
  from_card}`: a merge taken back (the card returns), or an appended message
  dropped.
- `POST /api/publishing/cards` `{project, text}` → `{card, existing}` (201): a
  card written by hand on the page (`source: page`).
- `POST /api/publishing/docs` `{project, name}` → `{doc, existing}` (201; the
  same name answers 200 with the existing doc; version 1 is made with it).
- `POST /api/publishing/docs/{id}/update` `{name?, archived?}` → `{doc}`.
- `POST /api/publishing/docs/{id}/versions` `{note?}` → `{doc}`: the next
  version, with the current version's items copied.
- `POST /api/publishing/docs/{id}/items` `{card_id, text?, before?}` → `{item,
  existing}`: the card placed into the current version.
- `POST /api/publishing/items/{id}/update` `{text?, before?}` → `{item}`.
- `POST /api/publishing/items/{id}/remove` → `{removed: true}`.
- `GET /api/publishing/docs/{id}/markdown?n=` → `text/markdown`.
- `GET /api/publishing/attachments/{id}/file` → the image, or the file under
  its own name.
- `POST /api/publishing/attachments/{id}/remove` → `{removed: true}` (the
  operator's).

Refusals: a name over 80 characters, a text over 20 000, an unknown card or
doc, a card of another project.
