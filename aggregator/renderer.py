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
WIDTH = 1872
HEIGHT = 1404
BG = 255    # white
FG = 0      # pure black — use for ALL text and lines
DARK = 64   # dark gray — renders as black after 1-bit conversion, use sparingly

HEADER_H = 120   # header bar height
FOOTER_H = 50    # footer area height
CONTENT_Y = HEADER_H + 10   # default content start
CONTENT_MAX_Y = HEIGHT - FOOTER_H - 10


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a TrueType font. Prefer bold sans-serif for e-ink readability."""
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
    """Draw a solid black header bar. Returns the y offset after the header."""
    draw.rectangle([0, 0, WIDTH, HEADER_H], fill=FG)
    f_title = _font(72)
    f_sub = _font(36)
    # Vertically center title in header
    draw.text((24, 18), title, font=f_title, fill=BG)
    if subtitle:
        bbox = draw.textbbox((0, 0), title, font=f_title)
        x_off = bbox[2] + 32
        # Right-align subtitle
        sub_bbox = draw.textbbox((0, 0), subtitle, font=f_sub)
        sub_w = sub_bbox[2]
        draw.text((WIDTH - sub_w - 24, 42), subtitle, font=f_sub, fill=200)
    return HEADER_H + 16


def _footer(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.line([0, HEIGHT - FOOTER_H, WIDTH, HEIGHT - FOOTER_H], fill=FG, width=3)
    f = _font(30)
    draw.text((24, HEIGHT - FOOTER_H + 8), text, font=f, fill=FG)


def _divider(draw: ImageDraw.ImageDraw, y: int, width: int = 2) -> int:
    """Draw a horizontal divider, return y after it."""
    draw.line([0, y, WIDTH, y], fill=FG, width=width)
    return y + width + 8


def render_ha(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Home Status", datetime.now().strftime("%a %b %-d  %-I:%M %p"))

    if "error" in data:
        draw.text((40, y + 20), f"HA not configured", font=_font(56), fill=FG)
        draw.text((40, y + 100), "Set HA_TOKEN in .env", font=_font(40), fill=DARK)
        _footer(draw, "Home Assistant")
        return img

    summary = data.get("summary", {})
    # 4 big stat boxes across the top
    stats = [
        ("LIGHTS ON",  str(summary.get("lights_on", "?"))),
        ("LOCKS",      str(summary.get("locks_locked", "?/?"))),
        ("DOORS OPEN", str(summary.get("doors_open", "?"))),
        ("ALARM",      str(summary.get("alarm", "?"))),
    ]

    f_label = _font(36)
    f_value = _font(100)
    col_w = WIDTH // 4
    stat_h = 180

    for i, (label, val) in enumerate(stats):
        x = i * col_w
        # Box border
        if i > 0:
            draw.line([x, y, x, y + stat_h], fill=FG, width=2)
        draw.text((x + 20, y + 12), label, font=f_label, fill=DARK)
        draw.text((x + 20, y + 56), val, font=f_value, fill=FG)

    y += stat_h
    y = _divider(draw, y, width=3)

    # Entity list — 2 columns, large readable text
    f_entity = _font(36)
    entities = data.get("entities", [])[:20]
    col_w2 = WIDTH // 2
    row_h = 48

    for idx, ent in enumerate(entities):
        col = idx % 2
        row = idx // 2
        x = col * col_w2 + 20
        ey = y + row * row_h
        if ey + row_h > CONTENT_MAX_Y:
            break
        name = ent.get("name", ent["entity_id"])[:32]
        state = ent.get("state", "")
        unit = ent.get("unit") or ""
        line = f"{name}: {state}{(' ' + unit) if unit else ''}".strip()
        draw.text((x, ey), line, font=f_entity, fill=FG)

    _footer(draw, f"Home Assistant  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


def render_weather(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "Weather", datetime.now().strftime("%A, %B %-d"))

    if "error" in data:
        draw.text((40, y + 20), "Weather unavailable", font=_font(56), fill=FG)
        _footer(draw, "Open-Meteo")
        return img

    cur = data.get("current", {})
    temp = cur.get("temp_f", "--")
    feels = cur.get("feels_like_f", "--")
    cond = cur.get("condition", "")
    hum = cur.get("humidity_pct", "--")
    wind = cur.get("wind_mph", "--")

    # Big temperature
    draw.text((40, y), f"{temp}\u00b0F", font=_font(160), fill=FG)
    draw.text((40, y + 170), cond, font=_font(64), fill=FG)
    draw.text((40, y + 248), f"Feels like {feels}\u00b0  \u2022  Humidity {hum}%  \u2022  Wind {wind} mph",
              font=_font(44), fill=DARK)

    # Forecast section
    y2 = y + 320
    y2 = _divider(draw, y2, width=3)

    forecast = data.get("forecast", [])[:5]
    if not forecast:
        _footer(draw, f"Open-Meteo  \u2022  {data.get('fetched_at', '')[:16]}Z")
        return img

    f_day = _font(48)
    f_temp = _font(56)
    f_cond = _font(36)
    col_w = WIDTH // len(forecast)

    for i, day in enumerate(forecast):
        x = i * col_w + 20
        date_str = day.get("date", "")
        try:
            label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %-d")
        except ValueError:
            label = date_str[:6]
        hi = day.get("high", "--")
        lo = day.get("low", "--")
        cond_d = day.get("condition", "")[:12]
        precip = day.get("precip_in", 0)

        if i > 0:
            draw.line([x - 20, y2, x - 20, CONTENT_MAX_Y], fill=FG, width=2)

        draw.text((x, y2), label, font=f_day, fill=FG)
        hi_str = str(int(hi)) if isinstance(hi, float) else str(hi)
        lo_str = str(int(lo)) if isinstance(lo, float) else str(lo)
        draw.text((x, y2 + 60), f"{hi_str}\u00b0/{lo_str}\u00b0", font=f_temp, fill=FG)
        draw.text((x, y2 + 128), cond_d, font=f_cond, fill=DARK)
        if isinstance(precip, (int, float)) and precip > 0.01:
            draw.text((x, y2 + 174), f"Rain {precip:.2f}\"", font=f_cond, fill=FG)

    _footer(draw, f"Open-Meteo  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


def render_sports(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    league = data.get("league", "Sports")
    y = _header(draw, f"{league} Scores", datetime.now().strftime("%a %b %-d"))

    if "error" in data:
        draw.text((40, y + 20), "Sports data unavailable", font=_font(56), fill=FG)
        _footer(draw, "ESPN")
        return img

    f_section = _font(40)
    f_team = _font(52)
    f_score = _font(64)
    f_status = _font(36)

    today = data.get("today", [])
    tomorrow = data.get("tomorrow", [])

    if not today:
        draw.text((40, y + 30), "No games today", font=_font(60), fill=FG)
    else:
        draw.text((24, y), "TODAY", font=f_section, fill=DARK)
        y += 52
        y = _divider(draw, y)

        # Column layout: Away | Score | Home | Status
        COL_AWAY = 24
        COL_SCORE = WIDTH // 2 - 120
        COL_HOME = WIDTH // 2 + 40
        COL_STATUS = WIDTH - 280

        # Headers
        draw.text((COL_AWAY, y), "Away", font=f_status, fill=DARK)
        draw.text((COL_SCORE, y), "Score", font=f_status, fill=DARK)
        draw.text((COL_HOME, y), "Home", font=f_status, fill=DARK)
        draw.text((COL_STATUS, y), "Status", font=f_status, fill=DARK)
        y += 44
        y = _divider(draw, y)

        row_h = 72
        for game in today[:6]:
            if y + row_h > CONTENT_MAX_Y - 120:
                break
            is_our_team = game.get("our_team") is not None
            color = FG
            away_score = game.get("away_score", "")
            home_score = game.get("home_score", "")
            score_str = f"{away_score}\u2013{home_score}" if game.get("completed") else "vs"
            status = game.get("status", "")[:14]

            away = game["away_team"][:18]
            home = game["home_team"][:18]

            # Bold our team's games
            f = f_team
            draw.text((COL_AWAY, y), away, font=f, fill=FG)
            draw.text((COL_SCORE, y), score_str, font=f_score, fill=FG)
            draw.text((COL_HOME, y), home, font=f, fill=FG)
            draw.text((COL_STATUS, y), status, font=f_status, fill=DARK)
            y += row_h

    if tomorrow and y + 80 < CONTENT_MAX_Y:
        y = _divider(draw, y + 8, width=3)
        draw.text((24, y), "TOMORROW", font=f_section, fill=DARK)
        y += 52
        for game in tomorrow[:4]:
            if y + 52 > CONTENT_MAX_Y:
                break
            draw.text((40, y), game["name"][:55], font=_font(44), fill=FG)
            y += 52

    _footer(draw, f"ESPN  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


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
    f_time = _font(36)
    f_title = _font(52)
    f_loc = _font(36)

    last_date = None
    for event in events[:10]:
        start = event.get("start", "")
        date_str = start[:10]
        time_str = "" if event.get("all_day") else start[11:16]
        summary = event.get("summary", "No title")[:45]
        location = event.get("location")

        # Date section header if new day
        if date_str != last_date:
            if last_date is not None:
                y = _divider(draw, y + 4)
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
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
        draw.text((24, y), time_label, font=f_time, fill=DARK)
        draw.text((160, y), summary, font=f_title, fill=FG)
        y += 58
        if location and y + 42 < CONTENT_MAX_Y:
            draw.text((160, y), f"\u25b8 {location[:44]}", font=f_loc, fill=DARK)
            y += 44

    _footer(draw, f"Calendar  \u2022  {data.get('fetched_at', '')[:16]}Z")
    return img


RENDERERS = {
    "ha": render_ha,
    "weather": render_weather,
    "sports": render_sports,
    "calendar": render_calendar,
}


def render_screen(name: str, data: dict[str, Any]) -> Image.Image:
    renderer = RENDERERS.get(name)
    if not renderer:
        raise ValueError(f"Unknown screen: {name}")
    img = renderer(data)
    # Convert to 1-bit with clean threshold (no dithering — e-ink looks better crisp)
    # Threshold at 128: pixels < 128 (dark) → black, >= 128 (light) → white
    bw = img.point(lambda x: 0 if x < 128 else 255, mode="L")
    return bw.convert("1", dither=Image.Dither.NONE)
