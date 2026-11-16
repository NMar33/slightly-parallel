# Publish — what shipped, worth telling

The operator tags a message in a chat with `#publish`: the server keeps it as a
**card** (`pu_…`), the way `#vision` keeps a vision. Nothing is asked of the
agent. The Publish page (`/publish`) is the operator's: a feed of the cards on
the left, the **documents** the operator makes on the right (a release note, a
post, a video script — tabs), each in **versions**. A card is placed into a
document's current version with one key or a drag; the text can be edited on
the card (its versions, U1, U2 …) and inside each document (the item's text);
every card shows its whole life: the original, its edits, and the documents and
versions it went into — like branches.

Only the operator writes here: an agent's write is refused (`AGENT_REFUSED`).

## Storage

- `publish.csv` + `publish_details/<…>.md` + `kept_versions/pu_….md` — the
  kept kind `publish` (keeplib): the message as typed, the operator's edits as
  versions (`versions_n`, `interpret` with `by_agent=False`).
- `publish_docs.csv` — `id, project, name, created_at, actor, archived_at`.
- `publish_versions.csv` — `id, doc_id, n, at, actor, note`.
- `publish_items.csv` — `id, doc_id, version_n, card_id, text, position, at, actor, removed_at`.

## Routes (routers/publish.py)

`GET /api/publishing?project=` → `{project, cards, docs}` (every route of the page is under `/api/publishing/…`; `/api/publish` is the kept entity's own lens list)

- `cards[]`: `id, project, agent_id, session_id, source_turn, at` (ISO),
  `message` (as typed, the `#publish` tag taken out), `text` (the current
  text: the last edit, else the message), `versions[]` (`n, at, text, note`),
  `tasks[]` (`id, title, status` — the tasks the message names, else the
  chat's task at that turn), `cores[]` (`id, name, type` — the tasks' cores),
  `commits[]` (`sha, subject, at` — the tasks' commits), `images[]`
  (`url, label` — the tasks' evidence images), `placements[]` (`doc_id,
  doc_name, version_n, item_id, text, changed`), `archived_at`. Newest first.
- `docs[]`: `id, project, name, created_at, archived_at, current` (the latest
  version number), `versions[]` (`n, at, actor, note, items[]` with
  `id, card_id, text, position, changed` — `changed` is true when the item's
  text differs from the card's current text).

`GET /api/publishing/cards/{id}` → the card, plus `history[]` (`at, what, doc_id,
doc_name, version_n, text`): `kept` · `edited` · `placed` · `edited in` ·
`removed from`, oldest first.

Writes (JSON bodies; `actor: "operator"` or the operator cookie):

- `POST /api/publishing/cards` `{project, text}` → `{card, existing}` (201): a
  card written by hand on the page (`source: page`), beside the ones kept
  from a chat. The same text in the same minute is the same card.
- `POST /api/publishing/cards/{id}/text` `{text, note?}` → `{card}`. A new version
  of the card's text; the same text again is no version.
- `POST /api/publishing/docs` `{project, name}` → `{doc, existing}` (201; the same
  name in the project answers 200 with the existing doc; version 1 is made
  with it).
- `POST /api/publishing/docs/{id}/update` `{name?, archived?}` → `{doc}`.
- `POST /api/publishing/docs/{id}/versions` `{note?}` → `{doc}`: the next version,
  with the current version's items copied.
- `POST /api/publishing/docs/{id}/items` `{card_id, text?, before?}` → `{item,
  existing}`: the card placed into the current version (text defaults to the
  card's current text; `before` an item id to land in front of, else last).
  The same card in the same version answers the existing item.
- `POST /api/publishing/items/{id}/update` `{text?, before?}` → `{item}`.
- `POST /api/publishing/items/{id}/remove` → `{removed: true}`.
- `GET /api/publishing/docs/{id}/markdown?n=` → `text/markdown`: the version's
  items in order, one paragraph each, with the document's name as the title.
- `POST /api/publishing/cards/{id}/attach` `{images?: [{title, ext, data_base64}],
  links?: [{title, url}]}` → `{attached: [{id, kind, title, existing}], card}`.
  The operator on the page (a drop or a paste of an image), or the agent with
  the MCP tool `publish_attach` right after the hook's `#publish` notice (1–3
  screenshots of what it is about, the links). Through the tool an image is
  given by its `path` on the machine; the translator reads and encodes it. The same image or link again
  is the existing attachment. Images live under `publish_images/<card>/`.
- `GET /api/publishing/attachments/{id}/file` → the image.
- `POST /api/publishing/attachments/{id}/remove` → `{removed: true}` (the operator's).

The card also carries what the server finds by itself: `files[]` (`path, add,
del` — the tasks' files, biggest change first, at most 12), `images[]` with
`from` = `evidence` | `story` | `attached` (and `id`, `by` for attached ones),
`links[]` (`url, label, id, by`).

Refusals: a name over 80 characters, a text over 20 000, an unknown card or
doc, a card of another project.
