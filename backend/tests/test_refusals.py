"""A refusal names every reason (tk_90c1ba5f): the collector, the wire and
the MCP translator's text. One reason reads as before, to the byte."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend import mcp
from backend.actors import refuse_agent
from backend.refusals import Reasons, Refused
from backend.server import create_app


def test_two_reasons_give_both_lines_and_the_first_status() -> None:
    got = Reasons().add("no access", "ask the operator", status=403, code="member")
    got.add("the title is long", "keep it under 80", code="title", field="title")
    with pytest.raises(Refused) as exc:
        got.raise_if_any()
    assert exc.value.status_code == 403
    assert exc.value.detail == "no access — ask the operator\nthe title is long — keep it under 80"
    assert exc.value.body()["reasons"] == [
        {"reason": "no access", "instead": "ask the operator", "code": "member"},
        {"reason": "the title is long", "instead": "keep it under 80", "code": "title", "field": "title"},
    ]


def test_one_reason_is_the_detail_refuse_agent_always_gave() -> None:
    with pytest.raises(HTTPException) as old:
        refuse_agent("a status is the operator's", "comment instead")
    with pytest.raises(Refused) as new:
        Reasons().add("a status is the operator's", "comment instead").raise_if_any()
    assert new.value.detail == old.value.detail
    assert new.value.status_code == old.value.status_code
    with pytest.raises(Refused) as bare:
        Reasons().add("just a line").raise_if_any()
    assert bare.value.detail == "just a line"


def test_no_reason_raises_nothing() -> None:
    Reasons().raise_if_any()
    assert not Reasons().add_pair(None)


def test_the_server_answers_detail_and_reasons(data_root: Path) -> None:
    app = create_app(data_root=data_root, watch=False)
    handler = app.exception_handlers[Refused]
    two = Refused(Reasons().add("a", "x", status=409).add("b").items)
    resp = handler(None, two)
    assert resp.status_code == 409
    body = json.loads(bytes(resp.body))
    assert body["detail"] == "a — x\nb"
    assert isinstance(body["detail"], str)
    assert [r["reason"] for r in body["reasons"]] == ["a", "b"]


def _http_error(body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x/api/y", 422, "Unprocessable", {},  # type: ignore[arg-type]
                                  io.BytesIO(json.dumps(body).encode()))


@pytest.mark.parametrize(("body", "text"), [
    # Two reasons: numbered, each with what to do.
    ({"detail": "a — x\nb", "reasons": [{"reason": "a", "instead": "x"}, {"reason": "b", "instead": ""}]},
     "422: 2 reasons, fix them all before sending again:\n1. a — x\n2. b"),
    # One reason: the detail, as always.
    ({"detail": "a — x", "reasons": [{"reason": "a", "instead": "x"}]}, "422: a — x"),
    # An old server sends no reasons.
    ({"detail": "a — x"}, "422: a — x"),
])
def test_mcp_numbers_two_reasons_and_keeps_one(monkeypatch, body: dict, text: str) -> None:
    def fail(*_a, **_k):
        raise _http_error(body)

    monkeypatch.setattr(mcp._DIRECT, "open", fail)
    with pytest.raises(mcp.ApiError) as exc:
        mcp.Api("http://127.0.0.1:1").post("/api/y", {})
    assert str(exc.value) == text
