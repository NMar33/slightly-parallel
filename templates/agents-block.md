## Slightly Parallel

This project is observed by Slightly Parallel (self-hosted agent dashboard).
Chat capture is automatic — your job is writing entries through the
Slightly Parallel MCP tools when the contract says so.

- Project code: `$project_code`
- Contract: read `$contract` at the start of every chat
  and follow it. It defines the commands (#scan, #decision, #task,
  #vision, …), when to write which entry, and what each entry holds.
- Writing: the MCP server `slightly-parallel` (wired into this project by Setup).
  The server lists its tools; `write_entry` writes one entry. Identity
  is stamped for you. Writes from an agent that bypass the MCP tools are
  refused by the server. If the `slightly-parallel` MCP server is not connected in this chat,
  tell the user before writing anything.
- Server: $api_url (reading, and the operator's own pages)
- Data root: `$data_root`
- Capture check: in Claude Code, Slightly Parallel's hook prints
  `[slightly-parallel] project … · your agent_id is …` on the first turn. If that
  line did not appear, capture is not active in the directory the tool
  was started in (hooks are installed per directory, at `$project_dir`):
  tell the user before doing anything else. Codex and OpenCode show no
  such line; there, a refused MCP write that says "no captured session"
  means the same.$notes_line
