"""Test-only policy for the disposable Codex core's stdio MCP server."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import uuid4


SCAN_SUMMARY = "The calculator now subtracts and has tests for addition and subtraction."
SCAN_GROUPS = ["does", "owes", "runs", "stores", "talks", "built with", "faces", "holds"]
RULE_TEXT = "Keep calc.py standalone."
RULE_POLL_INTERVAL_S = 0.1
RULE_CAPTURE_TIMEOUT_S = 4
OFFLINE_EDIT = r"printf '\ndef sub(a, b):\n    return a - b\n' >> calc.py"
OFFLINE_TESTS = (r"printf 'from calc import add, sub\n\ndef test_calc():\n"
                 r"    assert add(2, 3) == 5\n    assert sub(3, 2) == 1\n' > test_calc.py")
EDIT_POWERSHELL = "Add-Content -LiteralPath {path} -Value @('', 'def sub(a, b):', '    return a - b')"
TESTS_POWERSHELL = ("Set-Content -LiteralPath {path} -Value @('from calc import add, sub', '', "
                    "'def test_calc():', '    assert add(2, 3) == 5', '    assert sub(3, 2) == 1')")


def scan_fields(counters):
    return {"summary": SCAN_SUMMARY, **{key: counters[key] for key in (
        "files_n", "lines_add", "lines_del", "decisions_n",
    )}}


def file_fields(scan_id):
    return {
        "summary": "Calculator implementation and tests",
        "trigger_id": scan_id,
        "trigger_lens": "scan",
        "paths": [
            {"path": "calc.py", "importance": 3, "blast_radius": 2,
             "test_coverage": "covered", "novelty": "pattern-follow", "security_surface": False,
             "why": "Adds subtraction."},
            {"path": "test_calc.py", "importance": 3, "blast_radius": 2,
             "test_coverage": "covered", "novelty": "new", "security_surface": False,
             "why": "Tests both operations."},
        ],
    }


def form_fields(scan_id):
    return {"trigger_id": scan_id, "checked": SCAN_GROUPS, "changes": []}


class Plan:
    def __init__(self, folder: Path):
        self.policy = folder / "core-mcp.json"
        self.trace = folder / "core-mcp.jsonl"
        self.turn = ""
        self.expected = 0

    def start(self, name, calls=(), *, rule=None, shell=()):
        self.turn = uuid4().hex
        self.expected = len(calls)
        tmp = self.policy.with_suffix(".tmp")
        tmp.write_text(json.dumps({"turn": self.turn, "name": name, "calls": calls, "rule": rule, "shell": shell}), encoding="utf-8")
        tmp.replace(self.policy)

    def result(self):
        if not self.trace.exists():
            return 0, ""
        events = [json.loads(line) for line in self.trace.read_text(encoding="utf-8").rpartition("\n")[0].splitlines() if line]
        errors = [event for event in events if event["result"] != "accepted"]
        if errors:
            first = errors[0]
            detail = f" ({first['reason']})" if first.get("reason") else ""
            return 0, f"MCP {first['result']} in {first['name']}{detail}"
        return sum(event["turn"] == self.turn for event in events), ""


def requests_for_scan():
    return [
        ["scan_material", {}],
        ["write_entry", {"lens": "scan", "fields": {"$scan_fields": True}}],
        ["write_entry", {"lens": "file", "fields": {"$file_fields": True}}],
        ["write_entry", {"lens": "architecture", "fields": {"$form_fields": True}}],
    ]


def _argument_mismatch(wanted, actual, path="arguments"):
    """Explain a mismatch using fixture field names, never model text."""
    if type(wanted) is not type(actual):
        return f"{path} has the wrong type"
    if isinstance(wanted, dict):
        if missing := sorted(wanted.keys() - actual.keys()):
            return f"{path} is missing {', '.join(missing)}"
        if extra := len(actual.keys() - wanted.keys()):
            return f"{path} has {extra} extra field" + ("s" if extra > 1 else "")
        for key, value in wanted.items():
            if json.dumps(actual[key], sort_keys=True) != json.dumps(value, sort_keys=True):
                return _argument_mismatch(value, actual[key], f"{path}.{key}")
    return f"{path} differs from the fixture"


class Guard:
    def __init__(self, policy: Path, trace: Path, handle, rules):
        self.policy = policy
        self.trace = trace
        self.handle = handle
        self.rules = rules
        self.turn = ""
        self.index = 0
        self.scan_id = ""
        self.counters = {}
        self.failed = False

    def _arguments(self, template, rule):
        if "$rule_id" in template:
            end = time.monotonic() + RULE_CAPTURE_TIMEOUT_S
            before = set(rule["before"])
            while True:
                new = {row["id"] for row in self.rules(rule) if row.get("agent_id") == rule["agent"]} - before
                if len(new) == 1:
                    return {**template["$rule_id"], "id": new.pop()}
                if new or time.monotonic() >= end:
                    raise ValueError("expected one new rule")
                time.sleep(RULE_POLL_INTERVAL_S)
        if isinstance(fields := template.get("fields"), dict):
            if fields == {"$scan_fields": True}:
                return {**template, "fields": scan_fields(self.counters)}
            if fields == {"$file_fields": True} and self.scan_id:
                return {**template, "fields": file_fields(self.scan_id)}
            if fields == {"$form_fields": True} and self.scan_id:
                return {**template, "fields": form_fields(self.scan_id)}
        return template

    def dispatch(self, message):
        if message.get("method") != "tools/call":
            return self.handle(message)
        policy = json.loads(self.policy.read_text(encoding="utf-8"))
        if policy["turn"] != self.turn:
            self.turn, self.index = policy["turn"], 0
            self.scan_id, self.counters = "", {}
        params = message.get("params") or {}
        name, args = params.get("name"), params.get("arguments", {})
        reply = None
        outcome = "rejected unexpected call"
        reason = ""
        calls = policy["calls"]
        if not self.failed and self.index < len(calls) and message.get("id") is not None:
            expected, template = calls[self.index]
            try:
                wanted = self._arguments(template, policy.get("rule"))
            except (KeyError, ValueError):
                wanted = None
            if name == expected and wanted is not None and json.dumps(args, sort_keys=True) == json.dumps(wanted, sort_keys=True):
                self.index += 1
                reply = self.handle(message)
                result = (reply or {}).get("result") or {}
                outcome = "server refused call" if result.get("isError", True) else "accepted"
                if outcome == "accepted" and (name == "scan_material" or args.get("lens") == "scan"):
                    try:
                        data = json.loads(result["content"][0]["text"])
                        if name == "scan_material":
                            self.counters = data["counters"]
                        else:
                            self.scan_id = data.get("id") or data["metadata"]["id"]
                            if not re.fullmatch(r"sn_[0-9a-f]+", self.scan_id):
                                raise ValueError("invalid scan id")
                    except (KeyError, ValueError, TypeError, IndexError):
                        outcome = "invalid scan result"
            elif name == expected and wanted is not None:
                reason = _argument_mismatch(wanted, args)
        if outcome != "accepted":
            self.failed = True
        with self.trace.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"turn": self.turn, "name": policy["name"], "result": outcome,
                                  "reason": reason, "request": message, "scan_id": self.scan_id,
                                  "counters": self.counters}, ensure_ascii=False) + "\n")
        if reply is not None:
            return reply
        return {"jsonrpc": "2.0", "id": message.get("id"), "result": {
            "isError": True, "content": [{"type": "text", "text": "Unexpected call in the disposable core test."}],
        }}


def main():
    from backend import mcp

    policy, trace = map(Path, sys.argv[1:])
    api = mcp.Api(os.environ["SP_API"])
    translator = mcp.Translator(api, os.getcwd())
    mcp._utf8_pipes()

    def rules(rule):
        return api.get(f"/api/rules?project={rule['project']}&limit=200")["rules"]

    # Only one session may consume the plan. A reconnect fails closed.
    with policy.with_suffix(".owner").open("x"):
        guard = Guard(policy, trace, lambda msg: mcp.handle(translator, msg), rules)
        for line in sys.stdin:
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    continue
                reply = guard.dispatch(message)
            except (TypeError, ValueError, OSError, KeyError, AttributeError):
                return 1
            if reply is not None:
                print(json.dumps(reply, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
