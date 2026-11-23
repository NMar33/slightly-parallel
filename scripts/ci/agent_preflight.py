"""Run bounded provider probes for the L0 test report."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

REQUEST_TIMEOUT_S = 6
MAX_RESPONSE_BYTES = 65536
ANTHROPIC_MODEL = "claude-haiku-5-5"
FAKE_KEY = "sp-ci-invalid-key-control"


def classify(status: int, error: dict) -> str:
    kind = str(error.get("type") or "").lower()
    code = str(error.get("code") or "").lower()
    message = str(error.get("message") or "").lower()
    if status == 401:
        return "L0-auth"
    if {kind, code} & {"insufficient_quota", "billing_hard_limit_reached"} or "credit balance too low" in message:
        return "L0-billing"
    if status == 404 and (code == "model_not_found" or "model" in message):
        return "L0-model"
    if status == 429:
        return "L0-rate"
    return "L0-provider"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _redact(value: object, key: str) -> str:
    text = str(value or "")
    if key:
        text = text.replace(key, "[redacted]")
    return re.sub(r"sk-[\w.*-]+", "[redacted]", text)[:2000]


def probe(key: str, model: str) -> dict:
    request = Request("https://api.anthropic.com/v1/messages", method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json",
    }, data=json.dumps({"model": model, "max_tokens": 1,
                       "messages": [{"role": "user", "content": "ping"}]}).encode())
    try:
        try:
            response = build_opener(NoRedirect()).open(request, timeout=REQUEST_TIMEOUT_S)
        except HTTPError as exc:
            response = exc
        with response:
            status = response.code
            raw = response.read(MAX_RESPONSE_BYTES)
    except OSError as exc:
        # A transport exception can include request details. Log its class only.
        return {"http": None, "type": type(exc).__name__, "message": "No HTTP response", "verdict": "L0-network"}
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        body = {}
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        verdict = classify(status, error)
    elif 200 <= status < 300 and isinstance(body, dict) and body.get("model"):
        return {"http": status, "type": "", "message": "", "verdict": "pass",
                "served_model": _redact(body["model"], key)}
    else:
        verdict, error = "L0-provider", {"type": "invalid_response", "message": "No model response or structured error"}
    return {"http": status, "type": _redact(error.get("type"), key),
            "message": _redact(error.get("message"), key), "verdict": verdict}


def preflight(key: str, model: str) -> dict:
    checks = []
    if key:
        for name, credential, target, verdict, status in (
            ("real request", key, model, "pass", None),
            ("invalid key", FAKE_KEY, model, "L0-auth", 401),
            ("nonexistent model", key, f"sp-preflight-nonexistent-{uuid4().hex}", "L0-model", 404),
        ):
            result = probe(credential, target)
            checks.append({"check": name, **result,
                           "ok": result["verdict"] == verdict and (status is None or result["http"] == status)})
    else:
        checks.append({"check": "configured key", "http": None, "type": "missing_key",
                       "message": "ANTHROPIC_API_KEY is empty", "verdict": "L0-auth", "ok": False})
    return {"provider": "anthropic", "model": _redact(model, key),
            "passed": all(c["ok"] for c in checks), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=ANTHROPIC_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("live probes run only in GitHub Actions")
    result = preflight(os.environ.get("ANTHROPIC_API_KEY", ""), args.model)
    output = json.dumps(result, ensure_ascii=True, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as file:
            file.write(f"### L0 Anthropic\n\n```json\n{output}\n```\n")
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
