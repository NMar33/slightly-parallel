"""Print the CLI packages used by the pinned and rolling test runs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

NPM_VERSION_TIMEOUT_S = 15
PACKAGES = {
    "claude-code": ("@anthropic-ai/claude-code", "2.1.330"),
    "codex": ("@openai/codex", "0.170.0"),
    "opencode": ("opencode-ai", "1.19.3"),
}


def package_spec(channel: str, tool: str, *, freeze: bool = False) -> str:
    package, pinned = PACKAGES[tool]
    if channel == "pinned":
        return f"{package}@{pinned}"
    spec = f"{package}@latest"
    if not freeze:
        return spec
    result = subprocess.run(["npm", "view", spec, "version", "--json"], capture_output=True, text=True,
                            timeout=NPM_VERSION_TIMEOUT_S, check=True)
    version = json.loads(result.stdout)
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)*", version):
        raise ValueError(f"npm did not return a single version for {package}")
    return f"{package}@{version}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", choices=("pinned", "latest"))
    parser.add_argument("tools", nargs="*", metavar="tool")
    parser.add_argument("--github-output", type=Path, help="freeze every version and expose it to the workflow")
    args = parser.parse_args()
    specs = {}
    for tool in args.tools or PACKAGES:
        if tool not in PACKAGES:
            parser.error(f"unknown agent tool: {tool}")
        specs[tool] = package_spec(args.channel, tool, freeze=args.github_output is not None)
        print(specs[tool])
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            for tool, spec in specs.items():
                output.write(f"{tool}={spec}\n")


if __name__ == "__main__":
    main()
