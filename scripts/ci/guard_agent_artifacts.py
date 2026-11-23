"""Stage only credential-checked text from a live agent CI run."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fresh_user"))
from common import contains_diagnostic_key  # noqa: E402


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        yield from value
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _texts(text: str, *, report: bool) -> Iterator[str]:
    yield text
    if report:
        yield from _strings(json.loads(text))
        return
    for line in text.splitlines():
        if line.lstrip().startswith(("{", "[", '"')):
            try:
                yield from _strings(json.loads(line))
            except json.JSONDecodeError:
                pass  # logs are allowed to be plain text, including partial JSON lines


def stage_artifacts(source: Path, destination: Path) -> int:
    if source.is_symlink() or (source / "logs").is_symlink():
        raise ValueError("Unexpected link in upload inputs")
    files = [source] if source.suffix == ".json" else [source / "report.json", *(source / "logs").glob("*.log")]
    root = source.parent if source.suffix == ".json" else source
    checked = {}
    for path in files:
        if path.is_symlink():
            raise ValueError("Unexpected link in upload inputs")
        if not path.exists():
            continue
        raw = path.read_bytes()
        name = path.relative_to(root)
        if (contains_diagnostic_key(name.as_posix())
                or any(contains_diagnostic_key(text) for text in _texts(raw.decode("utf-8"), report=path.suffix == ".json"))):
            raise ValueError("Provider credential or fragment detected")
        checked[name] = raw
    destination.mkdir(parents=True)
    for name, raw in checked.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return len(checked)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        count = stage_artifacts(args.source, args.destination)
    except (OSError, ValueError):
        print("Agent artifact upload blocked: unsafe or unreadable report or log.", file=sys.stderr)
        return 1
    print(f"Audited {count} text artifact file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
