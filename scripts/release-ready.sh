#!/usr/bin/env bash
# Before Nick merges a CI branch of the publish folder into main and tags it:
# is the branch pushed as it is here, and did CI pass for exactly that commit?
#
#   scripts/release-ready.sh            # ci-windows
#   scripts/release-ready.sh ci-windows v0.3.3
#
# Green means the last run of each gating workflow for the branch's head
# commit finished with success on its first attempt: CI, Terminal window,
# Weekly, Agents and full Machine, with their required jobs and steps. A run for
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
command -v python3 >/dev/null || { echo "python3 is needed to verify the completed jobs" >&2; exit 1; }

cd "$publish"
sha=$(git rev-parse -q --verify "refs/heads/$branch") || { echo "no branch $branch in $publish" >&2; exit 1; }
remote=$(git ls-remote github "refs/heads/$branch" | cut -f1)
[[ $remote == "$sha" ]] || { echo "$branch here is ${sha:0:7}, on GitHub ${remote:0:7}: push it (or pull) first" >&2; exit 1; }

# passed WORKFLOW NAME: the last run of WORKFLOW for $sha completed with
# success on its first attempt; otherwise say why and stop. Sets $id.
passed() {
  local workflow=$1 name=$2 extra=${3:-} run status conclusion attempt
  run=$(gh run list --repo "$repo" --workflow "$workflow" --branch "$branch" --commit "$sha" --limit 1 \
    --json databaseId,status,conclusion --jq '.[] | "\(.databaseId) \(.status) \(.conclusion)"')
  # (.[] and not .[0]: no run at all prints nothing, where .[0] printed
  # "null null null" and the script said the run was "still null".)
  [[ -n $run ]] || { echo "no $name run for ${sha:0:7}: gh workflow run $workflow --repo $repo --ref $branch$extra" >&2; exit 1; }
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

workflows=(ci.yml terminal.yml weekly.yml agents.yml machine.yml)
labels=(CI 'Terminal window' Weekly Agents 'Machine full')
ids=()
for i in "${!workflows[@]}"; do
  extra=""
  [[ ${workflows[i]} != machine.yml ]] || extra=" -f full=true"
  passed "${workflows[i]}" "${labels[i]}" "$extra"
  ids+=("$id")
done
for i in "${!workflows[@]}"; do
  if ! gh api "repos/$repo/actions/runs/${ids[i]}/attempts/1/jobs?per_page=100" \
    | python3 "$here/scripts/ci/release_jobs.py" "${workflows[i]}" "$sha"; then
    echo "${labels[i]} run ${ids[i]} for ${sha:0:7} did not prove the required checks" >&2
    exit 1
  fi
  echo "${labels[i]} run ${ids[i]} passed the required checks on the first attempt."
done

echo "$branch ${sha:0:7}: ready to release."
cat <<EOF
cd "$publish"
git checkout master
git merge --ff-only $branch
git tag -a $version -m "Slightly Parallel $version"
git push github master:main
git push github $version
EOF
