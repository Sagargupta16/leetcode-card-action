"""Re-render every README preview from one live fetch.

    python scripts/render_examples.py [username] [--flat]

Writes examples/leetcode.svg (the default card) and examples/themes/<theme>.svg
(one per theme, with the heatmap), then the flat style's previews in
examples/flat/: leetcode.svg and leetcode-mobile.svg (the 840 px card and its
phone twin), heatmap.svg and heatmap-mobile.svg (the same with the heatmap) and
light.svg (the light theme). --flat writes the flat previews only. It prints
what each file shows so the README alt text and numbers can be copied from
real output.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import leetcode_card as card


def main() -> int:
    args = [arg for arg in sys.argv[1:] if arg != "--flat"]
    flat_only = len(args) < len(sys.argv) - 1
    username = args[0] if args else "sagargupta1610"
    lc = card.fetch_profile(username, heatmap=True)
    today = dt.datetime.now(dt.UTC).date()
    plain = {k: v for k, v in lc.items() if k != "calendar"}
    renders = {}
    if not flat_only:
        renders[ROOT / "examples" / "leetcode.svg"] = card.render_card(plain, username)
        for theme in card.THEMES:
            renders[ROOT / "examples" / "themes" / f"{theme}.svg"] = card.render_card(
                lc, username, theme=theme, today=today
            )
    flat = ROOT / "examples" / "flat"
    renders[flat / "leetcode.svg"] = card.render_flat_card(plain, username)
    renders[flat / "leetcode-mobile.svg"] = card.render_phone_card(plain, username)
    renders[flat / "heatmap.svg"] = card.render_flat_card(lc, username, today=today)
    renders[flat / "heatmap-mobile.svg"] = card.render_phone_card(
        lc, username, today=today
    )
    renders[flat / "light.svg"] = card.render_flat_card(plain, username, theme="light")
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
