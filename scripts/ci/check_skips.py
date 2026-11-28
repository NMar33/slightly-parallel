"""Fail a green pytest run whose skips are not the ones expected on this system.

A skip hides code that was never tested (docs/testing.md case 2: 17 tests
skipped on Windows found a bug the day they ran). A pytest run writes
--junitxml; this reads every skipped test's reason and fails on one that is
not in ALLOWED for this system, naming it. Each allowed reason says why the
test cannot run here, and where it does run.

    python ../scripts/ci/check_skips.py pytest.xml
    python ../scripts/ci/check_skips.py pytest.xml --one-passed
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET

LINUX, MAC, WIN = "Linux", "Darwin", "Windows"
ALL = {LINUX, MAC, WIN}

# (reason pattern, systems where it may skip): runs on the others.
ALLOWED: list[tuple[str, set[str]]] = [
    (r"a Unix pty|Unix PTY process groups", {WIN}),  # Windows coverage: tests/test_conpty.py and test_agent_screen.py
    (r"ConPTY is Windows only", {LINUX, MAC}),
    (r"a symlink needs privileges on Windows", {WIN}),
    (r"tmux is not (installed|on this machine)|no tmux on Windows", {WIN}),
    (r"requires Unix sockets", {WIN}),           # direct Codex delivery uses a Unix socket
    (r"a bash script, run on Linux and macOS", {WIN}),  # the operator's release script
    (r"Windows refuses to replace a file the archiver holds open", {WIN}),
    (r"needs a file its owner cannot read|read-only by permissions|permissions do not stop this user|root reads every file", {WIN}),
    (r"Linux entries are written on Linux", {WIN}),
    (r"reads /proc|Linux /proc", {MAC, WIN}),
    (r"sp\.sh is the POSIX launcher", {WIN}),
    (r"Windows reads the process table from the kernel", {WIN}),
    (r"POSIX lines|requires POSIX directory descriptors", {WIN}),
    (r"fcntl\.flock is POSIX only", {WIN}),
    (r"Windows: a process('s)? (cannot set its( own)? time zone|time zone cannot be set)", {WIN}),
    (r"a file held open without sharing exists on Windows only", {LINUX, MAC}),
    (r"drive letters are a Windows spelling", {LINUX, MAC}),
    (r"restore needs tarfile's data filter", ALL),
    (r"the real CLI runs in its own CI job", ALL),   # tests/test_real_cli.py, job real-cli   # Python before 3.12
    (r"the real Codex runs in its own CI job", ALL),   # tests/test_real_codex.py, job real-cli
    (r"the pinned interactive CLI CI job owns this check", ALL),  # test_interactive_agents.py
    # Probes of the real stores in this user's home (test_injected_prompts.py,
    # test_queued_messages.py): they read the newest transcript the installed
    # Claude Code, Codex or OpenCode wrote, to catch a format change the
    # fixture tests cannot. A CI runner has no such history; they run on the
    # developer's machine, where the tools are used every day.
    (r"no (Claude Code transcript|Codex rollout|OpenCode store) on this machine", ALL),
    # Two real Codex TUIs in tmux against one app-server (test_codex_message_tui.py):
    # the Backend jobs install no Codex, and Windows has neither tmux nor the
    # Unix socket. It runs on the developer's machine with Codex installed.
    (r"requires Codex with Unix app-server and tmux", ALL),
]


def system() -> str:
    import platform
    return platform.system()


def skipped(cases: list[ET.Element]) -> list[tuple[str, str]]:
    out = []
    for case in cases:
        for sk in case.findall("skipped"):
            if sk.get("type") == "pytest.xfail":
                continue
            name = f"{case.get('classname')}::{case.get('name')}"
            out.append((name, (sk.get("message") or "") + " " + (sk.text or "")))
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("system", nargs="?", default=system())
    count = parser.add_mutually_exclusive_group()
    count.add_argument("--minimum", type=int, default=1)
    count.add_argument("--one-passed", action="store_true")
    args = parser.parse_args(argv[1:])
    if args.minimum < 1:
        parser.error("--minimum must be at least one")
    report = ET.parse(args.report).getroot()
    cases = list(report.iter("testcase"))
    failed = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    passed = sum(all(case.find(tag) is None for tag in ("skipped", "failure", "error")) for case in cases)
    if failed or passed < args.minimum or (args.one_passed and len(cases) != 1):
        expected = "exactly one passed test" if args.one_passed else f"at least {args.minimum} passed tests"
        print(f"Expected {expected} and no failures. Found {passed} passes, {failed} failures in {len(cases)} cases.", file=sys.stderr)
        return 1
    here = args.system
    found = skipped(cases)
    unexpected = [(n, why) for n, why in found
                  if not any(re.search(p, why) and here in where for p, where in ALLOWED)]
    print(f"{passed} passed, {len(found)} skipped on {here}; {len(unexpected)} not expected here")
    for n, why in unexpected:
        print(f"  {n}: {why.strip()[:200]}")
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
