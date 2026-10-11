"""Tests for leetcode_card.py. No network: every test that reaches fetch patches it."""

from __future__ import annotations

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
) -> bytes:
    """A response shaped like the ones leetcode.com/graphql returned on 2026-09-25."""
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
