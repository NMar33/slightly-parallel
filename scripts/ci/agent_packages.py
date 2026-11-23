"""Print the CLI packages used by the pinned and rolling test runs."""

from __future__ import annotations

import argparse

PACKAGES = {
    "claude-code": ("@anthropic-ai/claude-code", "2.1.330"),
    "codex": ("@openai/codex", "0.170.0"),
    "opencode": ("opencode-ai", "1.19.3"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", choices=("pinned", "latest"))
    parser.add_argument("tools", nargs="*", metavar="tool")
    args = parser.parse_args()
    for tool in args.tools or PACKAGES:
        if tool not in PACKAGES:
            parser.error(f"unknown agent tool: {tool}")
        package, version = PACKAGES[tool]
        print(f"{package}@{version if args.channel == 'pinned' else 'latest'}")


if __name__ == "__main__":
    main()
