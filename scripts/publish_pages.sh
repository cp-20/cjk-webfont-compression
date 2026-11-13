#!/usr/bin/env bash
# Build from committed HEAD; check/dry-run never fetch from the network or push.
set -euo pipefail
root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
mode=publish
pages_repo=$root
pages_ref=refs/remotes/origin/gh-pages
output=
usage() {
    echo 'Usage: scripts/publish_pages.sh [--check | --dry-run OUTPUT] [--pages-repo LOCAL_REPO] [--pages-ref REF]'
}
while (($#)); do
    case "$1" in
        --check) mode=check; shift ;;
        --dry-run) mode=dry-run; output=${2:?OUTPUT required}; shift 2 ;;
        --pages-repo) pages_repo=${2:?LOCAL_REPO required}; shift 2 ;;
        --pages-ref) pages_ref=${2:?REF required}; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done
# Restrict comparison inputs to local repositories, including in offline tests.
[[ -d "$pages_repo" ]] || { echo 'pages repository must be a local directory' >&2; exit 2; }
source_commit=$(git -C "$root" rev-parse HEAD)
pages_commit=$(git -C "$pages_repo" rev-parse "$pages_ref^{commit}")
remote=$(git -C "$root" remote get-url --push origin)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/source" "$tmp/site" "$tmp/live"
git -C "$root" archive "$source_commit" | tar -x -C "$tmp/source"
python3 "$tmp/source/report/content.py"
python3 "$tmp/source/report/glc_content.py"
python3 "$tmp/source/report/build_demo.py"
cp -R "$tmp/source/report" "$tmp/site/report"
# Imports create caches, which are not published assets.
find "$tmp/site" -type d -name __pycache__ -prune -exec rm -rf {} +
cp "$tmp/source/scripts/pages-index.html" "$tmp/site/index.html"
touch "$tmp/site/.nojekyll"
if [[ "$mode" == dry-run ]]; then
    [[ ! -e "$output" ]] || { echo 'OUTPUT must not exist' >&2; exit 2; }
    cp -R "$tmp/site" "$output"
    echo "Dry-run tree: $output (source $source_commit)"
    exit 0
fi
git -C "$pages_repo" archive "$pages_commit" | tar -x -C "$tmp/live"
if [[ "$mode" == check ]]; then
    diff -rq "$tmp/live" "$tmp/site"
    echo "Pages match $pages_commit (source $source_commit); no push."
    exit 0
fi
# Fetch the known local parent; a normal push rejects remote advancement.
git -C "$tmp/site" init -q
git -C "$tmp/site" fetch -q "$pages_repo" "$pages_ref"
git -C "$tmp/site" reset --soft FETCH_HEAD
git -C "$tmp/site" add -A
if git -C "$tmp/site" diff --cached --quiet; then
    echo 'Pages already match; no push.'
    exit 0
fi
git -C "$tmp/site" -c user.name="$(git -C "$root" var GIT_AUTHOR_IDENT | sed 's/ <.*//')" \
    -c user.email="$(git -C "$root" var GIT_AUTHOR_IDENT | sed 's/.*<\(.*\)>.*/\1/')" \
    commit -m "Publish report and demo from $source_commit"
git -C "$tmp/site" push "$remote" HEAD:refs/heads/gh-pages
