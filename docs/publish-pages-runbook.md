# Publishing GitHub Pages

Requirements: Bash, Git, Python 3, tar, diff, and cp. No Python packages are
needed for HTML generation or the offline integration tests.

Work from current main on a branch. If font binaries are absent, first run
`python3 scripts/fetch_assets.py --fonts`; it verifies downloads against
`fonts/manifest.json`. Stop and investigate any verification failure rather
than accepting a changed upstream file.

Regenerate the HTML from the recorded measurements and existing demo assets:

```sh
python3 report/content.py
python3 report/glc_content.py
python3 report/build_demo.py
```

These commands do not remeasure or rebuild fonts. To intentionally rebuild
font assets, use `measure/build_demo_assets.py` with the measurement environment
and verified fonts first; follow README.md and the round-5 notes. Font rebuilds
can have byte jitter. Review generated changes, then commit them. The publisher
builds from **committed HEAD**, in a temporary source snapshot, so uncommitted
report changes are not published. It regenerates the three HTML files and
copies the full tracked `report/` tree (including demo fonts and reproduction
sources), excluding Python caches. `scripts/pages-index.html` supplies the
landing page; an empty `.nojekyll` disables Jekyll.

Fetch explicitly before an offline check, to identify the live branch snapshot:

```sh
git fetch origin gh-pages:refs/remotes/origin/gh-pages
python3 -m unittest discover -s tests -v
scripts/publish_pages.sh --check
scripts/publish_pages.sh --dry-run /tmp/pages-preview
```

The dry-run output path must not exist. Inspect that directory before publishing.
`--check` compares every path and file's bytes against the fetched
`origin/gh-pages` commit, reports differing/missing/extra files, and returns 1
on drift, 0 on equality. It performs no network calls, commits, or pushes and
does not modify either checkout. It compares content, not file modes or Git
history. A check is only as current as the explicit fetch above.
For another local clone, append `--pages-repo /path/to/clone --pages-ref HEAD`.
The integration test creates such a clone from a dry-run tree and verifies both
equality and an extra-file mismatch without changing either repository's refs.

Only after reviewing all differences and authorizing publication, run:

```sh
scripts/publish_pages.sh
```

The default mode creates a temporary Git repository, parents a new commit on
the selected local gh-pages snapshot, and uses a normal (never force) push to
origin's `gh-pages`. Remote advancement rejects the push; fetch, check, and
review again. An identical tree produces no commit or push. It never checks
out or resets the source worktree. Do not point publish mode at an unrelated
comparison repository. Git author identity must already be configured.

## Verified reconstruction result (2026-11-13)

Against main `c87f569` and fetched gh-pages `b40afeb`, `--check` returns 1:
only `report/glc.html` differs. The generator omits six embedded PNG figures
(grids 0/2/4/8/16/32) because `glc_demo.json` references PNG assets absent from
the committed report/assets tree. The live HTML still embeds those figures.
All other published files match. Do not publish this loss without resolving
and reviewing it. The passing local-clone test is a generated-tree fixture,
not a claim that the live snapshot matches. No gh-pages publication was done.
