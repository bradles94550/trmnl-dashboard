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
CONTENT_MAX_Y = HEIGHT - 10  # footers removed; use full height


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



# ── Weather icons (Unicode — e-ink safe, in DejaVu Sans) ───────────────────
_WEATHER_ICON: dict[str, str] = {
    "Clear":                   "☀",
    "Mainly Clear":            "☀",
    "Partly Cloudy":           "⛅",
    "Overcast":                "☁",
    "Foggy":                   "≡",
    "Icy Fog":                 "≡",
    "Light Drizzle":           "☂",
    "Drizzle":                 "☂",
    "Heavy Drizzle":           "☂",
    "Light Rain":              "☂",
    "Rain":                    "☂",
    "Heavy Rain":              "☂",
    "Light Snow":              "❄",
    "Snow":                    "❄",
    "Heavy Snow":              "❄",
    "Snow Grains":             "❄",
    "Showers":                 "☂",
    "Heavy Showers":           "☂",
    "Violent Showers":         "☂",
    "Snow Showers":            "❄",
    "Heavy Snow Showers":      "❄",
    "Thunderstorm":            "⚡",
    "Thunderstorm+Hail":       "⚡",
    "Thunderstorm+Heavy Hail": "⚡",
}




# ── Pro sports event filter ────────────────────────────────────────────────────
_PRO_SPORTS_SUMMARIES = {
    "tottenham", "spurs", "man city", "manchester city",
    "sf giants", "giants", "49ers", "niners", "warriors",
    "formula 1", "f1",
}

def _is_pro_sports_event(summary: str) -> bool:
    """Return True if the event summary looks like a pro sports fixture."""
    low = summary.lower()
    return any(kw in low for kw in _PRO_SPORTS_SUMMARIES)

def _weather_icon(condition: str) -> str:
    return _WEATHER_ICON.get(condition, "?")

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



def _has_upcoming_in_days(games: list[dict], days: int = 14) -> bool:
    """Return True if any game starts within `days` days from now."""
    from datetime import datetime, timezone, timedelta
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days)
    for g in games:
        date_iso = g.get("date_iso", "")
        if not date_iso:
            continue
        try:
            dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
            if dt <= cutoff:
                return True
        except Exception:
            pass
    return False

# ── HA Screen ─────────────────────────────────────────────────────────────────
def render_ha(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Home Status", datetime.now().strftime("%a %b %-d  %-I:%M %p"))

    if "error" in data:
        draw.text((40, y + 20), "HA not configured", font=_font(56), fill=FG)
        draw.text((40, y + 100), "Set HA_TOKEN in .env", font=_font(40), fill=DARK)
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

    return img


# ── Weather Screen ─────────────────────────────────────────────────────────────
def render_weather(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Weather", datetime.now().strftime("%A, %B %-d"))

    if "error" in data:
        draw.text((40, y + 20), "Weather unavailable", font=_font(56), fill=FG)
        return img

    cur   = data.get("current", {})
    temp  = cur.get("temp_f", "--")
    feels = cur.get("feels_like_f", "--")
    cond  = cur.get("condition", "")
    hum   = cur.get("humidity_pct", "--")
    wind  = cur.get("wind_mph", "--")

    def _cx(text, font):
        w = draw.textbbox((0, 0), text, font=font)[2]
        return (WIDTH - w) // 2

    f160 = _font(160); f64w = _font(64); f44w = _font(44)
    temp_text  = f"{temp}\u00b0F"
    feels_line = f"Feels like {feels}\u00b0  \u2022  Humidity {hum}%  \u2022  Wind {wind} mph"
    draw.text((_cx(temp_text,  f160), y),       temp_text,  font=f160, fill=FG)
    draw.text((_cx(cond,       f64w), y + 170), cond,       font=f64w, fill=FG)
    draw.text((_cx(feels_line, f44w), y + 248), feels_line, font=f44w, fill=DARK)

    y2 = y + 320
    y2 = _divider(draw, y2, width=3)

    forecast = data.get("forecast", [])[:5]
    if not forecast:
        return img

    f_day  = _font(60)
    f_temp = _font(64)
    f_cond = _font(60)
    col_w  = WIDTH // len(forecast)

    for i, day in enumerate(forecast):
        col_cx  = i * col_w + col_w // 2   # column center x
        date_str = day.get("date", "")
        try:
            label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %-d")
        except ValueError:
            label = date_str[:6]
        hi     = day.get("high", "--")
        lo     = day.get("low", "--")
        icon   = _weather_icon(day.get("condition", ""))
        precip = day.get("precip_in", 0)

        if i > 0:
            draw.line([i * col_w, y2, i * col_w, CONTENT_MAX_Y], fill=FG, width=2)

        hi_str   = str(int(hi)) if isinstance(hi, float) else str(hi)
        lo_str   = str(int(lo)) if isinstance(lo, float) else str(lo)
        temp_str = f"{hi_str}\u00b0/{lo_str}\u00b0"
        prec_str = f"\u2614 {precip:.2f}\"" if isinstance(precip, (int, float)) and precip > 0.01 else ""

        def _mid(text, font, cx=col_cx):
            w = draw.textbbox((0, 0), text, font=font)[2]
            return cx - w // 2

        draw.text((_mid(label,    f_day),  y2),       label,    font=f_day,  fill=FG)
        draw.text((_mid(temp_str, f_temp), y2 + 76),  temp_str, font=f_temp, fill=FG)
        draw.text((_mid(icon,     f_cond), y2 + 158), icon,     font=f_cond, fill=DARK)
        if prec_str:
            draw.text((_mid(prec_str, f_cond), y2 + 228), prec_str, font=f_cond, fill=FG)

    return img


# ── F1 Screen ─────────────────────────────────────────────────────────────────
def render_sports_f1(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    race_name = data.get("race_name", "Formula 1")
    subtitle  = f"Rnd {data.get('round', '?')}  {data.get('season', '')}"
    y = _header(draw, "Formula 1", subtitle)

    if "error" in data and not data.get("sessions"):
        draw.text((40, y + 40), data.get("error", "No data"), font=_font(56), fill=FG)
        return img

    # Race name banner
    draw.text((40, y), race_name, font=_font(72), fill=FG)
    y += 90
    y = _divider(draw, y, width=3)

    sessions = data.get("sessions", [])
    if not sessions:
        draw.text((40, y + 30), "No sessions found", font=_font(56), fill=DARK)
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

    return img


# ── Calendar Screen ────────────────────────────────────────────────────────────
def render_calendar(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Family Calendar", datetime.now().strftime("%a %b %-d"))

    if "error" in data:
        draw.text((40, y + 20), "Calendar unavailable", font=_font(56), fill=FG)
        return img

    events = data.get("events", [])
    if not events:
        draw.text((40, y + 40), "No upcoming events", font=_font(60), fill=FG)
        draw.text((40, y + 120), "in the next 7 days", font=_font(44), fill=DARK)
        return img

    f_date_header = _font(44)
    f_time        = _font(36)
    f_title       = _font(52)
    f_loc         = _font(36)

    events = [e for e in events if not _is_pro_sports_event(e.get("summary", ""))]
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
            BAR_H = 56
            draw.rectangle([0, y, WIDTH, y + BAR_H], fill=DARK)
            _th = draw.textbbox((0, 0), label, font=f_date_header)[3]
            draw.text((24, y + (BAR_H - _th) // 2), label, font=f_date_header, fill=BG)
            y += BAR_H + 8
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

    return img






# ── Main Dashboard Screen ──────────────────────────────────────────────────────
def render_main(data: dict[str, Any]) -> Image.Image:
    from datetime import timedelta  # noqa: F811

    img, draw = _new_canvas()

    BORDER     = 3
    PAD        = 14
    HDR_H      = 56
    TITLE_PAD  = 11   # breathing room between title bar and content panels
    CONTENT_Y0 = HDR_H + TITLE_PAD
    SPLIT_X    = 920   # left/right vertical divide
    PANEL_GAP  = 16    # gap between top-left and top-right panels
    L_RIGHT    = SPLIT_X - PANEL_GAP // 2
    R_LEFT     = SPLIT_X + PANEL_GAP // 2
    SPLIT_Y    = 730   # top/bottom horizontal divide
    SPLIT_GAP  = 14    # gap between top panels and bottom calendar panel

    # ── Header bar ────────────────────────────────────────────────────────────
    draw.rectangle([0, 0, WIDTH, HDR_H], fill=FG)
    f_hdr = _font(38)
    ts    = datetime.now().strftime("%a %b %-d  %-I:%M %p")
    draw.text((20, 9), "FAMILY DASHBOARD", font=f_hdr, fill=BG)
    ts_w  = draw.textbbox((0, 0), ts, font=f_hdr)[2]
    draw.text((WIDTH - ts_w - 20, 9), ts, font=f_hdr, fill=BG)

    # ── Section borders ───────────────────────────────────────────────────────
    draw.rectangle([0,        CONTENT_Y0, L_RIGHT,     SPLIT_Y - SPLIT_GAP // 2],     outline=FG, width=BORDER)
    draw.rectangle([R_LEFT,   CONTENT_Y0, WIDTH - 1,   SPLIT_Y - SPLIT_GAP // 2],     outline=FG, width=BORDER)
    draw.rectangle([0,        SPLIT_Y + SPLIT_GAP // 2, WIDTH - 1,   HEIGHT - 1],  outline=FG, width=BORDER)

    f_sec  = _font(34)
    f_team = _font(36)
    f_game = _font(32, bold=False)

    # ── Top Left: Pro Sports ──────────────────────────────────────────────────
    sports        = data.get("sports_us", {})
    s_left        = BORDER + PAD
    s_right       = L_RIGHT - BORDER - PAD
    sports_bottom = SPLIT_Y - SPLIT_GAP // 2 - BORDER - 8

    draw.rectangle([BORDER, CONTENT_Y0 + BORDER, L_RIGHT - BORDER, CONTENT_Y0 + BORDER + 42], fill=DARK)
    draw.text((s_left, CONTENT_Y0 + BORDER + 4), "PRO SPORTS SCHEDULE", font=f_sec, fill=BG)
    sy = CONTENT_Y0 + BORDER + 50

    # Giants — only if games within 14 days
    series_list     = sports.get("giants", {}).get("series", [])
    giant_games_flat = [g for s in series_list for g in s.get("games", [])]
    if giant_games_flat and _has_upcoming_in_days(giant_games_flat, 14) and sy + 40 < sports_bottom:
        draw.text((s_left, sy), "SF Giants", font=f_team, fill=FG)
        sy += 42
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

    # 49ers — only if games within 14 days
    niner_games = sports.get("niners", {}).get("games", [])
    if niner_games and _has_upcoming_in_days(niner_games, 14) and sy + 40 < sports_bottom:
        draw.text((s_left, sy), "SF 49ers", font=f_team, fill=FG)
        sy += 42
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

    # ── Soccer in sports panel ───────────────────────────────────────────────
    soccer_data = data.get("sports_soccer", {})
    for club_key, club_label in [("spurs", "Spurs"), ("mancity", "Man City")]:
        club = soccer_data.get(club_key, {})
        club_games = club.get("games", [])
        upcoming = [g for g in club_games if not g.get("past", False)]
        if not upcoming:
            continue
        if sy + 12 < sports_bottom - 40:
            draw.line([s_left, sy + 4, s_right, sy + 4], fill=128, width=1)
            sy += 14
        if sy + 40 < sports_bottom:
            draw.text((s_left, sy), club_label, font=f_team, fill=FG)
            sy += 38
            for game in upcoming[:1]:
                if sy + 30 > sports_bottom:
                    break
                venue = game.get("venue_flag", "vs")
                opp   = game.get("opponent", "")[:14]
                dt    = game.get("display_date", "")
                draw.text((s_left + 8, sy), f"{venue} {opp}  {dt}", font=f_game, fill=FG)
                sy += 30

    # ── Top Right: Weather ────────────────────────────────────────────────────
    weather        = data.get("weather", {})
    wx0            = R_LEFT + BORDER + PAD
    weather_right  = WIDTH - BORDER - PAD
    weather_bottom = SPLIT_Y - SPLIT_GAP // 2 - BORDER - 8

    draw.rectangle([R_LEFT + BORDER, CONTENT_Y0 + BORDER, WIDTH - BORDER - 1, CONTENT_Y0 + BORDER + 42], fill=DARK)
    draw.text((wx0, CONTENT_Y0 + BORDER + 4), "WEATHER  \u2014  Livermore", font=f_sec, fill=BG)
    wy = CONTENT_Y0 + BORDER + 50

    if "error" not in weather:
        cur   = weather.get("current", {})
        temp  = cur.get("temp_f",       "--")
        cond  = cur.get("condition",    "")
        feels = cur.get("feels_like_f", "--")
        wind  = cur.get("wind_mph",     "--")

        temp_str  = f"{int(temp)}\u00b0F"  if isinstance(temp,  (int, float)) else f"{temp}\u00b0F"
        feels_str = f"{int(feels)}\u00b0"  if isinstance(feels, (int, float)) else str(feels)
        wind_str  = f"{int(wind)} mph"     if isinstance(wind,  (int, float)) else str(wind)

        panel_cx = (R_LEFT + WIDTH) // 2
        def _pcx(text, font):
            w = draw.textbbox((0, 0), text, font=font)[2]
            return panel_cx - w // 2

        f130 = _font(130); f46 = _font(46); f34 = _font(34, bold=False)
        draw.text((_pcx(temp_str, f130), wy), temp_str, font=f130, fill=FG)
        wy += 144
        draw.text((_pcx(cond, f46), wy), cond, font=f46, fill=FG)
        wy += 56
        feels_wind = f"Feels {feels_str}  \u2022  Wind {wind_str}"
        draw.text((_pcx(feels_wind, f34), wy), feels_wind, font=f34, fill=DARK)
        wy += 48
        draw.line([wx0, wy, weather_right, wy], fill=FG, width=2)
        wy += 14

        # 5-day forecast — column table (one column per day, fixed positions)
        forecast = weather.get("forecast", [])[:5]
        if forecast:
            f_day = _font(34)
            f_hl  = _font(34)
            f_ico = _font(38)
            n_days = len(forecast)
            panel_w = weather_right - wx0
            col_w   = panel_w // n_days

            for i, day in enumerate(forecast):
                cx = wx0 + i * col_w + col_w // 2
                if i > 0:
                    draw.line([wx0 + i * col_w, wy, wx0 + i * col_w, weather_bottom],
                              fill=196, width=1)
                date_str = day.get("date", "")
                try:
                    day_lbl = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")
                except ValueError:
                    day_lbl = date_str[:3]
                hi  = day.get("high", "--")
                lo  = day.get("low", "--")
                hi_s = f"{int(hi)}\u00b0" if isinstance(hi, (int, float)) else str(hi)
                lo_s = f"{int(lo)}\u00b0" if isinstance(lo, (int, float)) else str(lo)
                icon = _weather_icon(day.get("condition", ""))
                precip = day.get("precip_in", 0)
                if isinstance(precip, (int, float)) and precip > 0.05:
                    icon += "\u2614"
                hl_s = f"{hi_s}/{lo_s}"

                def _cc(text, font, cx=cx):
                    w = draw.textbbox((0, 0), text, font=font)[2]
                    return cx - w // 2

                row0 = wy
                row1 = wy + 42
                row2 = wy + 86
                if row2 + 36 > weather_bottom:
                    break
                draw.text((_cc(day_lbl, f_day), row0), day_lbl, font=f_day, fill=FG)
                draw.text((_cc(icon,    f_ico), row1), icon,    font=f_ico, fill=DARK)
                draw.text((_cc(hl_s,    f_hl),  row2), hl_s,   font=f_hl,  fill=FG)
    else:
        draw.text((wx0, wy + 20), "Weather unavailable", font=_font(46), fill=DARK)

    # ── Bottom: Family Calendar (7 days, 2-column) ────────────────────────────
    cal_data   = data.get("calendar", {})
    events     = cal_data.get("events", [])
    cal_bottom = HEIGHT - BORDER - 8

    draw.rectangle([BORDER, SPLIT_Y + SPLIT_GAP // 2 + BORDER, WIDTH - BORDER - 1, SPLIT_Y + SPLIT_GAP // 2 + BORDER + 42], fill=DARK)
    draw.text((BORDER + PAD, SPLIT_Y + SPLIT_GAP // 2 + BORDER + 4),
              "FAMILY CALENDAR \u2014 NEXT 7 DAYS", font=f_sec, fill=BG)

    cy_start = SPLIT_Y + SPLIT_GAP // 2 + BORDER + 52
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

        events = [e for e in events if not _is_pro_sports_event(e.get("summary", ""))]
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
                _DHDR_H = 36
                draw.rectangle([cx - 4, cy, cx + HALF - 28, cy + _DHDR_H], fill=DARK)
                _dth = draw.textbbox((0, 0), dlbl, font=f_dhdr)[3]
                draw.text((cx, cy + (_DHDR_H - _dth) // 2), dlbl, font=f_dhdr, fill=BG)
                cy += _DHDR_H + 4
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
                    _DHDR_H = 36
                    draw.rectangle([cx - 4, cy, cx + HALF - 28, cy + _DHDR_H], fill=DARK)
                    _dth = draw.textbbox((0, 0), dlbl, font=f_dhdr)[3]
                    draw.text((cx, cy + (_DHDR_H - _dth) // 2), dlbl, font=f_dhdr, fill=BG)
                    cy += _DHDR_H + 4
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

    # ── Giants — skip if no games within 14 days ─────────────────────────────
    giants      = data.get("giants", {})
    giants_ser  = giants.get("series", [])
    giants_flat = [g for s in giants_ser for g in s.get("games", [])]
    if giants_flat and _has_upcoming_in_days(giants_flat, 14):
        y = _section_bar(draw, y, "SF Giants  \u26be", font_size=40)
        for series in giants_ser[:1]:
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

    # ── 49ers — skip if no games within 14 days ──────────────────────────────
    niners      = data.get("niners", {})
    niner_games = niners.get("games", [])
    if niner_games and _has_upcoming_in_days(niner_games, 14):
        y = _section_bar(draw, y, "SF 49ers  \U0001f3c8", font_size=40)
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
