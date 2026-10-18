# Contributing to leetcode-card-action

This repo is a composite GitHub Action that renders a self-hosted, animated LeetCode contest rating card as an SVG. Bug reports, fixes, doc corrections and new inputs that come with tests are welcome.

## Setup

The script is Python standard library only and `action.yml` has no install step, so there is nothing to install. Lint and tests run with `uv`/`uvx` locally; CI uses pip with pinned versions.

## Before you open a PR

CI (`.github/workflows/ci.yml`) runs three jobs on every push to `main` and every pull request:

- `lint`: `pip install --only-binary :all: ruff==0.17.1`, then `ruff check .` on Python 3.13
- `test`: `pip install --only-binary :all: pytest==9.1.1`, then `pytest -v` on Python 3.12, 3.13 and 3.14
- `action`: runs `action.yml` from the checkout against a live LeetCode profile, checks the SVG parses as an accessible `<svg role="img">`, and fails if any of the four outputs is empty, then runs it again with `heatmap: true` and a dark and light output pair and checks both cards

Run the first two locally:

```bash
uvx ruff@0.17.1 check .
uv run --no-project --with pytest==9.1.1 pytest -v
```

The `action` job calls the real LeetCode API. If only that job is red while `lint` and `test` pass, check whether LeetCode was reachable before you debug your change.

To render a card by hand:

```bash
LEETCODE_USERNAME=<username> python leetcode_card.py
```

That writes `assets/leetcode.svg`, which is gitignored. If your change alters the card, regenerate every README preview with `python scripts/render_examples.py`.

## Conventions

- Tests live in `test_leetcode_card.py` at the repo root and never touch the network: tests that reach `fetch` monkeypatch it with canned GraphQL bytes.
- A new input touches three places: `inputs` in `action.yml`, the step's `env` block, and the `os.environ` read in `main()`. Env vars use the `LEETCODE_` prefix, because Windows already sets `USERNAME`.
- The default title lives in `action.yml` and in `DEFAULT_TITLE`. Keep them identical. The same goes for the theme list in the `theme` input description and `THEMES`.
- A new theme is four colors in `THEMES`. The contrast tests pick it up automatically; do not hand-pick shades that bypass `palette()`.
- Composite outputs need `value: ${{ steps.card.outputs.<name> }}` and `id: card` on the step that writes `$GITHUB_OUTPUT`.
- Keep the script standard library only. Any third-party import breaks every consumer.
- The SVG stays self-contained: no scripts, external fonts or images; CSS and SMIL only.
- `html.escape` every string that reaches the SVG (username, title, badge). The accent is regex-validated instead.
- `fetch` refuses anything outside `ALLOWED_HOSTS` (https only). Keep `# nosec B310` on the `urlopen` line.
- Every fetch failure goes through `FETCH_ERRORS` into one fallback: keep the existing card and warn, or fail when there is no card yet.
- Identical data must give identical bytes, so a quiet day leaves nothing to commit.
- No en or em dashes anywhere, including SVG text and docs. Use `-` or `--`.
- There is no `ruff.toml` on purpose. The `ruff` and `pytest` pins in `ci.yml` are bumped by hand, because Renovate does not read `run:` blocks.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`).
- `CHANGELOG.md` follows Keep a Changelog and Semantic Versioning. Add your entry under a concrete next version, for example `## [1.0.1] - YYYY-MM-DD`, with a matching link reference at the bottom.

## Security issues

Do not report vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md).

## License

This project is released under the MIT License (see [LICENSE](LICENSE)). By contributing, you agree that your contributions are licensed under it.
