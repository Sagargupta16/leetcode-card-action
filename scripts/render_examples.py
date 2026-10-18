"""Re-render every README preview from one live fetch.

    python scripts/render_examples.py [username]

Writes examples/leetcode.svg (the default card) and examples/themes/<theme>.svg
(one per theme, with the heatmap), then prints what each file shows so the
README alt text and numbers can be copied from real output.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import leetcode_card as card


def main() -> int:
    username = sys.argv[1] if len(sys.argv) > 1 else "sagargupta1610"
    lc = card.fetch_profile(username, heatmap=True)
    today = dt.datetime.now(dt.UTC).date()
    plain = {k: v for k, v in lc.items() if k != "calendar"}
    renders = {ROOT / "examples" / "leetcode.svg": card.render_card(plain, username)}
    for theme in card.THEMES:
        renders[ROOT / "examples" / "themes" / f"{theme}.svg"] = card.render_card(
            lc, username, theme=theme, today=today
        )
    for path, svg in renders.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8", newline="\n")
        print(f"{path.relative_to(ROOT).as_posix()}: {len(svg):,} bytes")
    act = card.activity(lc["calendar"], today)
    print(f"rendered {today.isoformat()} UTC for {username}")
    print(card.aria_label(lc, username, act))
    print(
        f"past year: {act['total']} submissions, {act['active']} active days, "
        f"max streak {act['streak']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
