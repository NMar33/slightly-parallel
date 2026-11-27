"""Test-only policy for the disposable Codex core's stdio MCP server."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from uuid import uuid4


def _load_mcp_args():
    """The product's table of MCP tool arguments (backend/backend/mcp_args.py),
    loaded by path: the guard's allowlist is the product's, never a copy."""
    import importlib.util
    path = Path(__file__).resolve().parents[2] / "backend" / "backend" / "mcp_args.py"
    spec = importlib.util.spec_from_file_location("sp_mcp_args", path)
    assert spec is not None and spec.loader is not None, path
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mcp_args = _load_mcp_args()


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
            if "argument_keys" in first:
                keys = ", ".join(first["argument_keys"]) or "(none)"
                detail += f"\nMCP argument keys: {keys} ({first['unadvertised_keys']} unadvertised)"
            return 0, f"MCP {first['result']} in {first['name']}{detail}"
        return sum(event["turn"] == self.turn for event in events), ""


def requests_for_scan():
    return [
        ["scan_material", {}],
        ["write_entry", {"lens": "scan", "fields": {"$scan_fields": True}}],
        ["write_entry", {"lens": "file", "fields": {"$file_fields": True}}],
        ["write_entry", {"lens": "architecture", "fields": {"$form_fields": True}}],
    ]


def not_taken(name, args):
    """The top-level arguments the product's tool does not take (mcp_args):
    refused before the exact comparison with the fixture."""
    if not isinstance(args, dict):
        return []
    takes = mcp_args.accepts(name)
    return sorted(k for k in args if k not in takes)


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
        self.advertised_arguments: dict[str, set[str]] = {}

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
        method = message.get("method")
        if method != "tools/call":
            response = self.handle(message)
            if method == "tools/list" and response:
                for tool in (response.get("result") or {}).get("tools", []):
                    self.advertised_arguments[tool["name"]] = set(tool["inputSchema"].get("properties", {}))
            return response
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
            extra = not_taken(expected, args) if name == expected else ()
            if extra:
                reason = f"arguments has {len(extra)} unadvertised field" + ("s" if len(extra) > 1 else "")
            elif name == expected and wanted is not None and json.dumps(args, sort_keys=True) == json.dumps(wanted, sort_keys=True):
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
        event = {"turn": self.turn, "name": policy["name"], "result": outcome,
                 "reason": reason, "request": message, "scan_id": self.scan_id, "counters": self.counters}
        advertised = self.advertised_arguments.get(name) if isinstance(name, str) else None
        if outcome != "accepted" and isinstance(args, dict) and advertised is not None:
            # Only the server's own schema can contribute text to the public report.
            event.update(argument_keys=sorted(args.keys() & advertised),
                         unadvertised_keys=len(args.keys() - advertised))
        with self.trace.open("a", encoding="utf-8") as log:
            log.write(json.dumps(event, ensure_ascii=False) + "\n")
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
