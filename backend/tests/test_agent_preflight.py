import io
import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "agent_preflight.py"


@pytest.mark.parametrize(("status", "error", "expected"), [
    (401, {"type": "authentication_error", "message": "invalid x-api-key"}, "L0-auth"),
    (404, {"type": "not_found_error", "message": "model: some-missing-model"}, "L0-model"),
    (400, {"type": "invalid_request_error", "message": "Credit balance too low"}, "L0-billing"),
    (402, {"type": "invalid_request_error", "message": "Payment Required"}, "L0-billing"),
    (400, {"type": "invalid_request_error", "message": "Missing messages"}, "L0-provider"),
    (429, {"type": "insufficient_quota", "message": "Current quota exceeded"}, "L0-billing"),
    (429, {"message": "Quota exceeded. Check your plan and billing details."}, "L0-billing"),
    (429, {"message": "You exceeded your current quota, please check your plan and billing details."}, "L0-billing"),
    (429, {"type": "rate_limit_error", "message": "Rate limited"}, "L0-rate"),
    (404, {"type": "not_found_error", "message": "Workspace not found"}, "L0-provider"),
])
def test_preflight_classifies_provider_errors(status, error, expected):
    classify = run_path(str(SCRIPT))["classify"]
    assert classify(status, error) == expected


@pytest.mark.parametrize(("provider", "endpoint", "model", "token_field", "limit", "input_fields"), [
    ("anthropic", "https://api.anthropic.com/v1/messages", "claude-haiku-5-5", "max_tokens", 1,
     {"messages": [{"role": "user", "content": "ping"}]}),
    ("openai-codex", "https://api.openai.com/v1/responses", "gpt-6-luna", "max_output_tokens", 16,
     {"input": "ping", "store": False}),
    ("openai-opencode", "https://api.openai.com/v1/responses", "gpt-6-luna", "max_output_tokens", 16,
     {"input": "ping", "store": False}),
])
def test_preflight_uses_only_the_authorized_requests(monkeypatch, provider, endpoint, model, token_field, limit,
                                                    input_fields):
    preflight = run_path(str(SCRIPT))["preflight"]
    calls = []
    key = "sensitive-ci-credential"

    class Opener:
        def open(self, request, *, timeout):
            assert request.full_url == endpoint
            assert request.get_method() == "POST"
            assert 0 < timeout <= 6
            assert request.get_header("Originator") == ("codex-tui" if provider == "openai-codex" else None)
            body = json.loads(request.data)
            assert body == {"model": body["model"], token_field: limit, **input_fields}
            if provider == "anthropic":
                assert request.get_header("Authorization") is None
                credential = request.get_header("X-api-key")
            else:
                assert request.get_header("X-api-key") is None
                auth = request.get_header("Authorization")
                assert auth.startswith("Bearer ")
                credential = auth.removeprefix("Bearer ")
            calls.append((credential, body["model"]))
            if credential != key:
                status, result = 401, {"error": {"type": "authentication_error", "message": "invalid key"}}
            elif body["model"] != model:
                status, result = 404, {"error": {"type": "not_found_error", "message": "model not found"}}
            else:
                status, result = 200, {"model": model}
            response = io.BytesIO(json.dumps(result).encode())
            if status != 200:
                raise HTTPError(request.full_url, status, "", {}, response)
            response.code = status
            return response

    def build_opener(handler):
        assert handler.redirect_request(None, None, 307, "", {}, "https://elsewhere.invalid/") is None
        return Opener()

    monkeypatch.setitem(preflight.__globals__, "build_opener", build_opener)
    report = preflight(key, model, provider=provider)
    assert report["passed"]
    assert report["provider"] == provider
    assert report["checks"][0]["check"] == ("Codex eligibility" if provider == "openai-codex" else "real request")
    assert [check["http"] for check in report["checks"]] == [200, 401, 404]
    assert calls[:2] == [(key, model), ("sp-ci-invalid-key-control", model)]
    assert calls[2][0] == key
    assert calls[2][1].startswith("sp-preflight-nonexistent-")
    assert key not in json.dumps(report)


def test_anthropic_preflight_redacts_key_in_error_type_and_message(monkeypatch):
    probe = run_path(str(SCRIPT))["probe"]
    key = "sensitive-ci-credential"

    class Opener:
        def open(self, request, *, timeout):
            error = {"error": {"type": key, "message": f"Credit balance too low for {key}"}}
            raise HTTPError(request.full_url, 400, "", {}, io.BytesIO(json.dumps(error).encode()))

    monkeypatch.setitem(probe.__globals__, "build_opener", lambda *_: Opener())
    assert probe(key, "claude-haiku-5-5", provider="anthropic") == {
        "http": 400, "type": "[redacted]", "message": "Credit balance too low for [redacted]", "verdict": "L0-billing",
    }


def test_anthropic_credit_error_uses_the_api_envelope(monkeypatch):
    probe = run_path(str(SCRIPT))["probe"]
    message = ("Your credit balance is too low to access the Anthropic API. "
               "Please go to Plans & Billing to upgrade or purchase credits.")
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": message},
            "request_id": "req_fixture"}

    class Opener:
        def open(self, request, *, timeout):
            raise HTTPError(request.full_url, 400, "", {}, io.BytesIO(json.dumps(body).encode()))

    monkeypatch.setitem(probe.__globals__, "build_opener", lambda *_: Opener())
    assert probe("dummy-ci-key", "claude-haiku-5-5", provider="anthropic") == {
        "http": 400, "type": "invalid_request_error", "message": message, "verdict": "L0-billing",
    }


@pytest.mark.parametrize("key_display", ["sk-ant-api03-… TAIL5678", "sk-ant-*** abcd",
                                        "SK-ANT-\x1b[31m…\x1b[0m\n  TAIL5678",
                                        "sk-ant-api03-… TAIL\n5678", "sk-ant-api03-… TAIL567\n8",
                                        "sk-ant-api03-\n… TAIL5678", "sk-ant-api0\n3-… TAIL5678"])
def test_api_and_pty_reports_hide_masked_keys_without_the_environment_key(monkeypatch, key_display):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.syspath_prepend(str(SCRIPT.parents[1] / "fresh_user"))
    from common import redact_diagnostics

    redact_api = run_path(str(SCRIPT))["_redact"]
    text = f"API key {key_display}\nLogin required"
    expected = "API key [redacted]\nLogin required"
    assert redact_diagnostics(text) == expected
    assert redact_api(text, "") == expected


@pytest.mark.parametrize("frame", ["Your credit balance is\ntoo low to access the Anthropic API.",
                                  "Quota exceeded. Check your plan and billing details.",
                                  "You exceeded your current quota, please check your plan and billing details.",
                                  "billing_hard_limit_reached", "HTTP 402: Payment Required"])
def test_pty_wait_reports_the_api_credit_error_without_waiting_for_timeout(monkeypatch, frame) -> None:
    monkeypatch.syspath_prepend(str(SCRIPT.parents[1] / "fresh_user"))
    import interactive

    captured = []
    screen = SimpleNamespace(text="", rendered=frame, read=lambda: None, save_frame=captured.append)
    monkeypatch.setattr(interactive.time, "sleep", lambda _: pytest.fail("billing failure should return immediately"))
    verdict = "L4 provider error (L0-billing)"
    assert interactive._wait_for_turn(screen, lambda: False, 30) == verdict
    assert captured == [verdict]
    assert interactive._turn_failure_class(verdict) == "outside (billing)"


def test_codex_paid_machine_eligibility_error_fails_fast(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parents[1] / "fresh_user"))
    import interactive

    path = Path(__file__).with_name("fixtures") / "terminal-approvals" / "paid-machine-codex-eligibility.json"
    response = json.loads(path.read_text(encoding="utf-8"))
    saved = []
    screen = SimpleNamespace(text="", rendered="■ " + json.dumps(response), read=lambda: None, save_frame=saved.append)
    monkeypatch.setattr(interactive.time, "sleep", lambda _: pytest.fail("eligibility should fail before timeout"))
    verdict = interactive._wait_for_turn(screen, lambda: False, 30)
    assert saved == [verdict]
    assert interactive._turn_failure_class(verdict) == "outside (billing/eligibility)"
    assert run_path(str(SCRIPT))["classify"](response["status"], response["error"]) == "L0-eligibility"


def test_redaction_preserves_json_delimiters(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parents[1] / "fresh_user"))
    from common import redact_diagnostics

    payload = '{"error":"sk-proj-fakeVisibleKey-0987654321","status":401}'
    assert json.loads(redact_diagnostics(payload)) == {"error": "[redacted]", "status": 401}


def test_preflight_writes_only_to_the_file_until_the_audit(monkeypatch, tmp_path, capsys):
    run = run_path(str(SCRIPT))["main"]
    output, summary = tmp_path / "report.json", tmp_path / "summary"
    private = {"provider": "anthropic", "passed": False, "checks": [{"message": "provider evidence"}]}
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--provider", "anthropic", "--output", str(output)])
    monkeypatch.setitem(run.__globals__, "preflight", lambda *_, **__: private)
    assert run() == 1
    assert json.loads(output.read_text(encoding="utf-8")) == private
    assert "provider evidence" not in capsys.readouterr().out and not summary.exists()


@pytest.mark.parametrize(("provider", "secret"), [
    ("openai-codex", "CODEX_OPENAI_API_KEY"),
    ("openai-opencode", "OPENAI_API_KEY"),
])
def test_l0_selects_only_the_named_openai_key(monkeypatch, tmp_path, provider, secret):
    run = run_path(str(SCRIPT))["main"]
    output = tmp_path / "report.json"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CODEX_OPENAI_API_KEY", "codex-fixture-only")
    monkeypatch.setenv("OPENAI_API_KEY", "opencode-fixture-only")
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--provider", provider, "--output", str(output)])
    expected = {"CODEX_OPENAI_API_KEY": "codex-fixture-only", "OPENAI_API_KEY": "opencode-fixture-only"}[secret]
    original = run.__globals__["preflight"]

    def check(key, model, *, provider):
        assert key == expected
        return {"passed": True}

    monkeypatch.setitem(run.__globals__, "preflight", check)
    assert run() == 0
    monkeypatch.delenv(secret)
    monkeypatch.setitem(run.__globals__, "preflight", original)
    assert run() == 1
    report = json.loads(output.read_bytes())
    assert report["checks"][0]["message"] == f"secret {secret} is not set"
    assert report["credential"] == f"openai/{provider.split('-')[1]} key"



def test_codex_l0_retains_the_eligibility_refusal_and_redacts_both_keys(monkeypatch):
    run = run_path(str(SCRIPT))
    preflight = run["preflight"]
    response_path = Path(__file__).with_name("fixtures") / "terminal-approvals" / "paid-machine-codex-eligibility.json"
    envelope = json.loads(response_path.read_bytes())
    codex_key = "codex-private-extra-fixture-value"
    opencode_key = "opencode-private-extra-fixture-value"
    monkeypatch.setenv("CODEX_OPENAI_API_KEY", codex_key)
    monkeypatch.setenv("OPENAI_API_KEY", opencode_key)

    class EligibilityOpener:
        def open(self, request, *, timeout):
            assert request.get_header("Originator") == "codex-tui"
            error = {**envelope["error"], "message": envelope["error"]["message"] + f" {codex_key} {opencode_key}"}
            response = io.BytesIO(json.dumps({"error": error}).encode())
            raise HTTPError(request.full_url, envelope["status"], "", {}, response)

    monkeypatch.setitem(preflight.__globals__, "build_opener", lambda *_: EligibilityOpener())
    report = preflight(codex_key, "gpt-6-luna", provider="openai-codex")
    assert not report["passed"]
    assert report["checks"][0]["verdict"] == "L0-eligibility"
    assert report["checks"][0]["message"].endswith("[redacted] [redacted]")
    assert codex_key not in json.dumps(report)
    assert opencode_key not in json.dumps(report)
