"""The shared response plan for the interactive CLI test's local models."""

from __future__ import annotations

import json
import re

MARKER = re.compile(r"\bsp-stub-(hello|task|decision|rule|done)(?: (tk_[0-9a-f]{8}))?\b")
TITLE = "Check the interactive stub task"
DECISION = "Use pytest for the interactive stub tests."
RULE = "Keep the interactive stub free of external requests."
REPLY = "Interactive stub turn completed."


def choose(items: list[dict], tools: list[str]) -> tuple[str, dict] | None:
    """Call a real MCP tool once, then acknowledge its result on the same turn."""
    for item in reversed(items):
        content = item.get("content")
        if item.get("type") == "function_call_output" or (
            isinstance(content, list) and any(block.get("type") == "tool_result"
                                              for block in content if isinstance(block, dict))
        ):
            return None
        if item.get("role") != "user":
            continue
        match = MARKER.search(json.dumps(content))
        if match:
            break
    else:
        return None

    action, task = match.groups()
    if action == "task":
        suffix, arguments = "write_entry", {"lens": "task", "fields": {
            "title": TITLE, "description": TITLE, "tags": ["ag_followup"],
        }}
    elif action == "decision":
        suffix, arguments = "write_entry", {"lens": "decision", "fields": {"decision": DECISION}}
    elif action == "done" and task:
        suffix, arguments = "task_done", {}
    else:
        return None  # the operator's rule is written by the capture hook
    name = next((name for name in tools if name.endswith("_" + suffix)), None)
    return (name, arguments) if name else None
