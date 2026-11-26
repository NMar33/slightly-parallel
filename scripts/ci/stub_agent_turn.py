"""The shared response plan for the interactive CLI test's local models."""

from __future__ import annotations

import json
import re

MARKER = re.compile(r"\bsp-stub-(hello|task-skill|task|decision|rule|done)(?: (tk_[0-9a-f]{8}))?\b")
TITLE = "Check the interactive stub task"
DECISION = "Use pytest for the interactive stub tests."
RULE = "Keep the interactive stub free of external requests."
REPLY = "Interactive stub turn completed."


def choose(items: list[dict], tools: list[str]) -> tuple[str, dict] | None:
    """Call a real MCP tool once, optionally load a skill, then acknowledge the turn."""
    blocks: list[dict] = []
    returned = False
    for item in reversed(items):
        content = item.get("content")
        parts = [part for part in content if isinstance(part, dict)] if isinstance(content, list) else []
        result = item.get("type") == "function_call_output" or any(part.get("type") == "tool_result" for part in parts)
        if not result and item.get("role") == "user" and (match := MARKER.search(json.dumps(content))):
            break
        returned = returned or result
        blocks.extend(parts)
    else:
        return None

    action, task = match.groups()
    if returned:
        if action != "task-skill" or "skill" not in tools:
            return None
        calls = {part["id"]: part.get("name", "") for part in blocks if part.get("type") == "tool_use" and part.get("id")}
        if "skill" not in calls.values() and any(
            part.get("type") == "tool_result" and not part.get("is_error")
            and calls.get(part.get("tool_use_id"), "").endswith("_write_entry")
            for part in blocks
        ):
            return "skill", {"name": "write-a-task"}
        return None
    if action in {"task", "task-skill"}:
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
