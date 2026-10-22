#!/usr/bin/env bash
# check-no-raw-hex.sh — tokens.css is the single source of color truth.
# Any raw #hex outside frontend/src/styles/ is a bug (see tokens.css header).
# Exits 1 and lists offenders when a literal slips into a component.
# Runs in CI.
set -euo pipefail
cd "$(dirname "$0")/.."

# Files that paint with fixed colors on purpose, where a CSS variable cannot
# reach or must not: canvas palettes (the time-lapse film and its themes, the
# tour's pictures), the terminal's own palette (xterm takes literal colors),
# and the brand mark, which looks the same in every theme. A new file joins
# this list only for the same reason.
ALLOW=(
  'frontend/src/features/timelapse/theme.ts'
  'frontend/src/features/timelapse/spmark.ts'
  'frontend/src/features/timelapse/scene.ts'
  'frontend/src/features/terminal/palette.ts'
  'frontend/src/features/tour/scene.ts'
  'frontend/src/features/tour/yard.ts'
  'frontend/src/components/Brand.tsx'
)
allowed=$(printf '%s:\n' "${ALLOW[@]}")

matches=$(grep -rnoE '(^|[^&])#[0-9a-fA-F]{3,8}\b' frontend/src \
  --include='*.ts' --include='*.tsx' --include='*.css' \
  | grep -v 'frontend/src/styles/' \
  | grep -vE '(test|spec)\.' \
  | grep -vF "$allowed" || true)
if [[ -n "$matches" ]]; then
  echo "Raw hex colors outside styles/ — use a token instead:"
  echo "$matches"
  exit 1
fi
echo "no raw hex outside styles/ — clean"
