#!/usr/bin/env bash
# Before Nick merges a CI branch of the publish folder into main and tags it:
# is the branch pushed as it is here, and did CI pass for exactly that commit?
#
#   scripts/release-ready.sh            # ci-windows
#   scripts/release-ready.sh ci-windows v0.3.3
#
# Green means the last run of the CI workflow (ci.yml) for the branch's head
# commit finished with success; a run for an earlier commit does not count.
# On green it prints the merge and tag commands; it runs none of them.
set -euo pipefail
branch=${1:-ci-windows}
version=${2:-vX.Y.Z}
repo=${SP_PUBLISH_REPO:-NMar33/slightly-parallel}
here="$(cd "$(dirname "$0")/.." && pwd)"
publish="${SP_PUBLISH:-$(dirname "$(dirname "$here")")/slightly_parallel}"
[[ -d $publish/.git ]] || { echo "no publish folder at $publish" >&2; exit 1; }
command -v gh >/dev/null || { echo "gh (the GitHub CLI) is needed to read the CI runs" >&2; exit 1; }

cd "$publish"
sha=$(git rev-parse -q --verify "refs/heads/$branch") || { echo "no branch $branch in $publish" >&2; exit 1; }
remote=$(git ls-remote github "refs/heads/$branch" | cut -f1)
[[ $remote == "$sha" ]] || { echo "$branch here is ${sha:0:7}, on GitHub ${remote:0:7}: push it (or pull) first" >&2; exit 1; }

run=$(gh run list --repo "$repo" --workflow ci.yml --commit "$sha" --limit 1 \
  --json databaseId,status,conclusion --jq '.[0] | "\(.databaseId) \(.status) \(.conclusion)"')
[[ -n $run ]] || { echo "no CI run for ${sha:0:7}: gh workflow run ci.yml --repo $repo --ref $branch" >&2; exit 1; }
read -r id status conclusion <<<"$run"
if [[ $status != completed ]]; then
  echo "CI run $id for ${sha:0:7} is still $status" >&2; exit 1
fi
if [[ $conclusion != success ]]; then
  echo "CI run $id for ${sha:0:7} ended: $conclusion — see gh run view $id --repo $repo" >&2; exit 1
fi

echo "$branch ${sha:0:7}: CI run $id passed. To release:"
cat <<EOF
cd "$publish"
git checkout master
git merge --ff-only $branch
git tag -a $version -m "Slightly Parallel $version"
git push github master:main
git push github $version
EOF
