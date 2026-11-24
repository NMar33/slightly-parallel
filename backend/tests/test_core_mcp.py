"""The core harness must deny an invalid write before the real MCP is called."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def policy(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "fresh_user"))
    from core_mcp import Guard, Plan

    plan = Plan(tmp_path)
    forwarded = []

    def handle(message):
        forwarded.append(message)
        return {
            "id": message.get("id"),
            "result": {"isError": False, "content": [{"type": "text", "text": "{}"}]},
        }

    return plan, Guard(plan.policy, plan.trace, handle, lambda _: []), forwarded


def request(name, args):
    return {"id": 1, "jsonrpc": "2.0", "method": "tools/call", "params": {"name": name, "arguments": args}}


@pytest.mark.parametrize(("tool", "args"), [
    ("write_entry", {"lens": "task"}),
    ("checkup", {"project": "side-effect"}),
    ("task_done", {}),
    ("checkup", None),
])
def test_rejects_wrong_call_before_dispatch_and_stays_closed(policy, tool, args):
    plan, guard, forwarded = policy
    plan.start("checkup", [["checkup", {}]])
    assert guard.dispatch(request(tool, args))["result"]["isError"]
    assert guard.dispatch(request("checkup", {}))["result"]["isError"]
    assert not forwarded
    assert plan.result() == (0, "MCP rejected unexpected call in checkup")


def test_accepts_exact_calls_in_order_and_rejects_extra_calls(policy):
    plan, guard, forwarded = policy
    plan.start("two reads", [["checkup", {}], ["task_done", {}]])
    first, second = request("checkup", {}), request("task_done", {})
    assert not guard.dispatch(first)["result"]["isError"]
    assert plan.result() == (1, "")
    assert not guard.dispatch(second)["result"]["isError"]
    assert plan.result() == (2, "")
    assert guard.dispatch(second)["result"]["isError"]
    assert forwarded == [first, second]
    assert json.loads(plan.trace.read_text().splitlines()[2])["request"] == second


def test_plan_checks_entire_scan_arguments_after_the_trigger_is_known(policy):
    from core_mcp import file_fields, form_fields, requests_for_scan, scan_fields

    plan, guard, forwarded = policy
    plan.start("#scan", requests_for_scan())
    counters = dict(files_n=2, lines_add=18, lines_del=0, decisions_n=1)
    responses = iter([{"counters": counters}, {"metadata": {"id": "sn_abcdef12"}}, {}, {}])

    def handle(message):
        forwarded.append(message)
        return {"result": {"isError": False, "content": [{"text": json.dumps(next(responses))}]}}

    guard.handle = handle
    valid = [
        request("scan_material", {}),
        request("write_entry", {"lens": "scan", "fields": scan_fields(counters)}),
        request("write_entry", {"lens": "file", "fields": file_fields("sn_abcdef12")}),
        request("write_entry", {"lens": "architecture", "fields": form_fields("sn_abcdef12")}),
    ]
    for call in valid[:3]:
        assert not guard.dispatch(call)["result"]["isError"]
    assert guard.dispatch(request("write_entry", {"lens": "architecture", "fields": form_fields("sn_bad")}))["result"]["isError"]
    assert forwarded == valid[:3]



def test_report_cannot_write_to_a_different_task(policy):
    plan, guard, forwarded = policy
    plan.start("#done", [["task_done", {}], ["task_report", {"id": "tk_expected", "summary": "Done."}]])
    done = request("task_done", {})
    assert not guard.dispatch(done)["result"]["isError"]
    assert guard.dispatch(request("task_report", {"id": "tk_other", "summary": "Done."}))["result"]["isError"]
    assert forwarded == [done]
