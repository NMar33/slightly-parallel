"""Fail a green pytest run whose skips are not the ones expected on this system.

A skip hides code that was never tested (docs/testing.md case 2: 17 tests
skipped on Windows found a bug the day they ran). A pytest run writes
--junitxml; this reads every skipped test's reason and fails on one that is
not in ALLOWED for this system, naming it. Each allowed reason says why the
test cannot run here, and where it does run.

    python ../scripts/ci/check_skips.py pytest.xml
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET

LINUX, MAC, WIN = "Linux", "Darwin", "Windows"
ALL = {LINUX, MAC, WIN}

# (reason pattern, systems where it may skip): runs on the others.
ALLOWED: list[tuple[str, set[str]]] = [
    (r"the terminal needs macOS or Linux", {WIN}),
    (r"tmux is not (installed|on this machine)", {WIN}),
    (r"Windows refuses to replace a file the archiver holds open", {WIN}),
    (r"needs a file its owner cannot read|read-only by permissions|permissions do not stop this user|root reads every file", {WIN}),
    (r"Linux entries are written on Linux", {WIN}),
    (r"reads /proc|Linux /proc", {MAC, WIN}),
    (r"sp\.sh is the POSIX launcher", {WIN}),
    (r"Windows reads the process table from the kernel", {WIN}),
    (r"POSIX lines", {WIN}),
    (r"fcntl\.flock is POSIX only", {WIN}),
    (r"Windows: a process('s)? (cannot set its( own)? time zone|time zone cannot be set)", {WIN}),
    (r"a file held open without sharing exists on Windows only", {LINUX, MAC}),
    (r"drive letters are a Windows spelling", {LINUX, MAC}),
    (r"restore needs tarfile's data filter", ALL),
    (r"the real CLI runs in its own CI job", ALL),   # tests/test_real_cli.py, job real-cli   # Python before 3.12
    (r"the real Codex runs in its own CI job", ALL),   # tests/test_real_codex.py, job real-cli
]


def system() -> str:
    import platform
    return platform.system()


def skipped(path: str) -> list[tuple[str, str]]:
    out = []
    for case in ET.parse(path).getroot().iter("testcase"):
        for sk in case.findall("skipped"):
            if sk.get("type") == "pytest.xfail":
                continue
            name = f"{case.get('classname')}::{case.get('name')}"
            out.append((name, (sk.get("message") or "") + " " + (sk.text or "")))
    return out


def main(argv: list[str]) -> int:
    here = argv[2] if len(argv) > 2 else system()
    found = skipped(argv[1])
    unexpected = [(n, why) for n, why in found
                  if not any(re.search(p, why) and here in where for p, where in ALLOWED)]
    print(f"{len(found)} skipped on {here}; {len(unexpected)} not expected here")
    for n, why in unexpected:
        print(f"  {n}: {why.strip()[:200]}")
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
