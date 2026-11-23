from pathlib import Path
from runpy import run_path

import pytest

PLAN = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "stub_agent_turn.py"


@pytest.mark.parametrize("name", ["slightly-parallel_write_entry", "mcp__slightly-parallel__write_entry"])
def test_stub_requests_a_real_tool_once_per_operator_turn(name):
    choose = run_path(str(PLAN))["choose"]
    history = [{"role": "user", "content": "#task sp-stub-task"}]
    assert choose(history, [name]) == (name, {"lens": "task", "fields": {
        "title": "Check the interactive stub task", "description": "Check the interactive stub task", "tags": ["ag_followup"],
    }})
    output = {"type": "function_call_output", "output": "created"}
    assert choose([*history, output], [name]) is None
    next_turn = {"role": "user", "content": [{"type": "text", "text": "#decision sp-stub-decision"}]}
    assert choose([*history, output, next_turn], [name])[1]["lens"] == "decision"


def test_stub_cannot_invent_an_unavailable_mcp_tool():
    choose = run_path(str(PLAN))["choose"]
    prompt = {"role": "user", "content": "#done tk_a123bcde sp-stub-done tk_a123bcde"}
    assert choose([prompt], ["shell"]) is None
    assert choose([prompt], ["mcp__slightly_parallel__task_done"]) == ("mcp__slightly_parallel__task_done", {})
