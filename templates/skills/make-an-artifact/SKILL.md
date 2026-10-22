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

{{part:artifact}}

Check: `GET /api/artifacts/<id>` answers with `artifact.exists: true` and
the files you wrote.

Mistakes to avoid: writing the folder anywhere but under the project's `artifacts/`;
copying dependencies or build output into an app; leaving `description`
empty; sending the files through the tool — the tool takes the record
only, the folder is written by you.
