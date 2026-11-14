"""Render an animated LeetCode contest rating card as a self-contained SVG.

This file is the whole action: action.yml sets up Python and runs it with the
inputs as environment variables. It also runs standalone:

    LEETCODE_USERNAME=your-username python leetcode_card.py

Data comes from LeetCode's public GraphQL endpoint, which is unofficial and
needs no auth. When a fetch fails the existing card is kept, so a flaky API
never blanks a README. Stdlib only, because action.yml installs nothing else.

GitHub serves README images through an <img>, so the SVG must stay fully
self-contained: no scripts, no external fonts or images, CSS and SMIL only.
"""

from __future__ import annotations

import colorsys
import datetime as dt
import itertools
import json
import math
import os
import re
import sys
import unicodedata
import urllib.request
from html import escape
from http.client import HTTPException
from pathlib import Path

DEFAULT_OUTPUT = "assets/leetcode.svg"
DEFAULT_THEME = "dark"
DEFAULT_TITLE = "LEETCODE CONTEST RATING | {contests} CONTESTS"
HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}")
# classic is the card of 1.0 to 1.2; flat is the profile README's new look. A phone card is
# always drawn flat, because there is no classic phone card.
STYLES = ("classic", "flat")
LAYOUTS = ("desktop", "phone")
DEFAULT_STYLE = "classic"
DEFAULT_LAYOUT = "desktop"

# Named palettes. "ink" is the RGB that muted labels, gridlines and tracks are
# drawn in at partial alpha; "text" is the solved count; "accent" is the default
# accent. "dark" is the palette of the profile README card this action was
# extracted from, and stays its default.
THEMES = {
    "dark": {
        "bg": "#0b1012",
        "ink": "255,255,255",
        "text": "#f3f4f6",
        "accent": "#f59e0b",
    },
    "light": {
        "bg": "#ffffff",
        "ink": "31,35,40",
        "text": "#1f2328",
        "accent": "#b45309",
    },
    "github-dark": {
        "bg": "#0d1117",
        "ink": "230,237,243",
        "text": "#e6edf3",
        "accent": "#4493f8",
    },
    "github-light": {
        "bg": "#ffffff",
        "ink": "31,35,40",
        "text": "#1f2328",
        "accent": "#0969da",
    },
    "dracula": {
        "bg": "#282a36",
        "ink": "248,248,242",
        "text": "#f8f8f2",
        "accent": "#bd93f9",
    },
    "nord": {
        "bg": "#2e3440",
        "ink": "236,239,244",
        "text": "#eceff4",
        "accent": "#88c0d0",
    },
}
BG = THEMES[DEFAULT_THEME]["bg"]
MONO = "'JetBrains Mono','SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"
SANS = "'Segoe UI',Inter,-apple-system,BlinkMacSystemFont,Helvetica,Arial,sans-serif"
LC_COLORS = {"Easy": "#00b8a3", "Medium": "#ffc01e", "Hard": "#ef4743"}
SVG_CLOSE = "</svg>"
# WCAG 1.4.3 for text under 24 px (18.66 px bold). Every text color on the card meets it,
# the big badge line included, though 3:1 would do there.
MIN_CONTRAST = 4.5

W = 840
CHART_BOX = (40, 540, 70, 220)  # left, right, top, bottom of the rating chart
PANEL_X = 600

# The heatmap is GitHub's layout: one column per week, Sunday on top, the last
# column the current week. 53 columns of 12 px cells on a 15 px pitch span
# x = 24 to 816, the same margins as the rest of the card.
HEATMAP_WEEKS = 53
HEATMAP_CELL = 12
HEATMAP_PITCH = 15
HEATMAP_X = 24
# The heatmap starts 24 px above the bottom of the card it extends and adds this much
HEATMAP_HEIGHT = 176
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN")
MONTHS += ("JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

GRAPHQL_URL = "https://leetcode.com/graphql"
ALLOWED_HOSTS = ("https://leetcode.com/",)
QUERY_HEAD = (
    "query($u:String!){userContestRanking(username:$u){rating topPercentage "
    "attendedContestsCount badge{name}} userContestRankingHistory(username:$u)"
    "{attended rating} allQuestionsCount{difficulty count} matchedUser(username:$u)"
    "{submitStats{acSubmissionNum{difficulty count}}"
)
# The past year of submissions per UTC day, as a JSON string of {timestamp: count}
CALENDAR_FIELD = " userCalendar{submissionCalendar}"


def leetcode_query(heatmap: bool = False) -> str:
    """The one GraphQL query a run sends; the calendar is only asked for when it is drawn."""
    return QUERY_HEAD + (CALENDAR_FIELD if heatmap else "") + "}}"


LEETCODE_QUERY = leetcode_query()
# What a fetch can fail with: network and HTTP errors, bad JSON, a missing user,
# or a response whose shape changed under us (the API is unofficial).
FETCH_ERRORS = (
    OSError,
    HTTPException,
    ValueError,
    LookupError,
    TypeError,
    AttributeError,
)


def fetch(url: str, body: dict, timeout: int = 20) -> bytes:
    """POST body as JSON and return the raw response; allowlisted https URLs only."""
    if not url.startswith(ALLOWED_HOSTS):
        raise ValueError(f"refusing to fetch {url}")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "User-Agent": "leetcode-card-action (+https://github.com/Sagargupta16/leetcode-card-action)",
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com",
        },
    )
    # scheme and host were checked against ALLOWED_HOSTS above
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        return resp.read()


def parse_calendar(raw: str | None) -> dict[dt.date, int]:
    """LeetCode's submissionCalendar, a JSON string keyed by UTC-midnight timestamps, by date."""
    return {
        dt.datetime.fromtimestamp(int(ts), dt.UTC).date(): int(n)
        for ts, n in json.loads(raw or "{}").items()
    }


def parse_profile(payload: dict, username: str) -> dict:
    """Return the numbers the card shows, read from one GraphQL response."""
    data = payload["data"]
    user = data["matchedUser"]
    if user is None:
        raise LookupError(f"LeetCode user {username!r} does not exist")
    if payload.get("errors"):
        # a partial answer would draw a wrong card over the last good one
        raise LookupError(f"LeetCode answered with errors: {payload['errors'][0]}")
    rank = data["userContestRanking"]  # null until the first rated contest
    top = (rank or {}).get("topPercentage")
    solved = {
        x["difficulty"]: x["count"] for x in user["submitStats"]["acSubmissionNum"]
    }
    totals = {x["difficulty"]: x["count"] for x in data["allQuestionsCount"]}
    lc = {
        "badge": ((rank or {}).get("badge") or {}).get("name") or "",
        "rating": round(rank["rating"]) if rank else None,
        "top": None if top is None else round(top, 2),
        "contests": rank["attendedContestsCount"] if rank else 0,
        "solved": solved["All"],
        "by_difficulty": {
            k: [solved.get(k, 0), totals.get(k, 0)] for k in ("Easy", "Medium", "Hard")
        },
        "history": [
            round(x["rating"])
            for x in data["userContestRankingHistory"] or []
            if x["attended"]
        ],
    }
    if "userCalendar" in user:
        lc["calendar"] = parse_calendar(
            (user["userCalendar"] or {}).get("submissionCalendar")
        )
    return lc


def fetch_profile(username: str, heatmap: bool = False) -> dict:
    query = leetcode_query(heatmap)
    raw = fetch(GRAPHQL_URL, {"query": query, "variables": {"u": username}})
    return parse_profile(json.loads(raw), username)


def parse_color(color: str) -> tuple[float, float, float, float]:
    """#rgb, #rrggbb or rgba(r,g,b,a), the forms the card uses, as (r, g, b, alpha)."""
    if color.startswith("rgba("):
        r, g, b, a = (float(x) for x in color[5:-1].split(","))
        return r, g, b, a
    digits = color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16), 1.0


def luminance(r: float, g: float, b: float) -> float:
    """WCAG 2.2 relative luminance of an sRGB color with 0 to 255 channels."""

    def linear(v: float) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


def contrast(fg: str, bg: str = BG) -> float:
    """WCAG 2.2 contrast ratio of fg on the opaque bg; a translucent fg is blended over bg first."""
    *top, alpha = parse_color(fg)
    *under, _ = parse_color(bg)
    painted = [t * alpha + u * (1 - alpha) for t, u in zip(top, under, strict=True)]
    a, b = luminance(*painted), luminance(*under)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def readable(color: str, bg: str = BG) -> str:
    """color if text in it reaches MIN_CONTRAST on bg, else the nearest shade of its hue that does.

    On a dark card only lighter shades gain contrast and white gets there; on a light card
    only darker ones do and black gets there. Every theme's bg is one or the other.
    """
    if contrast(color, bg) >= MIN_CONTRAST:
        return color
    step_sign = 1 if contrast("#ffffff", bg) >= contrast("#000000", bg) else -1
    r, g, b, _ = parse_color(color)
    hue, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    shades = (
        colorsys.hls_to_rgb(
            hue, min(max(light + step_sign * step / 1000, 0.0), 1.0), sat
        )
        for step in range(1, 1001)
    )
    hexes = ("#" + "".join(f"{round(v * 255):02x}" for v in rgb) for rgb in shades)
    return next(h for h in hexes if contrast(h, bg) >= MIN_CONTRAST)


def muted(theme: dict, alpha: float) -> str:
    """Label text in the theme's ink at alpha, raised in 0.01 steps until it reaches MIN_CONTRAST."""
    for a in (round(alpha + i / 100, 2) for i in range(101)):
        color = f"rgba({theme['ink']},{a:g})"
        if a >= 1 or contrast(color, theme["bg"]) >= MIN_CONTRAST:
            return color
    raise AssertionError("unreachable: alpha 1 always returns")


def blend(color: str, bg: str, alpha: float) -> str:
    """color painted at alpha over bg, as the opaque hex a browser shows."""
    top, under = parse_color(color), parse_color(bg)
    return "#" + "".join(
        f"{round(t * alpha + u * (1 - alpha)):02x}"
        for t, u in zip(top[:3], under[:3], strict=True)
    )


def heat_colors(accent: str, bg: str) -> list[str]:
    """Four heatmap shades of the accent, the faintest still 3:1 on bg (WCAG 1.4.11).

    The faintest is the accent at the lowest alpha over bg that reaches 3:1, at least 0.35;
    the other three step evenly from there to the full accent.
    """
    low = next(
        a
        for a in (round(0.35 + i / 100, 2) for i in range(66))
        if a >= 1 or contrast(blend(accent, bg, a), bg) >= 3
    )
    return [blend(accent, bg, low + (1 - low) * i / 3) for i in range(4)]


def palette(theme: str = DEFAULT_THEME, accent: str | None = None) -> dict:
    """Every color the card paints for a theme, text colors already raised to MIN_CONTRAST.

    The dark theme with its default accent gives exactly the colors of the 1.0 card.
    """
    t = THEMES[theme]
    bg, ink = t["bg"], t["ink"]
    accent = readable(accent or t["accent"], bg)
    return {
        "bg": bg,
        "accent": accent,
        "text": readable(t["text"], bg),
        "axis": muted(t, 0.45),
        "sub": muted(t, 0.55),
        "label": muted(t, 0.5),
        "border": f"rgba({ink},0.08)",
        "grid": f"rgba({ink},0.06)",
        "track": f"rgba({ink},0.07)",
        "difficulty": {k: readable(v, bg) for k, v in LC_COLORS.items()},
        "heat": heat_colors(accent, bg),
    }


def svg_open(w: int, h: int, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{escape(label)}">'
    )


def headline(lc: dict) -> tuple[str, str]:
    """Return the big line and the line under it: the badge, else the rating."""
    if lc["rating"] is None:
        return "No contests yet", ""
    top = "" if lc["top"] is None else f"  |  TOP {lc['top']}%"
    if lc["badge"]:
        return lc["badge"], f"RATING {lc['rating']}{top}"
    return str(lc["rating"]), f"CONTEST RATING{top}"


def aria_label(lc: dict, username: str, activity: dict | None = None) -> str:
    past_year = (
        ""
        if activity is None
        else f", {activity['total']} submissions in the past year"
    )
    if lc["rating"] is None:
        return f"LeetCode {username}: no contests yet, {lc['solved']} solved{past_year}"
    badge = f"{lc['badge']}, " if lc["badge"] else ""
    top = "" if lc["top"] is None else f", top {lc['top']}%"
    return (
        f"LeetCode {username}: {badge}rating {lc['rating']}{top}, "
        f"{lc['contests']} contests, {lc['solved']} solved{past_year}"
    )


def chart_points(history: list[int]) -> list[tuple[float, float]]:
    """Map two or more ratings onto the chart box: oldest left, lowest at the bottom."""
    x0, x1, y0, y1 = CHART_BOX
    lo = min(history)
    span = max(max(history) - lo, 1)
    last = len(history) - 1
    return [
        (x0 + (x1 - x0) * i / last, y1 - (y1 - y0) * (r - lo) / span)
        for i, r in enumerate(history)
    ]


def render_chart(history: list[int], pal: dict) -> list[str]:
    """Gridlines, the rating line drawing itself in, the area under it, the peak."""
    x0, x1, y0, y1 = CHART_BOX
    accent = pal["accent"]
    lo, hi = min(history), max(history)
    span = max(hi - lo, 1)
    pts = chart_points(history)
    line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    length = sum(math.dist(a, b) for a, b in itertools.pairwise(pts))
    area = f"{line} L{x1} {y1} L{x0} {y1} Z"
    px, py = pts[history.index(hi)]
    lx, ly = pts[-1]
    label = f"PEAK {hi}"
    # The label ends just left of the peak, unless that runs off the card's left edge
    # (7.5 px a character: 10.5 px mono with the card's 1.2 px tracking)
    tx, anchor = (
        (px - 6, "end") if px - 6 - len(label) * 7.5 >= 12 else (px + 6, "start")
    )
    parts = []
    for frac in (0, 0.5, 1):
        y = y1 - (y1 - y0) * frac
        parts.append(
            f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{pal["grid"]}"/>'
            f'<text class="m" x="{x1 + 8}" y="{y + 3:.1f}" fill="{pal["axis"]}" font-size="10.5">{round(lo + span * frac)}</text>'
        )
    return [
        *parts,
        f'<path d="{area}" fill="url(#area)" opacity="0"><animate attributeName="opacity" to="1" begin="2.2s" dur="0.8s" fill="freeze"/></path>',
        (
            f'<path d="{line}" fill="none" stroke="{accent}" stroke-width="2" stroke-linejoin="round" stroke-dasharray="{length:.0f}" stroke-dashoffset="{length:.0f}">'
            f'<animate attributeName="stroke-dashoffset" from="{length:.0f}" to="0" dur="2.4s" begin="0.2s" fill="freeze"/></path>'
        ),
        (
            f'<circle class="ring" cx="{px:.1f}" cy="{py:.1f}" r="5" fill="none" stroke="{accent}" stroke-width="1.5" opacity="0">'
            '<set attributeName="opacity" to="1" begin="2.6s" fill="freeze"/></circle>'
        ),
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{accent}" opacity="0"><set attributeName="opacity" to="1" begin="2.6s" fill="freeze"/></circle>',
        (
            f'<text class="m" x="{tx:.1f}" y="{py - 12:.1f}" text-anchor="{anchor}" fill="{accent}" font-size="10.5" opacity="0">{label}'
            '<set attributeName="opacity" to="1" begin="2.6s" fill="freeze"/></text>'
        ),
    ]


def render_headline(x: int, y: int, lc: dict, pal: dict) -> list[str]:
    big, sub = headline(lc)
    parts = [
        f'<text class="v" x="{x}" y="{y}" fill="{pal["accent"]}" font-size="30">{escape(big)}</text>'
    ]
    if sub:
        parts.append(
            f'<text class="m" x="{x}" y="{y + 20}" fill="{pal["sub"]}" font-size="10.5">{escape(sub)}</text>'
        )
    return parts


def render_solved(x: int, y: int, lc: dict, pal: dict) -> list[str]:
    """Solved count with one animated progress bar per difficulty under it."""
    parts = [
        (
            f'<text class="v" x="{x}" y="{y}" fill="{pal["text"]}" font-size="22">{lc["solved"]:,}'
            f'<tspan class="m" font-size="10.5" fill="{pal["label"]}">  SOLVED</tspan></text>'
        )
    ]
    for j, (level, (done, total)) in enumerate(lc["by_difficulty"].items()):
        by = y + 22 + j * 22
        bar = 200 * (done / total if total else 0)
        color = pal["difficulty"][level]
        parts.append(
            f'<text class="m" x="{x}" y="{by}" fill="{color}" font-size="10.5">{level.upper()}</text>'
            f'<text class="m" x="{x + 200}" y="{by}" text-anchor="end" fill="{pal["label"]}" font-size="10.5">{done}/{total}</text>'
            f'<rect x="{x}" y="{by + 5}" width="200" height="5" rx="2.5" fill="{pal["track"]}"/>'
            f'<rect x="{x}" y="{by + 5}" width="{bar:.1f}" height="5" rx="2.5" fill="{color}" transform="scale(0 1)" style="transform-origin:{x}px 0">'
            f'<animateTransform attributeName="transform" type="scale" from="0 1" to="1 1" begin="{0.6 + j * 0.2:.1f}s" dur="0.9s" fill="freeze"/></rect>'
        )
    return parts


def activity(calendar: dict[dt.date, int], today: dt.date) -> dict:
    """The heatmap window ending today: its first day, a count per day, and the totals."""
    sunday_row = (today.weekday() + 1) % 7  # 0 for Sunday, the top row
    start = today - dt.timedelta(days=sunday_row + 7 * (HEATMAP_WEEKS - 1))
    counts = [
        calendar.get(start + dt.timedelta(days=d), 0)
        for d in range((today - start).days + 1)
    ]
    streak = best = 0
    for n in counts:
        streak = streak + 1 if n else 0
        best = max(best, streak)
    return {
        "start": start,
        "counts": counts,
        "total": sum(counts),
        "active": sum(1 for n in counts if n),
        "streak": best,
    }


def heat_level(count: int, peak: int) -> int:
    """1 to 4 on a log scale, so one busy day does not wash every other day out."""
    return max(1, min(4, math.ceil(4 * math.log(count + 1) / math.log(peak + 1))))


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}S"


def render_heatmap(act: dict, top: int, pal: dict) -> list[str]:
    """A year of daily submissions in GitHub's week-column layout, sweeping in left to right."""
    gy = top + 54
    counts = act["counts"]
    weeks = math.ceil(len(counts) / 7)
    last_rows = len(counts) - 7 * (weeks - 1)
    right = HEATMAP_X + HEATMAP_WEEKS * HEATMAP_PITCH - (HEATMAP_PITCH - HEATMAP_CELL)
    stats = f"{plural(act['active'], 'ACTIVE DAY')}  |  MAX STREAK {act['streak']:,}"
    parts = [
        f'<line x1="{HEATMAP_X}" y1="{top}" x2="{right}" y2="{top}" stroke="{pal["grid"]}"/>',
        f'<text class="m" x="{HEATMAP_X}" y="{top + 26}" fill="{pal["label"]}" font-size="10.5">{plural(act["total"], "SUBMISSION")} IN THE PAST YEAR</text>',
        f'<text class="m" x="{right}" y="{top + 26}" text-anchor="end" fill="{pal["label"]}" font-size="10.5">{stats}</text>',
    ]
    last_label = -3
    for week in range(weeks):
        days = (act["start"] + dt.timedelta(days=7 * week + d) for d in range(7))
        month_start = next((day for day in days if day.day == 1), None)
        if month_start and week - last_label >= 3:
            parts.append(
                f'<text class="m" x="{HEATMAP_X + week * HEATMAP_PITCH}" y="{top + 46}" fill="{pal["axis"]}" font-size="10.5">{MONTHS[month_start.month - 1]}</text>'
            )
            last_label = week
    # The empty grid is two pattern-filled rects, the full weeks and the current one, so
    # only active days cost markup
    tile = HEATMAP_PITCH * 7 - (HEATMAP_PITCH - HEATMAP_CELL)
    parts.append(
        f'<defs><pattern id="day" x="{HEATMAP_X}" y="{gy}" width="{HEATMAP_PITCH}" height="{HEATMAP_PITCH}" patternUnits="userSpaceOnUse">'
        f'<rect width="{HEATMAP_CELL}" height="{HEATMAP_CELL}" rx="2" fill="{pal["track"]}"/></pattern></defs>'
        f'<g opacity="0"><animate attributeName="opacity" to="1" begin="0.2s" dur="0.6s" fill="freeze"/>'
        f'<rect x="{HEATMAP_X}" y="{gy}" width="{(weeks - 1) * HEATMAP_PITCH}" height="{tile}" fill="url(#day)"/>'
        f'<rect x="{HEATMAP_X + (weeks - 1) * HEATMAP_PITCH}" y="{gy}" width="{HEATMAP_CELL}" height="{last_rows * HEATMAP_PITCH - (HEATMAP_PITCH - HEATMAP_CELL)}" fill="url(#day)"/></g>'
    )
    peak = max(counts, default=0)
    for week in range(weeks):
        cells = [
            f'<rect x="{HEATMAP_X + week * HEATMAP_PITCH}" y="{gy + row * HEATMAP_PITCH}" width="{HEATMAP_CELL}" height="{HEATMAP_CELL}" rx="2" class="l{heat_level(n, peak)}"/>'
            for row, n in enumerate(counts[7 * week : 7 * week + 7])
            if n
        ]
        if cells:
            parts.append(
                f'<g opacity="0"><animate attributeName="opacity" to="1" begin="{0.4 + week * 0.03:.2f}s" dur="0.4s" fill="freeze"/>'
                + "".join(cells)
                + "</g>"
            )
    return parts


def render_card(
    lc: dict,
    username: str,
    title: str = DEFAULT_TITLE,
    accent: str | None = None,
    theme: str = DEFAULT_THEME,
    today: dt.date | None = None,
) -> str:
    """Return the card SVG. A line needs two rated contests; below that the chart is left out.

    accent defaults to the theme's; one too dark (or, on a light theme, too light) to read on
    the card is shifted to the nearest shade that is. A profile fetched with its calendar gets
    the heatmap for the year ending today (UTC unless given).
    """
    pal = palette(theme, accent)
    chart = len(lc["history"]) >= 2
    h = 270 if chart else 188
    act = None
    if "calendar" in lc:
        act = activity(lc["calendar"], today or dt.datetime.now(dt.UTC).date())
        heat_top = h - 24
        h = heat_top + HEATMAP_HEIGHT
    heading = title.replace("{contests}", str(lc["contests"]))
    levels = "".join(
        f".l{n}{{fill:{color}}}" for n, color in enumerate(pal["heat"], start=1)
    )
    parts = [
        svg_open(W, h, aria_label(lc, username, act)),
        (
            f"<style>.m{{font-family:{MONO};font-weight:700;letter-spacing:1.2px}}.v{{font-family:{SANS};font-weight:800}}"
            # the pulse waits for the SMIL set that reveals the ring at 2.6s; a CSS animation
            # outranks the opacity attribute, so without the delay it pulses before the line arrives
            ".ring{animation:ring 2.2s ease-out 2.6s infinite;transform-origin:center;transform-box:fill-box}"
            f"@keyframes ring{{0%{{opacity:0.9;transform:scale(1)}}100%{{opacity:0;transform:scale(2.8)}}}}{levels if act else ''}</style>"
        ),
        (
            f'<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{pal["accent"]}" stop-opacity="0.28"/>'
            f'<stop offset="1" stop-color="{pal["accent"]}" stop-opacity="0"/></linearGradient></defs>'
        ),
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{h - 1}" rx="14" fill="{pal["bg"]}" stroke="{pal["border"]}"/>',
        f'<text class="m" x="24" y="32" fill="{pal["accent"]}" font-size="10.5">{escape(heading)}</text>',
    ]
    if chart:
        parts += render_chart(lc["history"], pal)
        parts += render_headline(PANEL_X, 84, lc, pal)
        parts += render_solved(PANEL_X, 146, lc, pal)
    else:
        parts += render_headline(24, 84, lc, pal)
        parts += render_solved(PANEL_X, 84, lc, pal)
    if act:
        parts += render_heatmap(act, heat_top, pal)
    parts.append(SVG_CLOSE)
    return "".join(parts)


# ---------------------------------------------------------------- flat style and phone layout
# The new look of the profile README this card comes from (Sagargupta16/Sagargupta16: its
# scripts/kit.py and the leetcode-mobile card in scripts/cards/stats.py). Panels are flat, one
# fill and one hairline, with no gradient or glow; labels are mono micro-labels and figures
# sans numerals; every loop lasts 2, 3, 4, 6, 12 or 24 s. Entrances are poster-safe: each
# element's own attributes are its finished frame, and its animation holds the start value
# from 0 s until its turn, so a still render (a link preview, a viewer without SMIL) shows
# the whole card and a browser still plays the entrance.
MICRO = 10.5  # the smallest label on the 840 px card
MICRO_PHONE = 11.5  # the smallest label on the 320 px card, shown at about 309 px
TRACK = 1.2  # letter-spacing of a mono label
PAD = 24
PHONE_W = 320
PHONE_PAD = 18
PHONE_COLUMN = PHONE_W - 2 * PHONE_PAD
LOOPS = (2, 3, 4, 6, 12, 24)  # the only lengths a repeating animation has, in seconds
CLOCK = 12  # the loop the heatmap's scan runs on
ENTER = 0.4
STAGGER = 0.08
EASE = "0.16 1 0.3 1"  # ease-out for entrances
DOT = chr(0xB7)  # the middle dot two facts are joined with
MISSING = "-"
FLAT_CSS = (
    f".m{{font-family:{MONO};font-weight:700;letter-spacing:{TRACK}px}}"
    f".c{{font-family:{MONO};font-weight:500}}"
    f".n{{font-family:{SANS};font-weight:800;font-variant-numeric:tabular-nums}}"
    f".b{{font-family:{SANS};font-weight:500}}"
)
# The 840 px card: a row of four tiles, then the rating panel beside the solved panel
TILES_TOP = 46
PANEL_H = 168
CHART_PANEL_W = 520
GAP = 12


def on_every(color: str, surfaces: tuple[str, ...]) -> str:
    """color raised by readable() until text in it reaches MIN_CONTRAST on each surface.

    The surfaces of one theme are all dark or all light, so raising for one never lowers
    the contrast on another.
    """
    for surface in surfaces:
        color = readable(color, surface)
    return color


def muted_on(
    ink: str, alpha: float, surfaces: tuple[str, ...], ratio: float = MIN_CONTRAST
) -> str:
    """The ink (an r,g,b triple) at alpha, raised in 0.01 steps until it reaches ratio on every surface."""
    for a in (round(alpha + i / 100, 2) for i in range(101)):
        color = f"rgba({ink},{a:g})"
        if a >= 1 or all(contrast(color, s) >= ratio for s in surfaces):
            return color
    raise AssertionError("unreachable: alpha 1 always returns")


def flat_palette(theme: str = DEFAULT_THEME, accent: str | None = None) -> dict:
    """Every color the flat card paints, derived from the theme's four colors.

    Hairlines, tracks and labels are the theme's ink at the profile kit's alphas; a tile is the
    ink at 3% over the card, and the lead tile is the accent at 10%. Text colors are raised
    until they reach MIN_CONTRAST on the card, a tile and the lead tile. The light that runs
    the rating line is the accent halfway to the text color, so it shows on the line in
    every theme.
    """
    t = THEMES[theme]
    bg, ink = t["bg"], t["ink"]
    tile = blend(f"rgba({ink},1)", bg, 0.03)
    lit = blend(readable(accent or t["accent"], bg), bg, 0.10)
    surfaces = (bg, tile, lit)
    color = on_every(accent or t["accent"], surfaces)
    text = on_every(t["text"], surfaces)
    r, g, b, _ = parse_color(color)
    return {
        "bg": bg,
        "tile": tile,
        "lit": lit,
        # the lead tile's outline: the kit's 0.55, or what reaches 3:1 (WCAG 1.4.11)
        "lit_edge": muted_on(f"{r:g},{g:g},{b:g}", 0.55, (bg, lit), 3),
        "frame": f"rgba({ink},0.09)",
        "edge": f"rgba({ink},0.14)",
        "accent": color,
        "text": text,
        "body": muted_on(ink, 0.78, surfaces),
        "meta": muted_on(ink, 0.62, surfaces),
        "light": blend(text, color, 0.5),
        "heat": heat_colors(color, bg),
    }


def num(value: float) -> str:
    """A coordinate to two places at most, with no trailing zeros and never "-0"."""
    out = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if out in ("-0", "") else out


def _advance(character: str) -> float:
    """A sans glyph's advance in ems, measured conservatively (the profile kit's table)."""
    if unicodedata.combining(character):
        return 0
    if unicodedata.east_asian_width(character) in {"W", "F"}:
        return 1.05
    if character in "W@%M":
        return 1
    if character in "ilI.,:;'!|`":
        return 0.34
    if character in " fjrt()[]":
        return 0.44
    return 0.7 if character.isupper() else 0.58


def text_width(content: str, size: float, mono: bool = False) -> float:
    """The width text takes: sans glyph advances, or monospace plus the label tracking."""
    if mono:
        return len(content) * (size * 0.6 + TRACK)
    return sum(_advance(character) for character in content) * size


def wrap(content: str, room: float, size: float, mono: bool = False) -> list[str]:
    """Wrap words to a pixel width; a word wider than the line keeps a line of its own."""
    lines, current = [], ""
    for word in content.split():
        candidate = f"{current} {word}" if current else word
        if current and text_width(candidate, size, mono) > room:
            lines.append(current)
            candidate = word
        current = candidate
    return [*lines, current] if current else lines


def _text(
    x: float,
    y: float,
    content: object,
    size: float,
    fill: str,
    cls: str = "m",
    anchor: str = "",
) -> str:
    align = f' text-anchor="{anchor}"' if anchor else ""
    return (
        f'<text class="{cls}" x="{num(x)}" y="{num(y)}" font-size="{size:g}" fill="{fill}"{align}>'
        f"{escape(str(content))}</text>"
    )


def _box(
    x: float, y: float, w: float, h: float, fill: str, stroke: str = "", r: float = 10
) -> str:
    edge = f' stroke="{stroke}"' if stroke else ""
    return (
        f'<rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" rx="{num(r)}" '
        f'fill="{fill}"{edge}/>'
    )


def held(begin: float, dur: float) -> str:
    """Timing that runs from 0 s and holds the start value until begin, then eases out."""
    total = begin + dur
    return (
        f'keyTimes="0;{begin / total:.3f};1" dur="{total:.2f}s" fill="freeze" '
        f'calcMode="spline" keySplines="0 0 1 1;{EASE}"'
    )


def enter(at: float, dur: float = ENTER, shift: str = "") -> str:
    """A poster-safe entrance for the element it sits in: fade in, and rise from shift if given."""
    times = held(at, dur)
    out = f'<animate attributeName="opacity" values="0;0;1" {times}/>'
    if shift:
        out += f'<animateTransform attributeName="transform" type="translate" values="{shift};{shift};0 0" {times}/>'
    return out


def group(at: float, body: str, shift: str = "0 8") -> str:
    """Wrap a block so it fades in and rises 8 px at `at`."""
    return f"<g>{enter(at, shift=shift)}{body}</g>"


def draw(d: str, at: float, dur: float, color: str, width: float) -> str:
    """Draw a path in once; with pathLength 1 the dash is its full length, and it rests drawn."""
    return (
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width:g}" stroke-linejoin="round" '
        f'stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="0">'
        f'<animate attributeName="stroke-dashoffset" values="1;1;0" {held(at, dur)}/></path>'
    )


def light(
    d: str,
    length: float,
    color: str,
    begin: float = 2,
    travel: float = 0.5,
    width: float = 3,
    dash: float = 8,
    dur: float = 6,
) -> str:
    """A short light that runs path d (`length` px long) once a loop from `begin`, then rests hidden.

    It parks a cap's width past either end, so a round cap never leaves a dot at rest.
    `dash` is the light's share of the path in hundredths.
    """
    margin = 100 * (width / 2 + 1) / max(length, 1)
    rest, gone = dash + margin, -(100 + margin)
    return (
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width:g}" stroke-linecap="round" '
        f'pathLength="100" stroke-dasharray="{dash:g} {100 + dash + 2 * margin:.1f}" stroke-dashoffset="{rest:.1f}">'
        f'<animate attributeName="stroke-dashoffset" values="{rest:.1f};{gone:.1f};{gone:.1f}" '
        f'keyTimes="0;{travel:g};1" dur="{dur:g}s" begin="{begin:g}s" repeatCount="indefinite"/></path>'
    )


def live_dot(cx: float, cy: float, color: str, r: float = 3) -> str:
    """A status point: a ring that widens and fades every 2 s around a steady dot."""
    return (
        f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="none" stroke="{color}" stroke-width="1.5">'
        f'<animate attributeName="r" values="{r:g};{r + 7:g}" dur="2s" repeatCount="indefinite"/>'
        '<animate attributeName="opacity" values="0.9;0" dur="2s" repeatCount="indefinite"/></circle>'
        f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{color}"/>'
    )


def rounded_rect_path(x: float, y: float, w: float, h: float, r: float) -> str:
    """A rounded rectangle's outline as a path, for an outline that moves or scales."""
    return (
        f"M{num(x + r)} {num(y)}H{num(x + w - r)}A{num(r)} {num(r)} 0 0 1 {num(x + w)} {num(y + r)}"
        f"V{num(y + h - r)}A{num(r)} {num(r)} 0 0 1 {num(x + w - r)} {num(y + h)}H{num(x + r)}"
        f"A{num(r)} {num(r)} 0 0 1 {num(x)} {num(y + h - r)}V{num(y + r)}A{num(r)} {num(r)} 0 0 1 {num(x + r)} {num(y)}Z"
    )


def starts(count: int) -> list[float]:
    """Entrance times for blocks in reading order: STAGGER apart from 0.1 s, all begun by 1.2 s."""
    return [round(min(0.1 + index * STAGGER, 1.2), 2) for index in range(count)]


def tile_figures(lc: dict) -> list[tuple[str, str]]:
    """(value, label) for the four tiles, the lead figure first."""
    rating, top = lc["rating"], lc["top"]
    return [
        (MISSING if rating is None else f"{rating:,}", "Contest rating"),
        (MISSING if top is None else f"{top}%", "Top worldwide"),
        (f"{lc['solved']:,}", "Problems solved"),
        (f"{lc['contests']:,}", "Contests"),
    ]


def render_tiles(
    x: float,
    y: float,
    width: float,
    columns: int,
    lc: dict,
    pal: dict,
    at: list[float],
    phone: bool,
) -> tuple[str, float]:
    """The stat tiles, `columns` to a row: a numeral over a mono label that wraps by whole words.

    The lead tile is tinted in the accent. Tiles hang from the top, so a row is as tall as
    its tallest label. Returns (svg, the y under the last row).
    """
    items = tile_figures(lc)
    gap = 10 if phone else GAP
    tw = (width - gap * (columns - 1)) / columns
    micro = MICRO_PHONE if phone else MICRO
    inset, size = (12, 22) if phone else (14, 26)
    value_y, label_y, pitch, foot = (30, 49, 14, 13) if phone else (38, 58, 13, 16)
    labels = [
        wrap(label.upper(), tw - 2 * inset + TRACK, micro, True) for _, label in items
    ]
    out = []
    for row in range(0, len(items), columns):
        cells = range(row, min(row + columns, len(items)))
        th = max(label_y + (len(labels[i]) - 1) * pitch + foot for i in cells)
        for i in cells:
            tx = x + (i - row) * (tw + gap)
            value = items[i][0]
            fit = (
                size  # a long figure steps the numeral down rather than leave its tile
            )
            while fit > 16 and text_width(value, fit) > tw - 2 * inset:
                fit -= 1
            fill, stroke = (
                (pal["lit"], pal["lit_edge"]) if i == 0 else (pal["tile"], pal["edge"])
            )
            body = _box(tx, y, tw, th, fill, stroke) + _text(
                tx + inset, y + value_y, value, fit, pal["text"], "n"
            )
            body += "".join(
                _text(tx + inset, y + label_y + k * pitch, line, micro, pal["meta"])
                for k, line in enumerate(labels[i])
            )
            out.append(group(at[i], body))
        y += th + gap
    return "".join(out), y - gap


def render_difficulty(
    x: float,
    first: float,
    width: float,
    pitch: float,
    lc: dict,
    pal: dict,
    at: float,
    phone: bool,
) -> tuple[str, float]:
    """Easy, Medium and Hard: a mono label and the count over a bar that grows from its left end.

    At rest each bar is its full length. Returns (svg, the y under the last bar).
    """
    micro = MICRO_PHONE if phone else MICRO
    rows, y = [], first
    for level, (done, total) in lc["by_difficulty"].items():
        fill = width * min(done / total, 1) if total else 0
        rows.append(
            _text(x, y, level.upper(), micro, pal["accent"])
            + _text(
                x + width,
                y,
                f"{done:,} / {total:,}",
                12.5 if phone else 12,
                pal["body"],
                "c",
                "end",
            )
            + _box(x, y + 8, width, 6, pal["edge"], r=3)
            + f'<g transform="translate({num(x)} {num(y + 8)})"><rect width="{fill:.1f}" height="6" rx="3" fill="{pal["accent"]}">'
            + '<animateTransform attributeName="transform" type="scale" values="0 1;0 1;1 1" '
            + f"{held(at + 0.2, 0.9)}/></rect></g>"
        )
        y += pitch
    return group(at, "".join(rows)), y - pitch + 14


def render_rating_line(
    history: list[int],
    box: tuple[float, float, float, float],
    label_x: float,
    pal: dict,
    at: float,
    phone: bool,
) -> str:
    """The contest rating line between gridlines at its high and low, drawn in once.

    A light runs the line in 3 s of every 6 from 2 s. On a phone the latest point pulses
    every 2 s, as on the profile's phone card; the 840 px card marks it with a steady dot
    and rings the peak when the peak is an earlier contest.
    """
    left, right, upper, lower = box
    low, high = min(history), max(history)
    micro = MICRO_PHONE if phone else MICRO
    out = []
    for value, y in ((high, upper), (low, lower)):
        out.append(_text(label_x, y + 4, round(value), micro, pal["meta"], "c"))
        out.append(
            f'<path d="M{num(left)} {num(y)}H{num(right)}" stroke="{pal["edge"]}"/>'
        )
    last = len(history) - 1
    points = [
        (
            left + index * (right - left) / last,
            lower - (value - low) / max(high - low, 1) * (lower - upper),
        )
        for index, value in enumerate(history)
    ]
    path = "".join(
        f"{'M' if index == 0 else 'L'}{x:.1f} {y:.1f}"
        for index, (x, y) in enumerate(points)
    )
    out.append(draw(path, at, 0.9, pal["accent"], 2))
    length = sum(math.dist(a, b) for a, b in itertools.pairwise(points))
    out.append(light(path, length, pal["light"]))
    x, y = (round(v, 1) for v in points[-1])
    if phone:
        mark = live_dot(x, y, pal["accent"])
    else:
        mark = f'<circle cx="{x:g}" cy="{y:g}" r="3.5" fill="{pal["accent"]}"/>'
        peak = history.index(high)
        if peak != last:
            px, py = (round(v, 1) for v in points[peak])
            mark += (
                f'<circle cx="{px:g}" cy="{py:g}" r="4" fill="none" '
                f'stroke="{pal["accent"]}" stroke-width="1.5"/>'
            )
    out.append(f"<g>{enter(at + 0.9, 0.3)}{mark}</g>")
    axis_y = lower + 20 if not phone else lower + 22
    out.append(_text(left, axis_y, "CONTEST 1", micro, pal["meta"]))
    out.append(
        _text(right, axis_y, f"CONTEST {last + 1:,}", micro, pal["meta"], anchor="end")
    )
    return "".join(out)


def climb(history: list[int]) -> str:
    """The change from the first rated contest to the latest, which the tiles do not say."""
    return f"{round(history[-1] - history[0]):+,} SINCE FIRST"


def heat_weeks(act: dict, shown: int) -> list[list[int]]:
    """The last `shown` week columns of the window, oldest first; the last one ends today."""
    counts = act["counts"]
    weeks = math.ceil(len(counts) / 7)
    return [counts[7 * w : 7 * w + 7] for w in range(max(0, weeks - shown), weeks)]


def render_flat_heatmap(
    act: dict,
    shown: int,
    x: float,
    top: float,
    pitch: float,
    cell: float,
    pal: dict,
    at: float,
) -> tuple[str, str, float]:
    """Daily submissions, a week to a column with Sunday on top: (defs, svg, height).

    One clip that slides in reveals the grid left to right, so the grid is one animated
    element and rests whole. Then a scan rests on this week and steps across the window
    from the oldest week on the 12 s clock, and a ripple marks the busiest day every 2 s.
    Shades step on the same log scale as the classic heatmap, over the whole year.
    """
    weeks = heat_weeks(act, shown)
    peak = max(act["counts"], default=0)
    height = 6 * pitch + cell
    wide = (len(weeks) - 1) * pitch + cell
    last = len(weeks) - 1
    defs = (
        f'<pattern id="day" x="{num(x)}" y="{num(top)}" width="{pitch:g}" height="{pitch:g}" patternUnits="userSpaceOnUse">'
        f'<rect width="{cell:g}" height="{cell:g}" rx="2" fill="{pal["edge"]}"/></pattern>'
        f'<clipPath id="weeks"><rect x="{num(x)}" y="{num(top)}" width="{num(wide)}" height="{num(height)}">'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="-{num(wide)} 0;-{num(wide)} 0;0 0" {held(at, 0.9)}/></rect></clipPath>'
    )
    cells = [
        f'<rect x="{num(x)}" y="{num(top)}" width="{num(last * pitch)}" height="{num(height)}" fill="url(#day)"/>',
        f'<rect x="{num(x + last * pitch)}" y="{num(top)}" width="{cell:g}" height="{num((len(weeks[-1]) - 1) * pitch + cell)}" fill="url(#day)"/>',
    ]
    for column, week in enumerate(weeks):
        cells += [
            f'<rect x="{num(x + column * pitch)}" y="{num(top + row * pitch)}" width="{cell:g}" '
            f'height="{cell:g}" rx="2" class="l{heat_level(n, peak)}"/>'
            for row, n in enumerate(week)
            if n
        ]
    svg = f'<g clip-path="url(#weeks)">{"".join(cells)}</g>'
    motion = ""
    if last > 0:
        # rests on this week, sweeps from the oldest at 2.4 s, one week a step, home by 11 s
        step = min(0.45, 8.6 / last)
        points = [(0.0, "0 0")] + [
            (2.4 + column * step, f"{num((column - last) * pitch)} 0")
            for column in range(last + 1)
        ]
        values = ";".join(value for _, value in points)
        times = ";".join(f"{round(second / CLOCK, 4):g}" for second, _ in points)
        outline = rounded_rect_path(
            x + last * pitch - 2.5, top - 2.5, cell + 5, height + 5, 4
        )
        motion += (
            f'<path d="{outline}" fill="none" stroke="{pal["accent"]}" stroke-width="1.5">'
            f'<animateTransform attributeName="transform" type="translate" values="{values}" '
            f'keyTimes="{times}" calcMode="discrete" dur="{CLOCK}s" repeatCount="indefinite"/></path>'
        )
    busy = [
        (n, column, row)
        for column, week in enumerate(weeks)
        for row, n in enumerate(week)
        if n
    ]
    if busy:
        # the busiest day in the window: the latest one when two tie
        _, column, row = max(busy)
        cx, cy = x + column * pitch + cell / 2, top + row * pitch + cell / 2
        half = cell / 2 + 1.5
        ring = rounded_rect_path(-half, -half, 2 * half, 2 * half, 3)
        motion += (
            f'<g transform="translate({num(cx)} {num(cy)})"><path d="{ring}" fill="none" '
            f'stroke="{pal["heat"][-1]}" stroke-width="1.5">'
            '<animateTransform attributeName="transform" type="scale" values="1;1.9" dur="2s" repeatCount="indefinite"/>'
            '<animate attributeName="opacity" values="0.9;0" dur="2s" repeatCount="indefinite"/></path></g>'
        )
    if motion:
        svg += group(at + 0.9, motion, "")
    return defs, svg, height


def flat_card(w: int, h: float, label: str, pal: dict, defs: str, body: str) -> str:
    """The svg root, the classes, the defs and the flat surface around the body."""
    levels = ""
    if 'class="l' in body:  # heatmap cells
        levels = "".join(
            f".l{n}{{fill:{color}}}" for n, color in enumerate(pal["heat"], start=1)
        )
    h = math.ceil(h)
    return (
        svg_open(w, h, label)
        + f"<style>{FLAT_CSS}{levels}</style>"
        + (f"<defs>{defs}</defs>" if defs else "")
        + f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="{pal["bg"]}" stroke="{pal["frame"]}"/>'
        + body
        + SVG_CLOSE
    )


def render_flat_card(
    lc: dict,
    username: str,
    title: str = DEFAULT_TITLE,
    accent: str | None = None,
    theme: str = DEFAULT_THEME,
    today: dt.date | None = None,
) -> str:
    """The card in the flat style, 840 px wide.

    The title opens the card with the badge as a chip beside it; four tiles carry the
    rating, the top percentage, the solved count and the contests; the rating line and the
    solved bars sit on panels under them, and a profile fetched with its calendar adds the
    year's heatmap. With fewer than two rated contests the solved panel takes the full width.
    """
    pal = flat_palette(theme, accent)
    act = None
    if "calendar" in lc:
        act = activity(lc["calendar"], today or dt.datetime.now(dt.UTC).date())
    at = starts(8)
    heading = title.replace("{contests}", str(lc["contests"]))
    parts = [_text(PAD, 30, heading, MICRO, pal["accent"])]
    if lc["badge"]:
        badge = lc["badge"].upper()
        chip_w = text_width(badge, MICRO, True) + 20 - TRACK
        chip_x = W - PAD - chip_w
        # a 22 px pill whose label sits on the title's baseline
        chip_y = 30 - 11 - MICRO * 0.36
        parts.append(
            _box(chip_x, chip_y, chip_w, 22, pal["lit"], pal["lit_edge"], 11)
            + _text(
                chip_x + chip_w / 2,
                30,
                badge,
                MICRO,
                pal["accent"],
                anchor="middle",
            )
        )
    tiles, y = render_tiles(PAD, TILES_TOP, W - 2 * PAD, 4, lc, pal, at, False)
    parts.append(tiles)
    y += GAP
    history = lc["history"]
    solved_x, solved_w = PAD, W - 2 * PAD
    if len(history) >= 2:
        right = PAD + CHART_PANEL_W - 16
        header = _text(
            PAD + 16, y + 28, "CONTEST RATING", MICRO, pal["accent"]
        ) + _text(
            right,
            y + 28,
            f"PEAK {max(history):,}  |  {climb(history)}",
            MICRO,
            pal["meta"],
            anchor="end",
        )
        box = (PAD + 56, right, y + 52, y + 132)
        parts.append(
            group(
                at[4],
                _box(PAD, y, CHART_PANEL_W, PANEL_H, pal["tile"], pal["edge"])
                + header
                + render_rating_line(history, box, PAD + 16, pal, at[4] + 0.2, False),
            )
        )
        solved_x = PAD + CHART_PANEL_W + GAP
        solved_w = W - PAD - solved_x
    bars, _ = render_difficulty(
        solved_x + 16, y + 62, solved_w - 32, 36, lc, pal, at[5], False
    )
    parts.append(
        group(
            at[5],
            _box(solved_x, y, solved_w, PANEL_H, pal["tile"], pal["edge"])
            + _text(
                solved_x + 16, y + 28, "SOLVED BY DIFFICULTY", MICRO, pal["accent"]
            ),
        )
        + bars
    )
    y += PANEL_H
    defs = ""
    if act:
        y += 34
        right = (
            HEATMAP_X + HEATMAP_WEEKS * HEATMAP_PITCH - (HEATMAP_PITCH - HEATMAP_CELL)
        )
        stats = (
            f"{plural(act['active'], 'ACTIVE DAY')}  |  MAX STREAK {act['streak']:,}"
        )
        labels = [
            _text(
                HEATMAP_X,
                y,
                f"{plural(act['total'], 'SUBMISSION')} IN THE PAST YEAR",
                MICRO,
                pal["accent"],
            ),
            _text(right, y, stats, MICRO, pal["meta"], anchor="end"),
        ]
        weeks = heat_weeks(act, HEATMAP_WEEKS)
        last_label = -3
        for week in range(len(weeks)):
            days = (act["start"] + dt.timedelta(days=7 * week + d) for d in range(7))
            month_start = next((day for day in days if day.day == 1), None)
            if month_start and week - last_label >= 3:
                labels.append(
                    _text(
                        HEATMAP_X + week * HEATMAP_PITCH,
                        y + 20,
                        MONTHS[month_start.month - 1],
                        MICRO,
                        pal["meta"],
                    )
                )
                last_label = week
        heat_defs, heat, height = render_flat_heatmap(
            act,
            HEATMAP_WEEKS,
            HEATMAP_X,
            y + 30,
            HEATMAP_PITCH,
            HEATMAP_CELL,
            pal,
            at[6] + 0.1,
        )
        defs += heat_defs
        parts.append(group(at[6], "".join(labels)) + heat)
        y += 30 + height
    return flat_card(
        W, y + PAD, aria_label(lc, username, act), pal, defs, "".join(parts)
    )


def render_phone_card(
    lc: dict,
    username: str,
    accent: str | None = None,
    theme: str = DEFAULT_THEME,
    today: dt.date | None = None,
) -> str:
    """The 320 px phone card, a port of the profile README's leetcode-mobile card.

    The badge opens it; four tiles sit two to a row, then the solved bars, the rating line
    and, for a profile fetched with its calendar, the last 20 weeks of the heatmap with the
    year's totals. It is always drawn in the flat style, and the title input is not used,
    because the 840 px title does not fit a phone's width.
    """
    pal = flat_palette(theme, accent)
    act = None
    if "calendar" in lc:
        act = activity(lc["calendar"], today or dt.datetime.now(dt.UTC).date())
    at = starts(8)
    badge = lc["badge"]
    eyebrow = "LEETCODE" + (f"  |  {badge.upper()}" if badge else "")
    parts = [_text(PHONE_PAD, 30, eyebrow, MICRO_PHONE, pal["accent"])]
    tiles, y = render_tiles(PHONE_PAD, 44, PHONE_COLUMN, 2, lc, pal, at, True)
    parts.append(tiles)
    bars, y = render_difficulty(
        PHONE_PAD, y + 26, PHONE_COLUMN, 38, lc, pal, at[4], True
    )
    parts.append(bars)
    y -= 2  # the profile card steps on from 12 px under the last label
    history = lc["history"]
    if len(history) >= 2:
        y += 34
        top = y + 8
        box = (PHONE_PAD + 40, PHONE_W - PHONE_PAD - 6, top + 8, top + 104)
        parts.append(
            group(
                at[5],
                _text(PHONE_PAD, y, "CONTEST RATING", MICRO_PHONE, pal["accent"])
                + _text(
                    PHONE_W - PHONE_PAD,
                    y,
                    climb(history),
                    MICRO_PHONE,
                    pal["meta"],
                    anchor="end",
                )
                + render_rating_line(history, box, PHONE_PAD, pal, at[5] + 0.2, True),
            )
        )
        y = top + 126
    defs = ""
    if act:
        y += 30
        weeks = heat_weeks(act, 20)
        parts.append(
            group(
                at[6],
                _text(
                    PHONE_PAD, y, f"LAST {len(weeks)} WEEKS", MICRO_PHONE, pal["accent"]
                )
                + _text(
                    PHONE_W - PHONE_PAD,
                    y,
                    "THIS WEEK",
                    MICRO_PHONE,
                    pal["meta"],
                    anchor="end",
                ),
            )
        )
        heat_defs, heat, height = render_flat_heatmap(
            act, 20, PHONE_PAD, y + 12, 14, 11, pal, at[6] + 0.1
        )
        defs += heat_defs
        parts.append(heat)
        y += 12 + height
        # one fact group a line, each wrapped only if a large count needs it
        facts = [
            f"{plural(act['total'], 'SUBMISSION').lower()} in the past year",
            f"{plural(act['active'], 'ACTIVE DAY').lower()} {DOT} longest streak {act['streak']:,}",
        ]
        lines = [part for fact in facts for part in wrap(fact, PHONE_COLUMN, 13.5)]
        y += 10
        parts.append(
            group(
                at[7],
                "".join(
                    _text(PHONE_PAD, y + 18 * (k + 1), text, 13.5, pal["body"], "b")
                    for k, text in enumerate(lines)
                ),
            )
        )
        y += 18 * len(lines)
    return flat_card(
        PHONE_W, y + PHONE_PAD, aria_label(lc, username, act), pal, defs, "".join(parts)
    )


def render(
    lc: dict,
    username: str,
    title: str = DEFAULT_TITLE,
    accent: str | None = None,
    theme: str = DEFAULT_THEME,
    today: dt.date | None = None,
    style: str = DEFAULT_STYLE,
    layout: str = DEFAULT_LAYOUT,
) -> str:
    """The card for one output: render_card for classic, the flat card or the phone card."""
    if layout == "phone":
        return render_phone_card(lc, username, accent, theme, today)
    if style == "flat":
        return render_flat_card(lc, username, title, accent, theme, today)
    return render_card(lc, username, title, accent, theme, today)


def parse_output_options(
    raw: str,
    default_theme: str,
    default_style: str = DEFAULT_STYLE,
    default_layout: str = DEFAULT_LAYOUT,
) -> list[tuple[Path, dict[str, str]]]:
    """One (path, {theme, style, layout}) per non-empty line.

    A line may end in ?key=value, several joined with &, to give that card its own theme,
    style or layout; a line without one takes the defaults.
    """
    choices = {"theme": THEMES, "style": STYLES, "layout": LAYOUTS}
    outputs = []
    for line in raw.splitlines():
        path, _, query = line.strip().partition("?")
        path = path.rstrip()
        if not path:
            continue
        options = {
            "theme": default_theme,
            "style": default_style,
            "layout": default_layout,
        }
        for pair in query.split("&") if query else ():
            key, _, value = pair.strip().partition("=")
            if key not in options:
                raise ValueError(
                    f"unknown option {key!r} in output {line.strip()!r}, pick theme=, style= or layout="
                )
            options[key] = value
        for key, allowed in choices.items():
            if options[key] not in allowed:
                raise ValueError(
                    f"unknown {key} {options[key]!r}, pick one of {', '.join(allowed)}"
                )
        if options["layout"] == "phone":
            options["style"] = "flat"  # there is no classic phone card
        outputs.append((Path(path), options))
    if not outputs:
        raise ValueError("output is empty: give at least one path")
    return outputs


def parse_outputs(raw: str, default_theme: str) -> list[tuple[Path, str]]:
    """One (path, theme) per non-empty line; a line may end in ?theme=<name> to override the theme.

    parse_output_options reads the style and layout options as well.
    """
    return [
        (path, options["theme"])
        for path, options in parse_output_options(raw, default_theme)
    ]


def annotate(level: str, message: str) -> None:
    """Print a GitHub Actions ::warning:: or ::error:: line, escaped like the runner expects."""
    message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{level}::{message}")


def set_outputs(lc: dict) -> None:
    """Append the step outputs to $GITHUB_OUTPUT when running inside Actions."""
    values = {
        "rating": "" if lc["rating"] is None else lc["rating"],
        "badge": lc["badge"],
        "solved": lc["solved"],
        "contests": lc["contests"],
    }
    print(" ".join(f"{name}={value}" for name, value in values.items()))
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as fh:
        # one line per output, so a newline in API data cannot start a new key
        fh.writelines(
            f"{name}={' '.join(str(value).splitlines())}\n"
            for name, value in values.items()
        )


def main() -> int:
    username = os.environ.get("LEETCODE_USERNAME", "").strip()
    accent = (os.environ.get("LEETCODE_ACCENT") or "").strip()
    title = os.environ.get("LEETCODE_TITLE") or DEFAULT_TITLE
    theme = (os.environ.get("LEETCODE_THEME") or DEFAULT_THEME).strip()
    heatmap = (os.environ.get("LEETCODE_HEATMAP") or "false").strip().lower()
    style = (os.environ.get("LEETCODE_STYLE") or DEFAULT_STYLE).strip()
    layout = (os.environ.get("LEETCODE_LAYOUT") or DEFAULT_LAYOUT).strip()
    if not username:
        annotate(
            "error",
            "username is required: set the username input (LEETCODE_USERNAME when run by hand)",
        )
        return 1
    if accent and not HEX_COLOR.fullmatch(accent):
        annotate("error", f"accent must be a hex color such as #f59e0b, got {accent!r}")
        return 1
    if heatmap not in {"true", "false"}:
        annotate("error", f"heatmap must be true or false, got {heatmap!r}")
        return 1
    try:
        outputs = parse_output_options(
            os.environ.get("LEETCODE_OUTPUT") or DEFAULT_OUTPUT, theme, style, layout
        )
    except ValueError as exc:
        annotate("error", str(exc))
        return 1
    try:
        lc = fetch_profile(username, heatmap=heatmap == "true")
    except FETCH_ERRORS as exc:
        reason = f"{type(exc).__name__}: {exc}"
        missing = [str(path) for path, _ in outputs if not path.is_file()]
        if not missing:
            kept = ", ".join(str(path) for path, _ in outputs)
            annotate(
                "warning",
                f"LeetCode fetch failed, keeping the existing {kept}. {reason}",
            )
            return 0
        annotate(
            "error",
            f"LeetCode fetch failed and there is no {', '.join(missing)} to keep. {reason}",
        )
        return 1
    today = dt.datetime.now(dt.UTC).date()
    for path, options in outputs:
        svg = render(lc, username, title, accent or None, today=today, **options)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8", newline="\n")
        shown = ", ".join(f"{key} {value}" for key, value in options.items())
        print(f"wrote {path} ({len(svg):,} bytes, {shown})")
    set_outputs(lc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
