import io
import json
from pathlib import Path
from runpy import run_path
from urllib.error import HTTPError

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "agent_preflight.py"


@pytest.mark.parametrize(("status", "error", "expected"), [
    (401, {"type": "authentication_error", "message": "invalid x-api-key"}, "L0-auth"),
    (404, {"type": "not_found_error", "message": "model: some-missing-model"}, "L0-model"),
    (400, {"type": "invalid_request_error", "message": "Credit balance too low"}, "L0-billing"),
    (429, {"type": "insufficient_quota", "message": "Current quota exceeded"}, "L0-billing"),
    (429, {"type": "rate_limit_error", "message": "Rate limited"}, "L0-rate"),
    (404, {"type": "not_found_error", "message": "Workspace not found"}, "L0-provider"),
])
def test_preflight_classifies_provider_errors(status, error, expected):
    classify = run_path(str(SCRIPT))["classify"]
    assert classify(status, error) == expected


@pytest.mark.parametrize(("provider", "endpoint", "model", "token_field", "limit", "input_fields"), [
    ("anthropic", "https://api.anthropic.com/v1/messages", "claude-haiku-5-5", "max_tokens", 1,
     {"messages": [{"role": "user", "content": "ping"}]}),
    ("openai", "https://api.openai.com/v1/responses", "gpt-6-luna", "max_output_tokens", 16,
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
