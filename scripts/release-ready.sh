#!/usr/bin/env bash
# Before Nick merges a CI branch of the publish folder into main and tags it:
# is the branch pushed as it is here, and did CI pass for exactly that commit?
#
#   scripts/release-ready.sh            # ci-windows
#   scripts/release-ready.sh ci-windows v0.3.3
#
# Green means the last run of each gating workflow for the branch's head
# commit finished with success on its first attempt: CI (ci.yml) and the
# Terminal window (terminal.yml, the real window on three systems). A run for
# an earlier commit, or one that passed only when re-run, does not count. The
# terminal bench (terminal-bench.yml) measures and never gates.
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

# passed WORKFLOW NAME: the last run of WORKFLOW for $sha completed with
# success on its first attempt; otherwise say why and stop. Sets $id.
passed() {
  local workflow=$1 name=$2 run status conclusion attempt
  run=$(gh run list --repo "$repo" --workflow "$workflow" --commit "$sha" --limit 1 \
    --json databaseId,status,conclusion --jq '.[] | "\(.databaseId) \(.status) \(.conclusion)"')
  # (.[] and not .[0]: no run at all prints nothing, where .[0] printed
  # "null null null" and the script said the run was "still null".)
  [[ -n $run ]] || { echo "no $name run for ${sha:0:7}: gh workflow run $workflow --repo $repo --ref $branch" >&2; exit 1; }
  read -r id status conclusion <<<"$run"
  if [[ $status != completed ]]; then
    echo "$name run $id for ${sha:0:7} is still $status" >&2; exit 1
  fi
  if [[ $conclusion != success ]]; then
    echo "$name run $id for ${sha:0:7} ended: $conclusion — see gh run view $id --repo $repo" >&2; exit 1
  fi
  # A run that passed only on a re-run ("Re-run failed jobs") hides a failure:
  # a flaky test or a flaky system. It does not count; push again for a clean run.
  attempt=$(gh api "repos/$repo/actions/runs/$id" --jq .run_attempt)
  if [[ $attempt != 1 ]]; then
    echo "$name run $id for ${sha:0:7} passed on attempt $attempt: a re-run does not count. Find what failed the first attempt (gh run view $id --attempt 1 --repo $repo), fix it, and push again" >&2; exit 1
  fi
}

passed ci.yml CI
ci_id=$id
# The window's suite gates too: on 18 Nov 2026 five of its last six runs were
# red and nothing stopped a merge.
passed terminal.yml "Terminal window"
term_id=$id

echo "$branch ${sha:0:7}: CI run $ci_id and Terminal window run $term_id passed on their first attempt. To release:"
cat <<EOF
cd "$publish"
git checkout master
git merge --ff-only $branch
git tag -a $version -m "Slightly Parallel $version"
git push github master:main
git push github $version
EOF
