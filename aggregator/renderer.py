"""
PNG renderer for TRMNL X (1872×1404, e-ink).
Uses Pillow only — no browser required, ARM64 native.

E-ink design principles:
- Pure black on white only (binary display)
- Large fonts — viewed from several feet away
- Bold weights for maximum contrast
- No gray text (threshold converts gray to white = invisible)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# TRMNL X native resolution
WIDTH  = 1872
HEIGHT = 1404
BG     = 255   # white
FG     = 0     # pure black
DARK   = 64    # dark gray — renders black after 1-bit conversion

HEADER_H    = 120
FOOTER_H    = 50
CONTENT_Y   = HEADER_H + 10
CONTENT_MAX_Y = HEIGHT - FOOTER_H - 10


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    bold_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    regular_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    candidates = bold_candidates + regular_candidates if bold else regular_candidates + bold_candidates
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    return img, draw


def _header(draw: ImageDraw.ImageDraw, title: str, subtitle: str = "") -> int:
    draw.rectangle([0, 0, WIDTH, HEADER_H], fill=FG)
    f_title = _font(72)
    f_sub   = _font(36)
    draw.text((24, 18), title, font=f_title, fill=BG)
    if subtitle:
        sub_bbox = draw.textbbox((0, 0), subtitle, font=f_sub)
        sub_w = sub_bbox[2]
        draw.text((WIDTH - sub_w - 24, 42), subtitle, font=f_sub, fill=200)
    return HEADER_H + 16


def _footer(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.line([0, HEIGHT - FOOTER_H, WIDTH, HEIGHT - FOOTER_H], fill=FG, width=3)
    draw.text((24, HEIGHT - FOOTER_H + 8), text, font=_font(30), fill=FG)


def _divider(draw: ImageDraw.ImageDraw, y: int, width: int = 2) -> int:
    draw.line([0, y, WIDTH, y], fill=FG, width=width)
    return y + width + 8


def _section_bar(draw: ImageDraw.ImageDraw, y: int, text: str, font_size: int = 44) -> int:
    """Dark band section header. Returns y after the band."""
    h = font_size + 20
    draw.rectangle([0, y, WIDTH, y + h], fill=DARK)
    draw.text((24, y + 10), text, font=_font(font_size), fill=BG)
    return y + h + 8


# ── HA Screen ─────────────────────────────────────────────────────────────────
def render_ha(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Home Status", datetime.now().strftime("%a %b %-d  %-I:%M %p"))

    if "error" in data:
        draw.text((40, y + 20), "HA not configured", font=_font(56), fill=FG)
        draw.text((40, y + 100), "Set HA_TOKEN in .env", font=_font(40), fill=DARK)
        _footer(draw, "Home Assistant")
        return img

    summary = data.get("summary", {})
    stats = [
        ("LIGHTS ON",  str(summary.get("lights_on", "?"))),
        ("LOCKS",      str(summary.get("locks_locked", "?/?"))),
        ("DOORS OPEN", str(summary.get("doors_open", "?"))),
        ("ALARM",      str(summary.get("alarm", "?"))),
    ]

    f_label = _font(36)
    f_value = _font(100)
    col_w   = WIDTH // 4
    stat_h  = 180

    for i, (label, val) in enumerate(stats):
        x = i * col_w
        if i > 0:
            draw.line([x, y, x, y + stat_h], fill=FG, width=2)
        draw.text((x + 20, y + 12), label, font=f_label, fill=DARK)
        draw.text((x + 20, y + 56), val,   font=f_value, fill=FG)

    y += stat_h
    y = _divider(draw, y, width=3)

    f_entity = _font(36)
    entities = data.get("entities", [])[:20]
    col_w2   = WIDTH // 2
    row_h    = 48

    for idx, ent in enumerate(entities):
        col = idx % 2
        row = idx // 2
        x   = col * col_w2 + 20
        ey  = y + row * row_h
        if ey + row_h > CONTENT_MAX_Y:
            break
        name  = ent.get("name", ent["entity_id"])[:32]
        state = ent.get("state", "")
        unit  = ent.get("unit") or ""
        line  = f"{name}: {state}{(' ' + unit) if unit else ''}".strip()
        draw.text((x, ey), line, font=f_entity, fill=FG)

    _footer(draw, f"Home Assistant  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


# ── Weather Screen ─────────────────────────────────────────────────────────────
def render_weather(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Weather", datetime.now().strftime("%A, %B %-d"))

    if "error" in data:
        draw.text((40, y + 20), "Weather unavailable", font=_font(56), fill=FG)
        _footer(draw, "Open-Meteo")
        return img

    cur   = data.get("current", {})
    temp  = cur.get("temp_f", "--")
    feels = cur.get("feels_like_f", "--")
    cond  = cur.get("condition", "")
    hum   = cur.get("humidity_pct", "--")
    wind  = cur.get("wind_mph", "--")

    draw.text((40, y), f"{temp}\u00b0F", font=_font(160), fill=FG)
    draw.text((40, y + 170), cond, font=_font(64), fill=FG)
    draw.text((40, y + 248),
              f"Feels like {feels}\u00b0  \u2022  Humidity {hum}%  \u2022  Wind {wind} mph",
              font=_font(44), fill=DARK)

    y2 = y + 320
    y2 = _divider(draw, y2, width=3)

    forecast = data.get("forecast", [])[:5]
    if not forecast:
        _footer(draw, f"Open-Meteo  \u2022  {data.get('fetched_at', '')[:16]}Z")
        return img

    f_day  = _font(48)
    f_temp = _font(56)
    f_cond = _font(36)
    col_w  = WIDTH // len(forecast)

    for i, day in enumerate(forecast):
        x       = i * col_w + 20
        date_str = day.get("date", "")
        try:
            label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %-d")
        except ValueError:
            label = date_str[:6]
        hi     = day.get("high", "--")
        lo     = day.get("low", "--")
        cond_d = day.get("condition", "")[:12]
        precip = day.get("precip_in", 0)

        if i > 0:
            draw.line([x - 20, y2, x - 20, CONTENT_MAX_Y], fill=FG, width=2)

        draw.text((x, y2), label, font=f_day, fill=FG)
        hi_str = str(int(hi)) if isinstance(hi, float) else str(hi)
        lo_str = str(int(lo)) if isinstance(lo, float) else str(lo)
        draw.text((x, y2 + 60),  f"{hi_str}\u00b0/{lo_str}\u00b0", font=f_temp, fill=FG)
        draw.text((x, y2 + 128), cond_d, font=f_cond, fill=DARK)
        if isinstance(precip, (int, float)) and precip > 0.01:
            draw.text((x, y2 + 174), f"Rain {precip:.2f}\"", font=f_cond, fill=FG)

    _footer(draw, f"Open-Meteo  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


# ── F1 Screen ─────────────────────────────────────────────────────────────────
def render_sports_f1(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    race_name = data.get("race_name", "Formula 1")
    subtitle  = f"Rnd {data.get('round', '?')}  {data.get('season', '')}"
    y = _header(draw, "Formula 1", subtitle)

    if "error" in data and not data.get("sessions"):
        draw.text((40, y + 40), data.get("error", "No data"), font=_font(56), fill=FG)
        _footer(draw, "Jolpica F1 API")
        return img

    # Race name banner
    draw.text((40, y), race_name, font=_font(72), fill=FG)
    y += 90
    y = _divider(draw, y, width=3)

    sessions = data.get("sessions", [])
    if not sessions:
        draw.text((40, y + 30), "No sessions found", font=_font(56), fill=DARK)
        _footer(draw, "Jolpica F1 API")
        return img

    # Column positions
    COL_NAME = 40
    COL_DATE = 420
    COL_TIME = 900
    row_h    = 110

    f_name   = _font(60)
    f_detail = _font(52, bold=False)
    f_label  = _font(36, bold=False)

    # Header row
    draw.text((COL_NAME, y), "Session",  font=f_label, fill=DARK)
    draw.text((COL_DATE, y), "Date",     font=f_label, fill=DARK)
    draw.text((COL_TIME, y), "Time (PT)",font=f_label, fill=DARK)
    y += 44
    y = _divider(draw, y)

    for session in sessions:
        if y + row_h > CONTENT_MAX_Y:
            break
        is_past = session.get("past", False)
        color   = DARK if is_past else FG

        name_text = session.get("name", "")
        # Highlight the Race row
        if name_text == "Race":
            draw.rectangle([0, y - 4, WIDTH, y + row_h - 4], fill=DARK)
            draw.text((COL_NAME, y + 16), name_text,                    font=f_name,   fill=BG)
            draw.text((COL_DATE, y + 16), session.get("display_date",""),font=f_detail, fill=BG)
            draw.text((COL_TIME, y + 16), session.get("display_time",""),font=f_detail, fill=BG)
        else:
            draw.text((COL_NAME, y + 16), name_text,                    font=f_name,   fill=color)
            draw.text((COL_DATE, y + 16), session.get("display_date",""),font=f_detail, fill=color)
            draw.text((COL_TIME, y + 16), session.get("display_time",""),font=f_detail, fill=color)

        y += row_h
        draw.line([0, y - 4, WIDTH, y - 4], fill=128, width=1)

    _footer(draw, f"Formula 1  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


# ── US Sports Screen ───────────────────────────────────────────────────────────
def render_sports_us(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "US Sports", datetime.now().strftime("%a %b %-d"))

    f_team    = _font(52)
    f_detail  = _font(44, bold=False)
    f_label   = _font(36, bold=False)
    f_badge   = _font(36)

    # ── Giants section ──────────────────────────────────────────────────────
    giants = data.get("giants", {})
    y = _section_bar(draw, y, "SF Giants  \u26be")

    series_list = giants.get("series", [])
    if not series_list:
        draw.text((40, y + 10), "No upcoming games", font=f_detail, fill=DARK)
        y += 70
    else:
        for series in series_list:
            if y + 120 > CONTENT_MAX_Y - 200:
                break
            venue   = series.get("venue_flag", "vs")
            opp     = series.get("opponent", "")
            n       = series.get("num_games", 0)
            s_date  = series.get("start_date", "")
            e_date  = series.get("end_date", "")
            date_rng = s_date if s_date == e_date else f"{s_date} – {e_date}"

            # Series header line
            draw.text((40, y + 8),
                      f"{venue} {opp}  ({n}-game series)",
                      font=f_team, fill=FG)
            y += 68

            # Individual game times
            for game in series.get("games", [])[:4]:
                if y + 50 > CONTENT_MAX_Y - 160:
                    break
                draw.text((80, y),
                          f"{game['display_date']}  {game['display_time']}",
                          font=f_detail, fill=DARK)
                y += 48

            y += 8

    y = _divider(draw, y, width=2)

    # ── 49ers section ─────────────────────────────────────────────────────────
    niners = data.get("niners", {})
    y = _section_bar(draw, y, "SF 49ers  \ud83c\udfc8")

    games = niners.get("games", [])
    if not games:
        draw.text((40, y + 10), "No upcoming games — off-season", font=f_detail, fill=DARK)
        y += 70
    else:
        for game in games:
            if y + 70 > CONTENT_MAX_Y:
                break
            venue = game.get("venue_flag", "vs")
            opp   = game.get("opponent", "")
            draw.text((40, y + 8),
                      f"{venue} {opp}",
                      font=f_team, fill=FG)
            draw.text((40 + 600, y + 18),
                      f"{game.get('display_date','')}  {game.get('display_time','')}",
                      font=f_detail, fill=DARK)
            y += 72

    _footer(draw, f"ESPN  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


# ── Soccer Screen ──────────────────────────────────────────────────────────────
def render_sports_soccer(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Soccer", datetime.now().strftime("%a %b %-d"))

    f_team   = _font(52)
    f_detail = _font(44, bold=False)
    f_comp   = _font(32, bold=False)

    # Columns
    COL_VENUE = 40
    COL_OPP   = 130
    COL_DATE  = 920
    COL_COMP  = 1480
    row_h     = 68

    for club_key, club_label, emoji in [
        ("spurs",   "Tottenham Hotspur", "\u26bd"),
        ("mancity", "Manchester City",   "\u26bd"),
    ]:
        club = data.get(club_key, {})
        y = _section_bar(draw, y, f"{club.get('label', club_label)}  {emoji}")

        games = club.get("games", [])
        if not games:
            draw.text((40, y + 10), "No upcoming fixtures found", font=f_detail, fill=DARK)
            y += 60
        else:
            for game in games:
                if y + row_h > CONTENT_MAX_Y - 80:
                    break
                venue = game.get("venue_flag", "vs")
                opp   = game.get("opponent", "")[:26]
                comp  = game.get("competition", "")

                draw.text((COL_VENUE,  y + 10), venue, font=f_detail, fill=DARK)
                draw.text((COL_OPP,   y + 8),  opp,   font=f_team,   fill=FG)
                draw.text((COL_DATE,  y + 14),
                          f"{game.get('display_date','')}  {game.get('display_time','')}",
                          font=f_detail, fill=DARK)
                draw.text((COL_COMP,  y + 18), comp,  font=f_comp,  fill=DARK)
                y += row_h

        if y < CONTENT_MAX_Y - 80:
            y = _divider(draw, y + 4, width=2)

    _footer(draw, f"ESPN  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


# ── Calendar Screen ────────────────────────────────────────────────────────────
def render_calendar(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Family Calendar", datetime.now().strftime("%a %b %-d"))

    if "error" in data:
        draw.text((40, y + 20), "Calendar unavailable", font=_font(56), fill=FG)
        _footer(draw, "Configure ICAL_URL in .env")
        return img

    events = data.get("events", [])
    if not events:
        draw.text((40, y + 40), "No upcoming events", font=_font(60), fill=FG)
        draw.text((40, y + 120), "in the next 14 days", font=_font(44), fill=DARK)
        _footer(draw, "Configure ICAL_URL in .env")
        return img

    f_date_header = _font(44)
    f_time        = _font(36)
    f_title       = _font(52)
    f_loc         = _font(36)

    last_date = None
    for event in events[:10]:
        start     = event.get("start", "")
        date_str  = start[:10]
        time_str  = "" if event.get("all_day") else start[11:16]
        summary   = event.get("summary", "No title")[:45]
        location  = event.get("location")
        cal_label = event.get("calendar")

        if date_str != last_date:
            if last_date is not None:
                y = _divider(draw, y + 4)
            try:
                d     = datetime.strptime(date_str, "%Y-%m-%d")
                label = d.strftime("%A, %B %-d")
            except ValueError:
                label = date_str
            draw.rectangle([0, y, WIDTH, y + 56], fill=DARK)
            draw.text((24, y + 8), label, font=f_date_header, fill=BG)
            y += 64
            last_date = date_str

        if y + 60 > CONTENT_MAX_Y:
            draw.text((24, y), "\u2026more events", font=f_time, fill=DARK)
            break

        time_label = time_str if time_str else "All day"
        draw.text((24, y),   time_label, font=f_time,  fill=DARK)
        draw.text((160, y),  summary,    font=f_title, fill=FG)
        y += 58
        if location and y + 42 < CONTENT_MAX_Y:
            draw.text((160, y), f"\u25b8 {location[:44]}", font=f_loc, fill=DARK)
            y += 44
        if cal_label and y + 42 < CONTENT_MAX_Y:
            draw.text((160, y), f"\u25cb {cal_label[:32]}", font=f_loc, fill=DARK)
            y += 40

    _footer(draw, f"Calendar  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


# ── Dispatch ──────────────────────────────────────────────────────────────────
RENDERERS = {
    "ha":            render_ha,
    "weather":       render_weather,
    "sports_f1":     render_sports_f1,
    "sports_us":     render_sports_us,
    "sports_soccer": render_sports_soccer,
    "calendar":      render_calendar,
}


def render_screen(name: str, data: dict[str, Any]) -> Image.Image:
    renderer = RENDERERS.get(name)
    if not renderer:
        raise ValueError(f"Unknown screen: {name}")
    img = renderer(data)
    # Convert to 1-bit — no dithering for e-ink
    bw = img.point(lambda x: 0 if x < 128 else 255, mode="L")
    return bw.convert("1", dither=Image.Dither.NONE)
