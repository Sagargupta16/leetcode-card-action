# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-11-14

### Added

- `style` input: `classic` (the default, the card of 1.0 to 1.2, unchanged byte for byte) or `flat`, the newer look of the profile README this card came from. Flat panels with one hairline border and no gradient, glow or CSS animation; four stat tiles (contest rating, top worldwide, problems solved, contests) with the badge as a chip beside the title; the rating line on its own panel with the peak and the climb since the first contest; the Easy/Medium/Hard bars beside it. Every entrance rests on the finished card, so a still image shows the line and the bars where the classic card showed empty axes, and every loop lasts 2, 6 or 12 seconds. 840 x 324, or 840 x 490 with the heatmap.
- `layout` input: `desktop` (the default) or `phone`, a 320 px card ported from the profile's phone card: two tiles to a row, the bars, the rating line with its latest point pulsing, no label under 11.5 px, and with `heatmap: true` the last 20 weeks and the year's totals. A phone card is always flat and does not use `title`.
- An `output` line takes `?style=` and `?layout=` as well as `?theme=`, joined with `&`, so one run and one fetch write the wide card and its phone twin (`assets/leetcode-mobile.svg?layout=phone`).
- Every theme and `accent` work in the flat style: text reaches 4.5:1 on the card, a tile and the tinted lead tile, and the line, bars, heatmap shades and the lead tile's outline reach 3:1.
- `examples/flat/` previews (wide and phone, with and without the heatmap, and the light theme), rendered from live data on 2026-11-14; `python scripts/render_examples.py --flat` re-renders only those.
- CI runs the action a third time with `style: flat` and a phone line, and checks both widths.
- Tests: the classic card's bytes against hashes of the 1.2.0 output, the flat and phone cards resting on their finished frame, loops on the 2, 3, 4, 6, 12 or 24 s clock, the text floor, no gradient or filter, the widths, contrast for every theme and accent, the heatmap cells and the new options: 325 tests, up from 183.

### Changed

- The error for an unknown `output` option names the three options (`theme=`, `style=`, `layout=`). `parse_outputs` keeps its signature and return value; `parse_output_options` returns every option.
- The run log line now ends with the style and layout (`wrote <path> (N bytes, theme dark, style classic, layout desktop)`); the SVG bytes are unchanged.

## [1.2.0] - 2026-10-25

### Changed

- No text on the card is under 10.5 px. The title, chart axis, `PEAK` label, the line under the badge, the `SOLVED` tag, the Easy/Medium/Hard rows and the heatmap's labels and months were 8 to 10 px; on an 840 px card in an 831 px README column they read at about 7.9 px. A 10.5 px label holds 10.4 px there. Card sizes are unchanged (840 x 270, 840 x 422 with the heatmap).
- The `PEAK` label's placement estimate is 7.5 px a character to match, so the check that flips it right of the point near the left edge still holds.
- Checked in a browser on five themes (121 texts): no text crosses the card edge and no two labels overlap. svg-forge's `validate_svg.py --strict-contrast` reports 0 errors on all seven examples, which are re-rendered from live data.

## [1.1.0] - 2026-10-18

### Added

- `theme` input with six themes: `dark` (the default, unchanged), `light`, `github-dark`, `github-light`, `dracula` and `nord`. Each one goes through the same contrast gate: text reaches 4.5:1 on the theme's background, and the rating line, markers, difficulty bars and heatmap shades reach 3:1. Accents and difficulty colors that fail are darkened on light themes and lightened on dark ones; muted labels get the lowest opacity that passes.
- `output` takes one path per line, and a line can end in `?theme=<name>`, so one run and one fetch write a dark and a light card for a `<picture>` embed. If a fetch fails, the run keeps every existing card and fails only when one of them has nothing to keep.
- `heatmap: true` draws the past 53 weeks of daily submissions under the card, GitHub-style, with the year's submissions, active days and longest streak. It asks LeetCode for the submission calendar in the same single query. The empty grid is one SVG pattern, so only active days add markup, and the cells sweep in column by column.
- `scripts/render_examples.py` re-renders every README preview from one live fetch.
- CI runs the action a second time with `heatmap: true` and a `github-dark`/`github-light` pair, and checks both cards.
- Tests for every theme crossed with every tested accent, the heatmap window, levels, layout and totals, multi-line outputs and the new input validation: 183 tests, up from 87.

### Changed

- `accent` now defaults to the theme's accent. With the default `dark` theme that is `#f59e0b`, as before.
- README: previews re-rendered 2026-10-18, a Themes gallery, and a light and dark `<picture>` snippet.

### Fixed

- The peak ring pulsed from the first frame, before the rating line reached it: its CSS animation overrode the SMIL `set` that reveals it at 2.6s. The pulse now starts at 2.6s (measured in Chrome: opacity 0 until 2.6s, where it was 0.78 at 0.2s). Apart from that delay, the default card is byte for byte the 1.0.2 card.

## [1.0.2] - 2026-10-18

### Changed

- README: CI, release, Marketplace and license badges, a flow diagram of one run, the design decisions behind the action, and a Development section with the local lint and test commands.
- CI lints with ruff 0.17.1 (was 0.16.6). The tree passes it unchanged; CONTRIBUTING.md and CLAUDE.md name the new pin.

## [1.0.1] - 2026-10-11

### Fixed

- Every text color on the card now reaches WCAG 1.4.3 contrast (4.5:1) on its background. The rating axis labels were `rgba(255,255,255,0.35)` at 3.18:1 on the card's `#0b1012`; they are now `rgba(255,255,255,0.45)` at 4.53:1, the lowest alpha that passes. With the default accent nothing else changes.
- An `accent` too dark to read on the card is lightened, keeping its hue, to the nearest shade that reaches 4.5:1. It colors the heading, the badge line, the rating line, the peak marker and its label, which all fell below WCAG for dark accents (`#1e3a8a` measured 1.84:1). Accents that already pass are used exactly as typed. The lightened line also clears 3:1 (WCAG 1.4.11) on the card and on the tinted area under it.

### Added

- Tests that check every text color on every card state against 4.5:1, and the rating line, markers and difficulty bars against 3:1, for the default accent and dark, light and gray ones.

### Changed

- README preview re-rendered from live data on 2026-10-11.

## [1.0.0] - 2026-09-25

### Added

- Composite action that renders an animated LeetCode card into your repo, `assets/leetcode.svg` by default: the contest rating history as a line that draws itself in with the peak marked, plus badge, rating, top percentage, contests, solved count and Easy/Medium/Hard progress bars.
- Inputs `username` (required), `output`, `accent` and `title`. `{contests}` in `title` becomes the number of rated contests attended.
- Outputs `rating`, `badge`, `solved` and `contests`.
- A shorter card without the chart for users with fewer than two rated contests, reading "No contests yet" when there are none, and the rating in place of the badge for users without one.
- Fallback when LeetCode fails: the existing card is kept and the run warns. The step fails only when there is no card to keep yet.
- CI: ruff, pytest on Python 3.12, 3.13 and 3.14, and a job that runs `action.yml` against a live profile.

[1.3.0]: https://github.com/Sagargupta16/leetcode-card-action/releases/tag/v1.3.0
[1.2.0]: https://github.com/Sagargupta16/leetcode-card-action/releases/tag/v1.2.0
[1.1.0]: https://github.com/Sagargupta16/leetcode-card-action/releases/tag/v1.1.0
[1.0.2]: https://github.com/Sagargupta16/leetcode-card-action/releases/tag/v1.0.2
[1.0.1]: https://github.com/Sagargupta16/leetcode-card-action/releases/tag/v1.0.1
[1.0.0]: https://github.com/Sagargupta16/leetcode-card-action/releases/tag/v1.0.0
