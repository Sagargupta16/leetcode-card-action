# CLAUDE.md

> This file stacks on top of the workspace root at `C:\Code\GitHub\`:
> - Root [`CLAUDE.md`](../../CLAUDE.md) -- voice, rules, routing map, references, skills, slash commands, conventions.
> - Root [`MEMORY.md`](../../MEMORY.md) -- live facts across repos.
> - Root [`STATUS.md`](../../STATUS.md) -- live PR/CI/security dashboard.
> - [`.claude/resources/`](../../.claude/resources/README.md) -- deep reference for collaboration, workflow, git, OSS, debugging, voice.
>
> Read those first. The guidance below only adds **repo-specific context** -- it does not override anything in the root.

## Project

Composite GitHub Action that renders a self-hosted animated LeetCode card (contest rating history chart with the peak marked, badge, rating, top percentage, contests, solved count, Easy/Medium/Hard bars, and an optional past-year submission heatmap) into the caller's repo as an SVG, `assets/leetcode.svg` by default, in one of six themes. One run can write several cards (a light and dark pair) from one fetch.

Extracted from `render_leetcode` in `brand/Sagargupta16/scripts/render-svgs.py` so anyone can use it as `Sagargupta16/leetcode-card-action@v1`. Built 2026-09-25, released as v1.0.0 that day and listed on the Marketplace as "LeetCode Card".

## Stack

- **Language**: Python 3.13 (what `action.yml` installs), stdlib only; CI tests 3.12, 3.13 and 3.14
- **Framework**: GitHub Actions composite action (`action.yml`)
- **Database**: none
- **Package manager**: none at runtime; `uv`/`uvx` for local lint and tests
- **Deploy target**: consumed via `uses:` in other repos' workflows; releases are git tags

## Run

```
LEETCODE_USERNAME=sagargupta1610 LEETCODE_OUTPUT=examples/leetcode.svg python leetcode_card.py
```

Without `LEETCODE_OUTPUT` it writes `assets/leetcode.svg`, which is gitignored. `python scripts/render_examples.py` regenerates every README preview (`examples/leetcode.svg` and `examples/themes/<theme>.svg`, the latter with the heatmap) from one live fetch and prints the numbers for the alt text.

## Test

```
uvx ruff@0.17.1 check .
uv run --no-project --with pytest==9.1.1 pytest -v
```

`test_leetcode_card.py` never touches the network: tests that reach `fetch` monkeypatch it with canned GraphQL bytes shaped like the live responses. It covers the chart path math, peak detection and label placement, every card state, XML validity through `xml.dom.minidom`, escaping, WCAG contrast of every color for every theme crossed with several accents, the heatmap window, levels and layout, response parsing, multi-line outputs, the step outputs and the fallback.

`.github/workflows/ci.yml` has three jobs on every push to `main` and every PR: `lint` (ruff, 3.13), `test` (pytest, 3.12/3.13/3.14) and `action`, the only job that loads `action.yml`. It runs the action from the checkout against the live profile `sagargupta1610`, parses the SVG and fails if any output is empty, then runs it again with `heatmap: true` and a `github-dark`/`github-light` output pair and checks both backgrounds and the heatmap label. Because `action` calls the real API, a LeetCode outage turns it red while lint and test stay green.

`ruff==0.17.1` and `pytest==9.1.1` are pinned inline in `ci.yml`: Renovate does not read `run:` text, and ruff 0.16.0 grew its default ruleset from 59 rules to 413. Bump them by hand, after `uvx ruff@<new> check .` passes locally (0.17.1 passed with no changes on 2026-10-18). There is deliberately no `ruff.toml`, so the full default set applies (it flagged ISC004 and FURB122 on the first draft).

## Entry points

- `action.yml` -- the contract: inputs, outputs, Python 3.13 setup, inputs mapped to `LEETCODE_*` env vars
- `leetcode_card.py` -- the whole action: fetch, parse, render, write, `$GITHUB_OUTPUT`

## Key files

- `leetcode_card.py` -- `THEMES`, `fetch` (allowlist), `parse_profile`, `palette` (every color for a theme, contrast-raised), `chart_points`, `render_chart`, `render_headline`, `render_solved`, `activity` and `render_heatmap`, `render_card`, `parse_outputs`, `main` (fallback)
- `examples/leetcode.svg` -- live data for sagargupta1610, rendered 2026-10-18; the README preview
- `examples/themes/*.svg` -- one card per theme with the heatmap, same data and date; the README Themes gallery
- `scripts/render_examples.py` -- regenerates all of `examples/`

## Gotchas

- Themes: a theme is `bg`, `ink` (RGB for muted labels, gridlines and tracks at partial alpha), `text` and `accent` in `THEMES`. `palette()` derives everything else: accent and difficulty colors go through `readable(color, bg)`, which lightens on dark backgrounds and darkens on light ones; muted labels go through `muted()`, which raises alpha in 0.01 steps until 4.5:1; heatmap shades come from `heat_colors()`, the faintest at the lowest alpha over `bg` that reaches 3:1. `dark` with its default accent reproduces the 1.0 colors exactly, so the default card only changed by the ring delay in 1.1.0 (diffed against origin/main for three accents and three states, 2026-10-18).
- Heatmap: `userCalendar{submissionCalendar}` is only added to the query when `heatmap` is on. It is a JSON string keyed by UTC-midnight timestamps; on 2026-10-18 it held the past year for sagargupta1610 (97 active days, 212 submissions, max streak 25, matching LeetCode's own `totalActiveDays` and `streak`). The window is 53 week columns, Sunday on top, ending today in UTC, so a heatmap card changes every day. The empty grid is two pattern-filled rects; only active days are `<rect>`s.
- The peak ring's CSS pulse has `animation-delay:2.6s`. A CSS animation outranks the SMIL-animated `opacity` attribute, so without the delay the ring pulsed from t=0 (measured 0.78 opacity at 0.2s in Chrome before the fix, 0 until 2.6s after).
- `output` is split into lines by `parse_outputs`; `?theme=<name>` is the only option. On a failed fetch the run warns and exits 0 only if every output exists.
- Adding an input touches three places: `inputs` in `action.yml`, the step's `env` block, and the `os.environ` read in `main()`.
- Composite outputs need `value: ${{ steps.card.outputs.<name> }}` and the `id: card` on the step that writes `$GITHUB_OUTPUT`. Without the mapping every output silently resolves to an empty string (credly-badge-readme-action shipped exactly that bug).
- The default title lives in `action.yml` and in `DEFAULT_TITLE`; keep them identical. `{contests}` is swapped with `str.replace`, not `str.format`, so titles with other braces render as typed instead of crashing.
- SVG collapses runs of spaces: the brand renderer's `"  |  "` and the default title's `" | "` measure the same (254.53 px in Chrome, 2026-09-25).
- The chart card matched the brand renderer byte for byte in 1.0.0 apart from the aria-label, which names the user (diffed against `brand/Sagargupta16/assets/svg/leetcode.svg` on 2026-09-25). Since then the profile renders that file with this action (pinned by SHA in its `render-svgs.yml`), so a card change reaches it only when the pin moves.
- Contrast is a gate: every text color reaches 4.5:1 on `BG` (`MIN_CONTRAST`), large text included, and the rating line, markers and difficulty bars reach 3:1. The tests check both for several accents. Muted labels sit at the lowest alpha that passes (axis labels `rgba(255,255,255,0.45)` at 4.53:1; 0.44 is 4.38:1). `render_card` runs the accent through `readable()`, which keeps a passing accent exactly as typed and otherwise raises its HLS lightness in 0.001 steps until it passes. A 4.5:1 accent also clears 3:1 against its own 0.28 area tint (worst 3.21:1 over 140,608 colors swept on 2026-10-11). Check a card change with svg-forge's `validate_svg.py --strict-contrast`.
- A chart needs two rated contests. With zero or one, the card drops the chart and shrinks from 270 to 188 px: headline on the left, solved panel at the same `x=600`.
- The `PEAK` label flips to the right of the point when it would run off the left edge (a user whose first contest was the peak). The brand card never hit this because its peak is the latest contest.
- LeetCode GraphQL shapes, measured live 2026-09-25: a missing user returns `matchedUser: null` with the error "That user does not exist."; a user with no contests returns `userContestRanking: null` and an empty history; a user without a badge returns `badge: null`.
- Every fetch failure (network, HTTP, bad JSON, missing user, changed shape) goes through `FETCH_ERRORS` into one fallback: keep the existing file and exit 0 with `::warning::`, or exit 1 with `::error::` when there is no file yet. Outputs are only written on success.
- Any non-empty `errors` in a response for an existing user also counts as a failure. GraphQL can answer with partial data, and a nulled `userContestRanking` would otherwise redraw a good card as "No contests yet". Measured 2026-09-25: real users with a badge, without one, with one contest and with none all came back with no `errors` key.
- The env vars are prefixed `LEETCODE_` because Windows already sets `USERNAME` to the OS user.
- The card is written without a trailing newline, like the brand renderer, and identical data gives identical bytes, so a quiet day leaves nothing to commit.

## Repo-specific rules

- Keep the script stdlib-only. `action.yml` has no install step, so a third-party import breaks every consumer.
- The SVG stays self-contained: no scripts, no external fonts or images, CSS and SMIL only. GitHub serves README images through `<img>`.
- `html.escape` every string that reaches the SVG (username, title, badge). The accent is regex-validated instead, because it lands in attributes raw.
- `fetch` refuses anything outside `ALLOWED_HOSTS` (https only); keep `# nosec B310` on the `urlopen` line.
- No en or em dashes anywhere, including SVG text and docs.

## Usage

- In a workflow: `uses: Sagargupta16/leetcode-card-action@v1` with `username`; the caller's workflow commits the SVG itself (README Quick start).
- Standalone: `LEETCODE_USERNAME=<u> python leetcode_card.py`.

## Config

- No config file. Everything flows action input -> env var -> script: `LEETCODE_USERNAME` (required), `LEETCODE_OUTPUT`, `LEETCODE_THEME`, `LEETCODE_HEATMAP`, `LEETCODE_ACCENT` (empty means the theme's), `LEETCODE_TITLE`.
- Outputs written to `$GITHUB_OUTPUT`: `rating`, `badge`, `solved`, `contests`; `rating` and `badge` are empty when the user has none.

## Release

- Releases: v1.0.0 (2026-09-25), v1.0.1 (2026-10-11). Listed on the Marketplace as "LeetCode Card".
- A release is: merge the PR, tag `vX.Y.Z` on the merge commit, move the `v1` tag to it (`git tag -f -a v1 -m v1 <sha>`, `git push -f origin v1`), publish the GitHub release from the CHANGELOG entry, then re-pin `Sagargupta16/Sagargupta16/.github/workflows/render-svgs.yml`, which pins a full SHA, not `v1`.
