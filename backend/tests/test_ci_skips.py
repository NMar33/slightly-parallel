"""The CI skip check only accepts known platform limits."""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_skips.py"


@pytest.mark.parametrize("system, expected", [("Windows", 0), ("Linux", 1), ("Darwin", 1)])
def test_the_windows_only_skips_are_reported_by_platform(tmp_path: Path, system: str, expected: int) -> None:
    suite = ET.Element("testsuite")
    for reason in ("no tmux on Windows", "requires Unix sockets", "a bash script, run on Linux and macOS"):
        case = ET.SubElement(suite, "testcase", classname="sample", name=reason)
        ET.SubElement(case, "skipped", message=reason)
    report = tmp_path / "pytest.xml"
    ET.ElementTree(suite).write(report, encoding="utf-8")
    checked = subprocess.run([sys.executable, str(SCRIPT), str(report), system],
                             capture_output=True, encoding="utf-8", timeout=10)
    assert checked.returncode == expected, checked.stdout
