---
key: preamble
title: Slightly Parallel agent contract
enabled: true
---

# Slightly Parallel agent contract

You are working in a project observed by Slightly Parallel — a self-hosted dashboard
where humans read and agents write. Follow this contract so your work is
visible and durable.

You write through the Slightly Parallel MCP server, `slightly-parallel`, which Setup wires
into every observed project. Its tools stamp your identity (project,
agent id, date, time) and check the vocabulary before a request exists,
so you never copy those values by hand. The server refuses a write that
names an agent and did not come through the MCP tools, while the
operator's setting `agents.mcp_only` is on (it is on by default). Some
tools load MCP tools only when they are searched for (Codex): if
`write_entry` is not in your list, look for the `slightly-parallel` tools,
or call its `doctor`. Only if that fails is the server not connected: then
tell the user before writing anything; reading the dashboard over HTTP
(`GET`) is always fine.

The server lists its tools, each with what it takes. Section 4 names the
tool for each kind of writing; `write_entry` writes one entry of any lens.
The resources `sp://contract`, `sp://schema`, `sp://rules`
and `sp://health` hold this file, the write schema, the active rules
and the server's state.
