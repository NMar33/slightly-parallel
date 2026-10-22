"""Text from a program or a file is read as UTF-8 on every system.

Without ``encoding`` Python takes the locale's (cp1252 on many Windows
machines): a commit subject or a path in Cyrillic raised there.
"""

from __future__ import annotations

import re
from pathlib import Path

CODE = Path(__file__).resolve().parents[1] / "backend"


def _calls(pattern: str) -> list[str]:
    found = []
    for path in sorted(CODE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(pattern, text):
            # The whole call: from the match to its closing parenthesis.
            depth, end = 0, m.start()
            for end in range(m.start(), len(text)):
                depth += {"(": 1, ")": -1}.get(text[end], 0)
                if depth == 0 and text[end] == ")":
                    break
            if "encoding=" not in text[m.start():end]:
                line = text.count("\n", 0, m.start()) + 1
                found.append(f"{path.relative_to(CODE)}:{line}")
    return found


def test_every_program_read_as_text_names_its_encoding() -> None:
    assert _calls(r"subprocess\.(run|Popen|check_output)\((?=(?:[^()]|\([^()]*\))*text=True)") == []


def test_every_file_read_as_text_names_its_encoding() -> None:
    assert _calls(r"(?<!folderwalk)\.(read_text|write_text)\(") == []
