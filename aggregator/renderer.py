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
        _footer(draw, "Calendar sync pending — check calendar-sync.py on Mac Mini")
        return img

    events = data.get("events", [])
    if not events:
        draw.text((40, y + 40), "No upcoming events", font=_font(60), fill=FG)
        draw.text((40, y + 120), "in the next 14 days", font=_font(44), fill=DARK)
        _footer(draw, "Calendar sync pending — check calendar-sync.py on Mac Mini")
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




_WEATHER_ABBR: dict[str, str] = {
    "Clear": "SUN",   "Mainly Clear": "SUN",  "Partly Cloudy": "PTLY",
    "Overcast": "CLDY", "Foggy": "FOG",        "Icy Fog": "FOG",
    "Light Drizzle": "DRIZ", "Drizzle": "DRIZ", "Heavy Drizzle": "DRIZ",
    "Light Rain": "RAIN",   "Rain": "RAIN",    "Heavy Rain": "RAIN",
    "Light Snow": "SNOW",   "Snow": "SNOW",    "Heavy Snow": "SNOW",
    "Snow Grains": "SNOW",  "Showers": "SHWR", "Heavy Showers": "SHWR",
    "Violent Showers": "SHWR", "Snow Showers": "SNOW", "Heavy Snow Showers": "SNOW",
    "Thunderstorm": "TSTM", "Thunderstorm+Hail": "TSTM", "Thunderstorm+Heavy Hail": "TSTM",
}


def _weather_abbr(condition: str) -> str:
    return _WEATHER_ABBR.get(condition, condition[:4].upper())


# ── Main Dashboard Screen ──────────────────────────────────────────────────────
def render_main(data: dict[str, Any]) -> Image.Image:
    from datetime import timedelta  # noqa: F811

    img, draw = _new_canvas()

    BORDER  = 3
    PAD     = 14
    HDR_H   = 56
    SPLIT_X = 920   # left/right vertical divide
    SPLIT_Y = 730   # top/bottom horizontal divide

    # ── Header bar ────────────────────────────────────────────────────────────
    draw.rectangle([0, 0, WIDTH, HDR_H], fill=FG)
    f_hdr = _font(38)
    ts    = datetime.now().strftime("%a %b %-d  %-I:%M %p")
    draw.text((20, 9), "FAMILY DASHBOARD", font=f_hdr, fill=BG)
    ts_w  = draw.textbbox((0, 0), ts, font=f_hdr)[2]
    draw.text((WIDTH - ts_w - 20, 9), ts, font=f_hdr, fill=BG)

    # ── Section borders ───────────────────────────────────────────────────────
    draw.rectangle([0,        HDR_H, SPLIT_X,     SPLIT_Y],     outline=FG, width=BORDER)
    draw.rectangle([SPLIT_X,  HDR_H, WIDTH - 1,   SPLIT_Y],     outline=FG, width=BORDER)
    draw.rectangle([0,        SPLIT_Y, WIDTH - 1,  HEIGHT - 1], outline=FG, width=BORDER)

    f_sec  = _font(34)
    f_team = _font(36)
    f_game = _font(32, bold=False)

    # ── Top Left: Pro Sports ──────────────────────────────────────────────────
    sports        = data.get("sports_us", {})
    s_left        = BORDER + PAD
    s_right       = SPLIT_X - BORDER - PAD
    sports_bottom = SPLIT_Y - BORDER - 8

    draw.rectangle([BORDER, HDR_H + BORDER, SPLIT_X - BORDER, HDR_H + BORDER + 42], fill=DARK)
    draw.text((s_left, HDR_H + BORDER + 4), "PRO SPORTS SCHEDULE", font=f_sec, fill=BG)
    sy = HDR_H + BORDER + 50

    # Giants
    if sy + 40 < sports_bottom:
        draw.text((s_left, sy), "SF Giants", font=f_team, fill=FG)
        sy += 42
        series_list = sports.get("giants", {}).get("series", [])
        if not series_list:
            draw.text((s_left + 16, sy), "No upcoming games", font=f_game, fill=DARK)
            sy += 34
        else:
            for series in series_list[:2]:
                if sy + 34 > sports_bottom - 120:
                    break
                venue = series.get("venue_flag", "vs")
                opp   = series.get("opponent", "")[:16]
                n     = series.get("num_games", 0)
                draw.text((s_left + 8, sy), f"{venue} {opp}  ({n}G)", font=f_game, fill=FG)
                sy += 34
                for game in series.get("games", [])[:3]:
                    if sy + 30 > sports_bottom - 120:
                        break
                    draw.text((s_left + 28, sy),
                              f"{game.get('display_date','')}  {game.get('display_time','')}",
                              font=f_game, fill=DARK)
                    sy += 30
                sy += 4

    # Thin divider between teams
    if sy + 12 < sports_bottom - 80:
        draw.line([s_left, sy + 4, s_right, sy + 4], fill=128, width=1)
        sy += 14

    # 49ers
    if sy + 40 < sports_bottom:
        draw.text((s_left, sy), "SF 49ers", font=f_team, fill=FG)
        sy += 42
        niner_games = sports.get("niners", {}).get("games", [])
        if not niner_games:
            draw.text((s_left + 16, sy), "Off-season -- no upcoming games", font=f_game, fill=DARK)
            sy += 34
        else:
            for game in niner_games[:5]:
                if sy + 34 > sports_bottom:
                    break
                venue = game.get("venue_flag", "vs")
                opp   = game.get("opponent", "")[:14]
                dt    = f"{game.get('display_date','')}  {game.get('display_time','')}"
                draw.text((s_left + 8, sy), f"{venue} {opp}  {dt}", font=f_game, fill=FG)
                sy += 34

    # ── F1 next race in sports panel ─────────────────────────────────────────────
    if sy + 12 < sports_bottom - 60:
        draw.line([s_left, sy + 4, s_right, sy + 4], fill=128, width=1)
        sy += 14
    if sy + 40 < sports_bottom:
        draw.text((s_left, sy), "Formula 1", font=f_team, fill=FG)
        sy += 42
        f1_data      = data.get("sports_f1", {})
        race_name_f1 = f1_data.get("race_name", "")
        f1_sessions  = f1_data.get("sessions", [])
        race_sess_f1 = next((s for s in f1_sessions if s.get("name") == "Race"), None)
        if race_name_f1 and sy + 30 < sports_bottom:
            draw.text((s_left + 8, sy), race_name_f1[:24], font=f_game, fill=FG)
            sy += 30
        if race_sess_f1 and sy + 30 < sports_bottom:
            draw.text((s_left + 8, sy),
                      f"Race: {race_sess_f1.get('display_date', '')}  {race_sess_f1.get('display_time', '')}",
                      font=f_game, fill=DARK)
            sy += 30

    # ── Top Right: Weather ────────────────────────────────────────────────────
    weather        = data.get("weather", {})
    wx0            = SPLIT_X + BORDER + PAD
    weather_right  = WIDTH - BORDER - PAD
    weather_bottom = SPLIT_Y - BORDER - 8

    draw.rectangle([SPLIT_X + BORDER, HDR_H + BORDER, WIDTH - BORDER - 1, HDR_H + BORDER + 42], fill=DARK)
    draw.text((wx0, HDR_H + BORDER + 4), "WEATHER  \u2014  Livermore", font=f_sec, fill=BG)
    wy = HDR_H + BORDER + 50

    if "error" not in weather:
        cur   = weather.get("current", {})
        temp  = cur.get("temp_f",       "--")
        cond  = cur.get("condition",    "")
        feels = cur.get("feels_like_f", "--")
        wind  = cur.get("wind_mph",     "--")

        temp_str  = f"{int(temp)}\u00b0F"  if isinstance(temp,  (int, float)) else f"{temp}\u00b0F"
        feels_str = f"{int(feels)}\u00b0"  if isinstance(feels, (int, float)) else str(feels)
        wind_str  = f"{int(wind)} mph"     if isinstance(wind,  (int, float)) else str(wind)

        draw.text((wx0, wy), temp_str, font=_font(130), fill=FG)
        wy += 144
        draw.text((wx0, wy), cond, font=_font(46), fill=FG)
        wy += 56
        draw.text((wx0, wy),
                  f"Feels {feels_str}  \u2022  Wind {wind_str}",
                  font=_font(34, bold=False), fill=DARK)
        wy += 48
        draw.line([wx0, wy, weather_right, wy], fill=FG, width=2)
        wy += 14

        # 5-day forecast table
        forecast = weather.get("forecast", [])[:5]
        f_day = _font(38)
        f_hi  = _font(42)
        f_ico = _font(36, bold=False)
        C_DAY  = wx0
        C_HI   = wx0 + 130
        C_ICON = wx0 + 270

        for day in forecast:
            if wy + 50 > weather_bottom:
                break
            date_str = day.get("date", "")
            try:
                day_lbl = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")
            except ValueError:
                day_lbl = date_str[:3]
            hi     = day.get("high", "--")
            hi_s   = f"{int(hi)}\u00b0" if isinstance(hi, (int, float)) else str(hi)
            icon   = f"[{_weather_abbr(day.get('condition', ''))}]"
            precip = day.get("precip_in", 0)
            if isinstance(precip, (int, float)) and precip > 0.05:
                icon += " \u2614"  # umbrella char

            draw.text((C_DAY,  wy),     day_lbl, font=f_day, fill=FG)
            draw.text((C_HI,   wy - 4), hi_s,    font=f_hi,  fill=FG)
            draw.text((C_ICON, wy + 4), icon,     font=f_ico, fill=DARK)
            wy += 50
    else:
        draw.text((wx0, wy + 20), "Weather unavailable", font=_font(46), fill=DARK)

    # ── Bottom: Family Calendar (7 days, 2-column) ────────────────────────────
    cal_data   = data.get("calendar", {})
    events     = cal_data.get("events", [])
    cal_bottom = HEIGHT - BORDER - 8

    draw.rectangle([BORDER, SPLIT_Y + BORDER, WIDTH - BORDER - 1, SPLIT_Y + BORDER + 42], fill=DARK)
    draw.text((BORDER + PAD, SPLIT_Y + BORDER + 4),
              "FAMILY CALENDAR \u2014 NEXT 7 DAYS", font=f_sec, fill=BG)

    cy_start = SPLIT_Y + BORDER + 52
    f_dhdr   = _font(36)
    f_evt    = _font(32, bold=False)

    if not events:
        draw.text((BORDER + PAD, cy_start + 16),
                  "No events in the next 7 days", font=f_evt, fill=DARK)
    else:
        HALF     = WIDTH // 2
        col_x    = [BORDER + PAD, HALF + PAD]
        col_y    = [cy_start, cy_start]
        cur_col  = 0
        seen     : dict[int, str] = {}

        for event in events[:40]:
            if cur_col >= 2:
                break
            cx       = col_x[cur_col]
            cy       = col_y[cur_col]
            start    = event.get("start", "")
            date_str = start[:10]
            time_str = "" if event.get("all_day") else start[11:16]
            summary  = event.get("summary", "")

            # Date header
            if date_str != seen.get(cur_col):
                if cy + 40 > cal_bottom:
                    cur_col += 1
                    if cur_col >= 2:
                        break
                    cx, cy = col_x[cur_col], col_y[cur_col]
                try:
                    dlbl = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %b %-d")
                except ValueError:
                    dlbl = date_str
                draw.rectangle([cx - 4, cy, cx + HALF - 28, cy + 36], fill=DARK)
                draw.text((cx, cy + 2), dlbl, font=f_dhdr, fill=BG)
                cy += 40
                seen[cur_col] = date_str
                col_y[cur_col] = cy

            # Event row
            if cy + 32 > cal_bottom:
                cur_col += 1
                if cur_col >= 2:
                    break
                cx, cy = col_x[cur_col], col_y[cur_col]
                # Repeat date header in new column if needed
                if date_str != seen.get(cur_col):
                    try:
                        dlbl = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %b %-d")
                    except ValueError:
                        dlbl = date_str
                    draw.rectangle([cx - 4, cy, cx + HALF - 28, cy + 36], fill=DARK)
                    draw.text((cx, cy + 2), dlbl, font=f_dhdr, fill=BG)
                    cy += 40
                    seen[cur_col] = date_str
                    col_y[cur_col] = cy

            if cy + 32 > cal_bottom:
                break

            time_lbl = time_str if time_str else "All day"
            summ     = summary[:34]
            draw.text((cx + 4, cy), f"{time_lbl}  {summ}", font=f_evt, fill=FG)
            cy += 34
            col_y[cur_col] = cy

    return img


# ── All Sports Screen ──────────────────────────────────────────────────────────
def render_sports_all(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Sports", datetime.now().strftime("%a %b %-d"))

    f_team   = _font(48)
    f_detail = _font(40, bold=False)

    # ── Giants ────────────────────────────────────────────────────────────────
    giants = data.get("giants", {})
    y = _section_bar(draw, y, "SF Giants  \u26be", font_size=40)
    series_list = giants.get("series", [])
    if not series_list:
        draw.text((40, y + 8), "No upcoming games", font=f_detail, fill=DARK)
        y += 52
    else:
        for series in series_list[:1]:
            venue = series.get("venue_flag", "vs")
            opp   = series.get("opponent", "")[:22]
            n     = series.get("num_games", 0)
            draw.text((40, y + 6), f"{venue} {opp}  ({n}-game series)", font=f_team, fill=FG)
            y += 56
            for game in series.get("games", [])[:3]:
                if y + 44 > CONTENT_MAX_Y - 560:
                    break
                draw.text((72, y), f"{game['display_date']}  {game['display_time']}", font=f_detail, fill=DARK)
                y += 44
            y += 4
    draw.line([0, y + 2, WIDTH, y + 2], fill=128, width=1)
    y += 12

    # ── 49ers ─────────────────────────────────────────────────────────────────
    niners = data.get("niners", {})
    y = _section_bar(draw, y, "SF 49ers  \U0001f3c8", font_size=40)
    niner_games = niners.get("games", [])
    if not niner_games:
        draw.text((40, y + 8), "Off-season \u2014 no upcoming games", font=f_detail, fill=DARK)
        y += 52
    else:
        for game in niner_games[:2]:
            if y + 52 > CONTENT_MAX_Y - 420:
                break
            venue = game.get("venue_flag", "vs")
            opp   = game.get("opponent", "")[:22]
            dt    = f"{game.get('display_date', '')}  {game.get('display_time', '')}"
            draw.text((40, y + 6), f"{venue} {opp}  {dt}", font=f_team, fill=FG)
            y += 52
    draw.line([0, y + 2, WIDTH, y + 2], fill=128, width=1)
    y += 12

    # ── Formula 1 ─────────────────────────────────────────────────────────────
    f1 = data.get("f1", {})
    rnd    = f1.get("round", "?")
    season = f1.get("season", "")
    y = _section_bar(draw, y, f"Formula 1 \u2014 Rnd {rnd} {season}", font_size=40)
    race_name = f1.get("race_name", "")
    if not race_name:
        draw.text((40, y + 8), "No F1 data", font=f_detail, fill=DARK)
        y += 52
    else:
        draw.text((40, y + 6), race_name[:40], font=f_team, fill=FG)
        y += 56
        sessions = f1.get("sessions", [])
        race_sess = next((s for s in sessions if s.get("name") == "Race"), None)
        if race_sess:
            past_marker = " \u2713" if race_sess.get("past") else ""
            color = DARK if race_sess.get("past") else FG
            draw.text((72, y),
                      f"Race: {race_sess.get('display_date', '')}  {race_sess.get('display_time', '')}{past_marker}",
                      font=f_detail, fill=color)
            y += 44
        y += 4
    draw.line([0, y + 2, WIDTH, y + 2], fill=128, width=1)
    y += 12

    # ── Soccer ────────────────────────────────────────────────────────────────
    for club_key, club_label, emoji in [
        ("spurs",   "Tottenham Hotspur", "\u26bd"),
        ("mancity", "Manchester City",   "\u26bd"),
    ]:
        club = data.get(club_key, {})
        y = _section_bar(draw, y, f"{club.get('label', club_label)}  {emoji}", font_size=40)
        club_games = club.get("games", [])
        if not club_games:
            draw.text((40, y + 8), "No upcoming fixtures", font=f_detail, fill=DARK)
            y += 52
        else:
            for game in club_games[:2]:
                if y + 52 > CONTENT_MAX_Y - 20:
                    break
                venue = game.get("venue_flag", "vs")
                opp   = game.get("opponent", "")[:22]
                comp  = game.get("competition", "")
                draw.text((40, y + 6),
                          f"{venue} {opp}  {game.get('display_date', '')}  {game.get('display_time', '')}  [{comp}]",
                          font=f_detail, fill=FG)
                y += 48
        if club_key == "spurs" and y < CONTENT_MAX_Y - 80:
            draw.line([0, y + 2, WIDTH, y + 2], fill=128, width=1)
            y += 12

    _footer(draw, f"ESPN / Jolpica F1  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img

# ── Dispatch ──────────────────────────────────────────────────────────────────
RENDERERS = {
    "ha":            render_ha,
    "weather":       render_weather,
    "sports_f1":     render_sports_f1,
    "sports_all":    render_sports_all,
    "sports_us":     render_sports_us,
    "sports_soccer": render_sports_soccer,
    "calendar":      render_calendar,
    "main":          render_main,
}


def render_screen(name: str, data: dict[str, Any]) -> Image.Image:
    renderer = RENDERERS.get(name)
    if not renderer:
        raise ValueError(f"Unknown screen: {name}")
    img = renderer(data)
    # Convert to 1-bit — no dithering for e-ink
    bw = img.point(lambda x: 0 if x < 128 else 255, mode="L")
    return bw.convert("1", dither=Image.Dither.NONE)
