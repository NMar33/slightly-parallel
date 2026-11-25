"""The standalone CI probes distinguish a limits reading from a logged-out RPC."""

from pathlib import Path

import pytest


@pytest.fixture()
def probe(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts" / "ci"))
    import check_codex_limits

    monkeypatch.setattr(check_codex_limits.time, "sleep", lambda _: None)
    monkeypatch.setattr(check_codex_limits, "codex_processes", dict)
    monkeypatch.setattr(check_codex_limits.codexlimits, "detect", lambda: {"exe": "codex", "home": "profile"})
    return check_codex_limits


@pytest.mark.parametrize("cause", ["not signed in", "new error from Codex", "unreadable answer"])
def test_signed_in_limits_probe_does_not_pass_on_an_error(probe, monkeypatch, cause):
    monkeypatch.setattr(probe.codexlimits, "read", lambda: {"ok": False, "cause": cause})
    assert probe.main() == 1


@pytest.mark.parametrize("answer, passed", [
    ({"error": {"code": -32600, "message": "codex account authentication required to read rate limits"}}, True),
    ({"error": {"code": -32600, "message": "some other authentication error"}}, False),
    ({"error": {"code": -32603, "message": "codex account authentication required to read rate limits"}}, False),
    ({}, False),
])
def test_signed_out_probe_requires_the_limits_response_itself(probe, monkeypatch, answer, passed):
    monkeypatch.setattr(probe.codexlimits, "_rpc", lambda *_: {
        1: {"result": {}}, 2: {"result": {"account": None}}, 3: answer,
    })
    assert probe.main(expect_signed_out=True) == (0 if passed else 1)


def test_server_poll_accepts_only_the_specified_result(probe):
    from codex_server_check import poll_answered

    assert poll_answered({"last_success": "2026-11-25T10:00:00"}, expect_signed_out=False)
    assert poll_answered({"cause": "not signed in"}, expect_signed_out=True)
    assert not poll_answered({"cause": "not signed in"}, expect_signed_out=False)
    assert not poll_answered({"cause": "a new error from Codex"}, expect_signed_out=True)
