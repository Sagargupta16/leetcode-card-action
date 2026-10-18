"""Tests for leetcode_card.py. No network: every test that reaches fetch patches it."""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
from pathlib import Path
from xml.dom import minidom

import pytest

import leetcode_card as card

BY_DIFFICULTY = {"Easy": [60, 800], "Medium": [50, 1600], "Hard": [10, 600]}


def profile(
    *,
    history: tuple[int, ...] = (1500, 1600, 1550),
    badge: str = "Knight",
    rating: int | None = 1550,
    top: float | None = 22.95,
) -> dict:
    """A profile shaped like the one parse_profile returns."""
    return {
        "badge": badge,
        "rating": rating,
        "top": top,
        "contests": len(history),
        "solved": 120,
        "by_difficulty": BY_DIFFICULTY,
        "history": list(history),
    }


NO_CONTESTS = profile(history=(), badge="", rating=None, top=None)


def counts(pairs: dict[str, int]) -> list[dict]:
    return [{"difficulty": k, "count": v} for k, v in pairs.items()]


def graphql(
    *,
    history: tuple[float, ...] = (1500.2, 1600.7, 1549.6),
    badge: str = "Knight",
    exists: bool = True,
    calendar: dict[str, int] | None = None,
) -> bytes:
    """A response shaped like the ones leetcode.com/graphql returned on 2026-09-25.

    calendar, keyed by UTC-midnight timestamps as strings, is the userCalendar the
    heatmap query adds (shape measured live on 2026-10-18).
    """
    ranking = None
    if history:
        ranking = {
            "rating": history[-1],
            "topPercentage": 22.9512,
            "attendedContestsCount": len(history),
            "badge": {"name": badge} if badge else None,
        }
    user = {
        "submitStats": {
            "acSubmissionNum": counts(
                {"All": 120, "Easy": 60, "Medium": 50, "Hard": 10}
            )
        }
    }
    if calendar is not None:
        user["userCalendar"] = {"submissionCalendar": json.dumps(calendar)}
    data = {
        "userContestRanking": ranking if exists else None,
        "userContestRankingHistory": [
            *({"attended": True, "rating": r} for r in history),
            {"attended": False, "rating": history[-1] if history else 1500},
        ],
        "allQuestionsCount": counts(
            {"All": 3000, "Easy": 800, "Medium": 1600, "Hard": 600}
        ),
        "matchedUser": user if exists else None,
    }
    return json.dumps({"data": data}).encode()


def parse(svg: str) -> minidom.Element:
    """Parse the card as XML and return the <svg> root; raises if it is malformed."""
    return minidom.parseString(svg).documentElement


def texts(root: minidom.Element) -> list[str]:
    """The first text node of every <text> element, in document order."""
    return [t.firstChild.data for t in root.getElementsByTagName("text")]


def big_line(root: minidom.Element) -> list[str]:
    """Text drawn at the badge line's 30px size."""
    return [
        t.firstChild.data
        for t in root.getElementsByTagName("text")
        if t.getAttribute("font-size") == "30"
    ]


def rating_line(root: minidom.Element) -> minidom.Element:
    return next(
        p
        for p in root.getElementsByTagName("path")
        if p.getAttribute("stroke-dasharray")
    )


def peak_ring(root: minidom.Element) -> tuple[str, str]:
    ring = next(
        c
        for c in root.getElementsByTagName("circle")
        if c.getAttribute("class") == "ring"
    )
    return ring.getAttribute("cx"), ring.getAttribute("cy")


def peak_label(root: minidom.Element) -> minidom.Element:
    return next(
        t
        for t in root.getElementsByTagName("text")
        if t.firstChild.data.startswith("PEAK ")
    )


# ---------------------------------------------------------------- chart path math


def test_chart_points_put_the_oldest_left_and_the_lowest_at_the_bottom() -> None:
    points = card.chart_points([1500, 1600, 1550])

    assert points == [(40.0, 220.0), (290.0, 70.0), (540.0, 145.0)]


def test_flat_history_sits_on_the_bottom_gridline() -> None:
    points = card.chart_points([1500, 1500])

    assert points == [(40.0, 220.0), (540.0, 220.0)]


def test_rating_line_path_and_dash_length_match_the_points() -> None:
    root = parse(card.render_card(profile(), "someone"))

    line = rating_line(root)

    assert line.getAttribute("d") == "M40.0 220.0 L290.0 70.0 L540.0 145.0"
    # hypot(250, 150) + hypot(250, 75) = 291.548 + 261.008 = 552.556
    assert line.getAttribute("stroke-dasharray") == "553"
    assert line.getAttribute("stroke-dashoffset") == "553"


def test_gridline_labels_show_low_mid_and_high_ratings() -> None:
    root = parse(card.render_card(profile(history=(1400, 1800, 1600)), "someone"))

    labels = [t for t in texts(root) if t.isdigit()]

    assert labels[:3] == ["1400", "1600", "1800"]


# ---------------------------------------------------------------- peak detection


def test_peak_ring_and_label_mark_the_highest_rating() -> None:
    root = parse(card.render_card(profile(history=(1500, 1700, 1600)), "someone"))

    assert peak_ring(root) == ("290.0", "70.0")
    assert peak_label(root).firstChild.data == "PEAK 1700"


def test_peak_is_the_first_of_two_equal_highs() -> None:
    root = parse(card.render_card(profile(history=(1500, 1700, 1600, 1700)), "someone"))

    # index 1 of 4 points: 40 + 500 / 3
    assert peak_ring(root) == ("206.7", "70.0")


def test_peak_label_ends_left_of_a_peak_with_room() -> None:
    root = parse(card.render_card(profile(history=(1500, 1600, 1700)), "someone"))

    label = peak_label(root)

    assert (label.getAttribute("text-anchor"), label.getAttribute("x")) == (
        "end",
        "534.0",
    )


def test_peak_label_flips_right_when_the_peak_is_at_the_left_edge() -> None:
    root = parse(card.render_card(profile(history=(1700, 1500, 1600)), "someone"))

    label = peak_label(root)

    assert (label.getAttribute("text-anchor"), label.getAttribute("x")) == (
        "start",
        "46.0",
    )


# ---------------------------------------------------------------- card states


def test_badge_user_shows_the_badge_over_rating_and_top_percentage() -> None:
    root = parse(card.render_card(profile(), "someone"))

    assert big_line(root) == ["Knight"]
    assert "RATING 1550  |  TOP 22.95%" in texts(root)


def test_no_badge_user_shows_the_rating_in_the_badge_line() -> None:
    root = parse(card.render_card(profile(badge="", rating=1611), "someone"))

    assert big_line(root) == ["1611"]
    assert "CONTEST RATING  |  TOP 22.95%" in texts(root)


def test_no_contest_user_gets_no_chart() -> None:
    root = parse(card.render_card(NO_CONTESTS, "someone"))

    assert root.getElementsByTagName("path").length == 0
    assert root.getAttribute("height") == "188"


def test_no_contest_user_reads_no_contests_yet() -> None:
    root = parse(card.render_card(NO_CONTESTS, "someone"))

    assert big_line(root) == ["No contests yet"]


def test_no_contest_user_keeps_the_solved_panel() -> None:
    root = parse(card.render_card(NO_CONTESTS, "someone"))

    shown = texts(root)

    assert "120" in shown
    assert [t for t in shown if t in {"EASY", "MEDIUM", "HARD"}] == [
        "EASY",
        "MEDIUM",
        "HARD",
    ]
    assert ["60/800", "50/1600", "10/600"] == [t for t in shown if "/" in t]


def test_one_contest_is_not_enough_for_a_chart_but_shows_the_rating() -> None:
    root = parse(
        card.render_card(profile(history=(1475,), badge="", rating=1475), "someone")
    )

    assert root.getElementsByTagName("path").length == 0
    assert big_line(root) == ["1475"]


@pytest.mark.parametrize(
    "lc",
    [
        profile(),
        profile(badge=""),
        profile(history=(1475,), badge="", rating=1475),
        NO_CONTESTS,
        profile(top=None),
    ],
    ids=["badge", "no-badge", "one-contest", "no-contests", "no-top-percentage"],
)
def test_every_card_state_is_a_valid_accessible_svg(lc: dict) -> None:
    root = parse(card.render_card(lc, "someone"))

    assert root.tagName == "svg"
    assert root.getAttribute("width") == "840"
    assert root.getAttribute("role") == "img"
    assert root.getAttribute("aria-label").startswith("LeetCode someone: ")


def test_card_has_no_scripts_or_external_references() -> None:
    svg = card.render_card(profile(), "someone")

    assert "<script" not in svg
    assert "href" not in svg
    assert "@import" not in svg


# ---------------------------------------------------------------- escaping and inputs


def test_title_badge_and_username_are_escaped() -> None:
    lc = profile(badge="<script>x</script>")

    svg = card.render_card(lc, 'a"&<b>', title='<b>"R&D"</b> {contests}')
    root = parse(svg)

    assert "<script>" not in svg
    assert "<b>" not in svg
    assert '<b>"R&D"</b> 3' in texts(root)
    assert big_line(root) == ["<script>x</script>"]
    assert root.getAttribute("aria-label").startswith('LeetCode a"&<b>: ')


def test_title_placeholder_is_the_only_substitution() -> None:
    root = parse(
        card.render_card(profile(), "someone", title="{contests} RATED {x} {0}")
    )

    assert "3 RATED {x} {0}" in texts(root)


def test_accent_colors_the_title_and_the_rating_line() -> None:
    root = parse(card.render_card(profile(), "someone", accent="#60a5fa"))

    assert root.getElementsByTagName("text")[0].getAttribute("fill") == "#60a5fa"
    assert rating_line(root).getAttribute("stroke") == "#60a5fa"


# ---------------------------------------------------------------- contrast

# The default, a light one, dark ones in several hues, gray, and both extremes
ACCENTS = [
    "#f59e0b",
    "#60a5fa",
    "#1e3a8a",
    "#7c3aed",
    "#b91c1c",
    "#555",
    "#000000",
    "#ffffff",
]
CONTRAST_STATES = {
    "chart": profile(),
    "peak-left": profile(history=(1700, 1500, 1600)),
    "one-contest": profile(history=(1475,), badge="", rating=1475),
    "no-contests": NO_CONTESTS,
}


def tint(color: str, alpha: float) -> str:
    """color at alpha over the card background, as the opaque hex a browser paints."""
    top, under = card.parse_color(color), card.parse_color(card.BG)
    return "#" + "".join(
        f"{round(t * alpha + u * (1 - alpha)):02x}"
        for t, u in zip(top[:3], under[:3], strict=True)
    )


def test_contrast_is_21_for_black_on_white() -> None:
    assert card.contrast("#000", "#fff") == pytest.approx(21)


def test_contrast_blends_a_translucent_color_over_the_card() -> None:
    # the 1.0.0 axis labels, which svg-forge's validator measured at 3.18:1
    assert card.contrast("rgba(255,255,255,0.35)") == pytest.approx(3.19, abs=0.01)


def test_a_readable_accent_is_kept_as_typed() -> None:
    assert card.readable("#F59E0B") == "#F59E0B"


def test_a_dark_accent_is_lightened_just_enough_to_read() -> None:
    fixed = card.readable("#1e3a8a")

    assert 4.5 <= card.contrast(fixed) < 4.6


@pytest.mark.parametrize("accent", ACCENTS)
@pytest.mark.parametrize("lc", CONTRAST_STATES.values(), ids=CONTRAST_STATES.keys())
def test_every_text_color_reaches_4_5_to_1_on_the_card(lc: dict, accent: str) -> None:
    root = parse(card.render_card(lc, "someone", accent=accent))

    # no text sits on another shape, so the card background is behind all of it
    fills = {
        el.getAttribute("fill")
        for tag in ("text", "tspan")
        for el in root.getElementsByTagName(tag)
        if el.getAttribute("fill")
    }

    assert {
        f: round(card.contrast(f), 2) for f in fills if card.contrast(f) < 4.5
    } == {}


@pytest.mark.parametrize("accent", ACCENTS)
def test_rating_line_and_markers_reach_3_to_1(accent: str) -> None:
    root = parse(card.render_card(profile(), "someone", accent=accent))
    line = rating_line(root).getAttribute("stroke")
    top_stop = root.getElementsByTagName("stop")[0]
    area_top = tint(
        top_stop.getAttribute("stop-color"),
        float(top_stop.getAttribute("stop-opacity")),
    )
    marks = [
        c.getAttribute("stroke") or c.getAttribute("fill")
        for c in root.getElementsByTagName("circle")
    ]

    # WCAG 1.4.11: the line on the card and on the tinted area right under it
    assert card.contrast(line) >= 3
    assert card.contrast(line, area_top) >= 3
    assert min(card.contrast(m) for m in marks) >= 3


def test_difficulty_bars_reach_3_to_1_on_their_track() -> None:
    track = tint("#ffffff", 0.07)

    assert min(card.contrast(c, track) for c in card.LC_COLORS.values()) >= 3


# ---------------------------------------------------------------- parsing


def test_parse_profile_rounds_the_contest_numbers() -> None:
    lc = card.parse_profile(json.loads(graphql()), "someone")

    assert (lc["rating"], lc["top"], lc["contests"], lc["badge"]) == (
        1550,
        22.95,
        3,
        "Knight",
    )


def test_parse_profile_keeps_only_attended_contests() -> None:
    lc = card.parse_profile(json.loads(graphql()), "someone")

    assert lc["history"] == [1500, 1601, 1550]


def test_parse_profile_reads_solved_counts_per_difficulty() -> None:
    lc = card.parse_profile(json.loads(graphql()), "someone")

    assert (lc["solved"], lc["by_difficulty"]) == (120, BY_DIFFICULTY)


def test_parse_profile_reads_a_user_without_contests() -> None:
    lc = card.parse_profile(json.loads(graphql(history=())), "someone")

    assert (lc["rating"], lc["top"], lc["contests"], lc["history"]) == (
        None,
        None,
        0,
        [],
    )


def test_parse_profile_reads_a_user_without_a_badge() -> None:
    lc = card.parse_profile(json.loads(graphql(badge="")), "someone")

    assert lc["badge"] == ""


def test_parse_profile_rejects_a_partial_answer_with_errors() -> None:
    payload = json.loads(graphql())
    payload["data"]["userContestRanking"] = None
    payload["errors"] = [{"message": "contest service unavailable"}]

    with pytest.raises(LookupError, match="contest service unavailable"):
        card.parse_profile(payload, "someone")


def test_parse_profile_rejects_a_missing_user() -> None:
    with pytest.raises(LookupError, match="'ghost' does not exist"):
        card.parse_profile(json.loads(graphql(exists=False)), "ghost")


@pytest.mark.parametrize(
    "url",
    [
        "http://leetcode.com/graphql",
        "https://leetcode.com.evil.example/graphql",
        "https://example.com/graphql",
    ],
)
def test_fetch_refuses_urls_outside_the_allowlist(url: str) -> None:
    with pytest.raises(ValueError, match="refusing"):
        card.fetch(url, {})


# ---------------------------------------------------------------- main and fallback


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Set the environment the way action.yml does; return the card and output paths."""
    out = tmp_path / "assets" / "leetcode.svg"
    github_output = tmp_path / "github_output"
    monkeypatch.setenv("LEETCODE_USERNAME", "someone")
    monkeypatch.setenv("LEETCODE_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.delenv("LEETCODE_ACCENT", raising=False)
    monkeypatch.delenv("LEETCODE_TITLE", raising=False)
    return out, github_output


def offline(url: str, body: dict) -> bytes:
    raise urllib.error.URLError("network is unreachable")


def test_main_writes_a_parseable_card(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = paths
    monkeypatch.setattr(card, "fetch", lambda url, body: graphql())

    assert card.main() == 0
    assert parse(out.read_text(encoding="utf-8")).tagName == "svg"


def test_main_writes_the_step_outputs(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, github_output = paths
    monkeypatch.setattr(card, "fetch", lambda url, body: graphql())

    card.main()

    assert github_output.read_text(encoding="utf-8").splitlines() == [
        "rating=1550",
        "badge=Knight",
        "solved=120",
        "contests=3",
    ]


def test_outputs_are_empty_without_a_rating_or_a_badge(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, github_output = paths
    monkeypatch.setattr(card, "fetch", lambda url, body: graphql(history=()))

    card.main()

    assert github_output.read_text(encoding="utf-8").splitlines() == [
        "rating=",
        "badge=",
        "solved=120",
        "contests=0",
    ]


def test_failed_fetch_keeps_the_existing_card(
    paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out, github_output = paths
    out.parent.mkdir(parents=True)
    out.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(card, "fetch", offline)

    assert card.main() == 0
    assert out.read_text(encoding="utf-8") == "<svg/>"
    assert capsys.readouterr().out.startswith("::warning::LeetCode fetch failed")
    assert not github_output.exists()


def test_failed_fetch_without_a_card_fails_with_the_reason(
    paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out, _ = paths
    monkeypatch.setattr(card, "fetch", offline)

    assert card.main() == 1
    assert not out.exists()
    assert "::error::LeetCode fetch failed" in capsys.readouterr().out


def test_missing_user_is_reported_by_name(
    paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(card, "fetch", lambda url, body: graphql(exists=False))

    assert card.main() == 1
    assert "'someone' does not exist" in capsys.readouterr().out


def test_changed_response_shape_counts_as_a_failed_fetch(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = paths
    out.parent.mkdir(parents=True)
    out.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(card, "fetch", lambda url, body: b'{"data": {"renamed": 1}}')

    assert card.main() == 0
    assert out.read_text(encoding="utf-8") == "<svg/>"


def test_invalid_accent_fails_before_fetching(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEETCODE_ACCENT", 'red" onload="x')
    monkeypatch.setattr(card, "fetch", lambda url, body: pytest.fail("fetched"))

    assert card.main() == 1


def test_missing_username_fails_before_fetching(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEETCODE_USERNAME", " ")
    monkeypatch.setattr(card, "fetch", lambda url, body: pytest.fail("fetched"))

    assert card.main() == 1


# ---------------------------------------------------------------- themes


def test_the_default_theme_keeps_the_1_0_colors() -> None:
    pal = card.palette()

    assert (pal["bg"], pal["accent"], pal["text"]) == ("#0b1012", "#f59e0b", "#f3f4f6")
    assert (pal["axis"], pal["sub"], pal["label"]) == (
        "rgba(255,255,255,0.45)",
        "rgba(255,255,255,0.55)",
        "rgba(255,255,255,0.5)",
    )
    assert pal["difficulty"] == card.LC_COLORS


def test_the_dark_theme_is_the_default_card() -> None:
    assert card.render_card(profile(), "someone") == card.render_card(
        profile(), "someone", theme="dark"
    )


def test_each_theme_paints_its_own_background() -> None:
    for name, theme in card.THEMES.items():
        root = parse(card.render_card(profile(), "someone", theme=name))

        assert root.getElementsByTagName("rect")[0].getAttribute("fill") == theme["bg"]


def test_a_light_accent_is_darkened_on_a_light_theme() -> None:
    fixed = card.readable("#f59e0b", "#ffffff")

    assert card.contrast("#f59e0b", "#ffffff") < 4.5
    assert 4.5 <= card.contrast(fixed, "#ffffff") < 4.6


def test_the_theme_accent_is_used_when_no_accent_is_given() -> None:
    root = parse(card.render_card(profile(), "someone", theme="github-light"))

    assert rating_line(root).getAttribute("stroke") == "#0969da"


def ink_tint(theme: str, alpha: float) -> str:
    """The theme's ink at alpha over its background, as an opaque hex."""
    rgb = "#" + "".join(f"{int(c):02x}" for c in card.THEMES[theme]["ink"].split(","))
    return card.blend(rgb, card.THEMES[theme]["bg"], alpha)


@pytest.mark.parametrize("theme", card.THEMES)
@pytest.mark.parametrize("accent", [None, *ACCENTS])
def test_every_theme_reaches_wcag_contrast(theme: str, accent: str | None) -> None:
    bg = card.THEMES[theme]["bg"]
    lc = dict(profile(), calendar={dt.date(2026, 10, 1): 3, dt.date(2026, 10, 2): 9})
    root = parse(
        card.render_card(lc, "someone", accent=accent, theme=theme, today=TODAY)
    )
    pal = card.palette(theme, accent)
    fills = {
        el.getAttribute("fill")
        for tag in ("text", "tspan")
        for el in root.getElementsByTagName(tag)
        if el.getAttribute("fill")
    }
    track = ink_tint(theme, 0.07)

    # WCAG 1.4.3 for text, 1.4.11 for the line, the bars on their track and every heat level
    assert {
        f: round(card.contrast(f, bg), 2) for f in fills if card.contrast(f, bg) < 4.5
    } == {}
    assert card.contrast(rating_line(root).getAttribute("stroke"), bg) >= 3
    assert min(card.contrast(c, track) for c in pal["difficulty"].values()) >= 3
    assert min(card.contrast(c, bg) for c in pal["heat"]) >= 3


# ---------------------------------------------------------------- peak ring timing


def test_the_peak_ring_pulse_waits_for_the_ring_to_appear() -> None:
    svg = card.render_card(profile(), "someone")

    assert ".ring{animation:ring 2.2s ease-out 2.6s infinite" in svg
    assert '<set attributeName="opacity" to="1" begin="2.6s"' in svg


# ---------------------------------------------------------------- heatmap

TODAY = dt.date(2026, 10, 14)  # a Wednesday


def heatmap_card(calendar: dict[dt.date, int], **kw: object) -> minidom.Element:
    lc = dict(profile(**kw), calendar=calendar)
    return parse(card.render_card(lc, "someone", today=TODAY))


def cells(root: minidom.Element) -> list[minidom.Element]:
    return [
        r
        for r in root.getElementsByTagName("rect")
        if r.getAttribute("class").startswith("l")
    ]


def test_the_window_starts_on_a_sunday_52_weeks_before_this_week() -> None:
    act = card.activity({}, TODAY)

    assert act["start"] == dt.date(2025, 10, 12)
    assert act["start"].weekday() == 6  # Sunday
    assert len(act["counts"]) == 52 * 7 + 4  # then Sunday to Wednesday of this week


def test_activity_counts_only_the_window() -> None:
    calendar = {
        dt.date(2025, 10, 11): 50,  # the Saturday before the window
        dt.date(2025, 10, 12): 2,
        dt.date(2026, 10, 13): 1,
        dt.date(2026, 10, 14): 4,
        dt.date(2026, 10, 15): 7,  # tomorrow
    }

    act = card.activity(calendar, TODAY)

    assert (act["total"], act["active"], act["streak"]) == (7, 3, 2)


def test_the_streak_is_the_longest_run_of_active_days() -> None:
    days = [dt.date(2026, 3, 1) + dt.timedelta(days=d) for d in (0, 1, 2, 4, 5)]

    act = card.activity(dict.fromkeys(days, 1), TODAY)

    assert act["streak"] == 3


@pytest.mark.parametrize(
    ("count", "peak", "level"),
    [(1, 1, 4), (1, 16, 1), (2, 16, 2), (5, 16, 3), (9, 16, 4), (16, 16, 4)],
)
def test_heat_levels_follow_a_log_scale(count: int, peak: int, level: int) -> None:
    assert card.heat_level(count, peak) == level


def test_heatmap_draws_one_cell_per_active_day() -> None:
    calendar = {dt.date(2026, 1, 5): 5, dt.date(2026, 1, 6): 1, TODAY: 16}

    root = heatmap_card(calendar)

    assert len(cells(root)) == 3
    assert {c.getAttribute("class") for c in cells(root)} == {"l1", "l3", "l4"}


def test_todays_cell_sits_in_the_last_column_on_its_weekday_row() -> None:
    root = heatmap_card({TODAY: 1})

    (cell,) = cells(root)
    grid_top = 270 - 24 + 54

    assert cell.getAttribute("x") == str(24 + 52 * 15)
    assert cell.getAttribute("y") == str(grid_top + 3 * 15)  # Wednesday is row 3


def test_heatmap_spans_the_card_margins() -> None:
    root = heatmap_card({})
    full, current = (
        r
        for r in root.getElementsByTagName("rect")
        if r.getAttribute("fill") == "url(#day)"
    )

    right = int(current.getAttribute("x")) + int(current.getAttribute("width"))

    assert (full.getAttribute("x"), right) == ("24", 816)
    assert current.getAttribute("height") == str(4 * 15 - 3)  # Sunday to Wednesday


def test_heatmap_shows_the_year_totals() -> None:
    root = heatmap_card({dt.date(2026, 10, 12): 1, dt.date(2026, 10, 13): 2})

    shown = texts(root)

    assert "3 SUBMISSIONS IN THE PAST YEAR" in shown
    assert "2 ACTIVE DAYS  |  MAX STREAK 2" in shown
    assert root.getAttribute("aria-label").endswith(", 3 submissions in the past year")


def test_heatmap_uses_the_singular_for_one() -> None:
    shown = texts(heatmap_card({TODAY: 1}))

    assert "1 SUBMISSION IN THE PAST YEAR" in shown
    assert "1 ACTIVE DAY  |  MAX STREAK 1" in shown


def test_heatmap_labels_the_months() -> None:
    months = [t for t in texts(heatmap_card({})) if t in card.MONTHS]

    assert months == [
        "NOV",
        "DEC",
        "JAN",
        "FEB",
        "MAR",
        "APR",
        "MAY",
        "JUN",
        "JUL",
        "AUG",
        "SEP",
        "OCT",
    ]


def test_heatmap_makes_the_card_taller() -> None:
    no_contests = heatmap_card({}, history=(), badge="", rating=None, top=None)

    assert heatmap_card({}).getAttribute("height") == "422"
    assert no_contests.getAttribute("height") == "340"


def test_an_empty_year_still_draws_the_grid() -> None:
    root = heatmap_card({})

    assert cells(root) == []
    assert "0 SUBMISSIONS IN THE PAST YEAR" in texts(root)


def test_no_calendar_means_no_heatmap() -> None:
    svg = card.render_card(profile(), "someone")

    assert "url(#day)" not in svg
    assert "PAST YEAR" not in svg


def test_heatmap_card_is_self_contained() -> None:
    lc = dict(profile(), calendar={TODAY: 2})
    svg = card.render_card(lc, "someone", today=TODAY)

    assert "<script" not in svg
    assert "href" not in svg


def test_the_query_asks_for_the_calendar_only_for_a_heatmap() -> None:
    query = card.leetcode_query(heatmap=True)

    assert "userCalendar" not in card.leetcode_query()
    assert "userCalendar{submissionCalendar}" in query
    assert query.count("{") == query.count("}")


def test_parse_profile_reads_the_calendar_by_utc_date() -> None:
    # 1760313600 is 2025-10-13 00:00 UTC
    payload = json.loads(graphql(calendar={"1760313600": 4}))

    lc = card.parse_profile(payload, "someone")

    assert lc["calendar"] == {dt.date(2025, 10, 13): 4}


def test_parse_profile_has_no_calendar_unless_asked() -> None:
    assert "calendar" not in card.parse_profile(json.loads(graphql()), "someone")


def test_a_null_calendar_reads_as_an_empty_year() -> None:
    payload = json.loads(graphql(calendar={}))
    payload["data"]["matchedUser"]["userCalendar"] = None

    assert card.parse_profile(payload, "someone")["calendar"] == {}


# ---------------------------------------------------------------- several outputs


def test_one_output_line_uses_the_default_theme() -> None:
    assert card.parse_outputs("assets/leetcode.svg", "nord") == [
        (Path("assets/leetcode.svg"), "nord")
    ]


def test_each_output_line_can_pick_its_theme() -> None:
    raw = "\n  assets/dark.svg \nassets/light.svg ?theme=github-light\n\n"

    assert card.parse_outputs(raw, "dark") == [
        (Path("assets/dark.svg"), "dark"),
        (Path("assets/light.svg"), "github-light"),
    ]


@pytest.mark.parametrize(
    ("raw", "theme", "message"),
    [
        ("a.svg?theme=solarized", "dark", "unknown theme 'solarized'"),
        ("a.svg", "pink", "unknown theme 'pink'"),
        ("a.svg?palette=dark", "dark", "unknown option 'palette'"),
        (" \n ", "dark", "output is empty"),
    ],
)
def test_bad_outputs_are_rejected(raw: str, theme: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        card.parse_outputs(raw, theme)


def test_main_writes_every_output_in_its_theme(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = paths
    light = out.with_name("leetcode-light.svg")
    monkeypatch.setenv("LEETCODE_OUTPUT", f"{out}\n{light}?theme=light")
    monkeypatch.setattr(card, "fetch", lambda url, body: graphql())

    assert card.main() == 0
    for path, theme in ((out, "dark"), (light, "light")):
        root = parse(path.read_text(encoding="utf-8"))
        bg = root.getElementsByTagName("rect")[0].getAttribute("fill")
        assert bg == card.THEMES[theme]["bg"]


def test_main_asks_for_the_calendar_when_heatmap_is_on(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = paths
    sent = []

    def answer(url: str, body: dict) -> bytes:
        sent.append(body["query"])
        return graphql(calendar={"1760313600": 4})

    monkeypatch.setenv("LEETCODE_HEATMAP", "True")
    monkeypatch.setattr(card, "fetch", answer)

    assert card.main() == 0
    assert "userCalendar" in sent[0]
    assert "PAST YEAR" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LEETCODE_HEATMAP", "yes"),
        ("LEETCODE_THEME", "solarized"),
        ("LEETCODE_OUTPUT", "a.svg?x=1"),
    ],
)
def test_bad_options_fail_before_fetching(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    monkeypatch.setattr(card, "fetch", lambda url, body: pytest.fail("fetched"))

    assert card.main() == 1


def test_failed_fetch_fails_when_any_output_is_missing(
    paths: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out, _ = paths
    light = out.with_name("leetcode-light.svg")
    out.parent.mkdir(parents=True)
    out.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setenv("LEETCODE_OUTPUT", f"{out}\n{light}?theme=light")
    monkeypatch.setattr(card, "fetch", offline)

    assert card.main() == 1
    assert f"there is no {light} to keep" in capsys.readouterr().out
    assert out.read_text(encoding="utf-8") == "<svg/>"


def test_failed_fetch_keeps_every_existing_output(
    paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    out, _ = paths
    light = out.with_name("leetcode-light.svg")
    out.parent.mkdir(parents=True)
    for path in (out, light):
        path.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setenv("LEETCODE_OUTPUT", f"{out}\n{light}?theme=light")
    monkeypatch.setattr(card, "fetch", offline)

    assert card.main() == 0
