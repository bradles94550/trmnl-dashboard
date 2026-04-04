"""
PNG renderer for TRMNL X (1872×1404, 2-bit grayscale).
Uses Pillow only — no browser required, ARM64 native.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# TRMNL X native resolution
WIDTH = 1872
HEIGHT = 1404
BG = 255   # white
FG = 0     # black
GRAY = 128

# Try to load a monospace font; fall back to PIL default
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _new_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    return img, draw


def _header(draw: ImageDraw.ImageDraw, title: str, subtitle: str = "") -> int:
    """Draw a header bar. Returns the y offset after the header."""
    draw.rectangle([0, 0, WIDTH, 80], fill=FG)
    f_title = _font(40)
    f_sub = _font(24)
    draw.text((20, 18), title, font=f_title, fill=BG)
    if subtitle:
        bbox = draw.textbbox((0, 0), title, font=f_title)
        x_off = bbox[2] + 20
        draw.text((x_off, 28), subtitle, font=f_sub, fill=200)
    return 100


def _footer(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.line([0, HEIGHT - 40, WIDTH, HEIGHT - 40], fill=GRAY, width=1)
    f = _font(20)
    draw.text((20, HEIGHT - 35), text, font=f, fill=GRAY)


def render_ha(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "🏠  Home Status", datetime.now().strftime("%a %b %-d, %-I:%M %p"))
    f_label = _font(24)
    f_value = _font(60)
    f_entity = _font(22)

    if "error" in data:
        draw.text((40, y + 20), f"⚠  {data['error']}", font=_font(32), fill=FG)
        _footer(draw, "Configure HA_TOKEN in .env")
        return img

    summary = data.get("summary", {})
    stats = [
        ("Lights On", str(summary.get("lights_on", "?"))),
        ("Locks",     str(summary.get("locks_locked", "?/?"))),
        ("Doors Open", str(summary.get("doors_open", "?"))),
        ("Alarm",     str(summary.get("alarm", "?"))),
    ]

    col_w = WIDTH // 4
    for i, (label, val) in enumerate(stats):
        x = i * col_w + 30
        draw.text((x, y + 10), label.upper(), font=f_label, fill=GRAY)
        draw.text((x, y + 40), val, font=f_value, fill=FG)

    # Entity list below stats
    y2 = y + 130
    draw.line([0, y2, WIDTH, y2], fill=GRAY, width=1)
    y2 += 12
    col2_w = WIDTH // 2
    entities = data.get("entities", [])[:30]
    for idx, ent in enumerate(entities):
        col = idx % 2
        row = idx // 2
        x = col * col2_w + 20
        ey = y2 + row * 30
        if ey + 30 > HEIGHT - 50:
            break
        name = ent.get("name", ent["entity_id"])[:35]
        state = ent.get("state", "")
        unit = ent.get("unit") or ""
        draw.text((x, ey), f"{name}: {state} {unit}".strip(), font=f_entity, fill=FG)

    _footer(draw, f"Updated {data.get('fetched_at', '')[:19]}Z")
    return img


def render_weather(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "⛅  Weather", datetime.now().strftime("%a %b %-d"))
    f_huge = _font(90)
    f_large = _font(36)
    f_med = _font(28)
    f_small = _font(22)

    if "error" in data:
        draw.text((40, y + 20), f"⚠  {data['error']}", font=_font(32), fill=FG)
        return img

    cur = data.get("current", {})
    temp = cur.get("temp_f", "--")
    feels = cur.get("feels_like_f", "--")
    cond = cur.get("condition", "")
    hum = cur.get("humidity_pct", "--")
    wind = cur.get("wind_mph", "--")

    draw.text((40, y + 10), f"{temp}°F", font=f_huge, fill=FG)
    draw.text((40, y + 110), cond, font=f_large, fill=FG)
    draw.text((40, y + 158), f"Feels like {feels}°  |  Humidity {hum}%  |  Wind {wind} mph", font=f_med, fill=GRAY)

    # 5-day forecast grid
    forecast = data.get("forecast", [])[:5]
    y3 = y + 220
    draw.line([0, y3, WIDTH, y3], fill=GRAY, width=1)
    y3 += 20
    col_w = WIDTH // max(len(forecast), 1)

    for i, day in enumerate(forecast):
        x = i * col_w + 20
        date_str = day.get("date", "")
        label = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %-d") if date_str else "?"
        hi = day.get("high", "--")
        lo = day.get("low", "--")
        cond_d = day.get("condition", "")[:10]
        precip = day.get("precip_in", 0)

        draw.text((x, y3), label, font=f_med, fill=FG)
        draw.text((x, y3 + 40), cond_d, font=f_small, fill=GRAY)
        draw.text((x, y3 + 70), f"{int(hi) if isinstance(hi, float) else hi}° / {int(lo) if isinstance(lo, float) else lo}°", font=f_med, fill=FG)
        if isinstance(precip, (int, float)) and precip > 0.01:
            draw.text((x, y3 + 110), f"💧 {precip:.2f}\"", font=f_small, fill=GRAY)

        if i > 0:
            draw.line([x - 20, y3 - 10, x - 20, y3 + 140], fill=200, width=1)

    _footer(draw, f"Open-Meteo  •  Updated {data.get('fetched_at', '')[:19]}Z")
    return img


def render_sports(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    league = data.get("league", "Sports")
    y = _header(draw, f"🏀  {league} Scores", datetime.now().strftime("%a %b %-d"))
    f_large = _font(36)
    f_med = _font(28)
    f_small = _font(22)

    if "error" in data:
        draw.text((40, y + 20), f"⚠  {data['error']}", font=_font(32), fill=FG)
        return img

    today = data.get("today", [])
    tomorrow = data.get("tomorrow", [])

    if not today:
        draw.text((40, y + 30), "No games today", font=f_large, fill=GRAY)
    else:
        draw.text((20, y + 5), "TODAY", font=_font(24), fill=GRAY)
        y += 35
        # Column headers
        draw.text((20, y), "Away", font=f_small, fill=GRAY)
        draw.text((WIDTH // 2 - 60, y), "Score", font=f_small, fill=GRAY)
        draw.text((WIDTH // 2 + 40, y), "Home", font=f_small, fill=GRAY)
        draw.text((WIDTH - 200, y), "Status", font=f_small, fill=GRAY)
        y += 30
        draw.line([0, y, WIDTH, y], fill=GRAY, width=1)
        y += 8

        for game in today[:8]:
            bold = game.get("our_team") is not None
            color = FG if bold else 80
            away_score = game.get("away_score", "")
            home_score = game.get("home_score", "")
            score_str = f"{away_score} – {home_score}" if game.get("completed") else "vs"
            status = game.get("status", "")[:12]

            draw.text((20, y), game["away_team"][:20], font=f_med, fill=color)
            draw.text((WIDTH // 2 - 80, y), score_str, font=f_med, fill=FG)
            draw.text((WIDTH // 2 + 40, y), game["home_team"][:20], font=f_med, fill=color)
            draw.text((WIDTH - 200, y), status, font=f_small, fill=GRAY)
            y += 38

    if tomorrow:
        y += 10
        draw.line([0, y, WIDTH, y], fill=GRAY, width=1)
        y += 10
        draw.text((20, y), "TOMORROW", font=_font(24), fill=GRAY)
        y += 30
        for game in tomorrow[:4]:
            bold = game.get("has_our_team")
            draw.text((40, y), game["name"][:50], font=f_small, fill=FG if bold else 80)
            y += 28

    _footer(draw, f"ESPN  •  Updated {data.get('fetched_at', '')[:19]}Z")
    return img


def render_calendar(data: dict[str, Any]) -> Image.Image:
    img, draw = _new_canvas()
    y = _header(draw, "📅  Family Calendar", datetime.now().strftime("%a %b %-d"))
    f_date = _font(22)
    f_title = _font(30)
    f_loc = _font(20)

    if "error" in data:
        draw.text((40, y + 20), f"⚠  {data['error']}", font=_font(32), fill=FG)
        return img

    events = data.get("events", [])
    if not events:
        draw.text((40, y + 30), "No upcoming events in the next 14 days", font=_font(32), fill=GRAY)
        _footer(draw, "Configure ICAL_URL in .env")
        return img

    last_date = None
    for event in events[:12]:
        start = event.get("start", "")
        date_str = start[:10]
        time_str = "" if event.get("all_day") else start[11:16]
        summary = event.get("summary", "No title")[:50]
        location = event.get("location")

        # Date header if new day
        if date_str != last_date:
            if last_date is not None:
                draw.line([0, y, WIDTH, y], fill=200, width=1)
                y += 4
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                label = d.strftime("%A, %B %-d")
            except ValueError:
                label = date_str
            draw.text((20, y + 4), label, font=_font(26), fill=GRAY)
            y += 36
            last_date = date_str

        if y + 50 > HEIGHT - 50:
            draw.text((20, y), "…more events not shown", font=f_date, fill=GRAY)
            break

        # Event row
        time_label = time_str if time_str else "All day"
        draw.text((20, y), time_label, font=f_date, fill=GRAY)
        draw.text((130, y), summary, font=f_title, fill=FG)
        y += 34
        if location:
            draw.text((130, y), f"📍 {location[:50]}", font=f_loc, fill=GRAY)
            y += 26

    _footer(draw, f"Updated {data.get('fetched_at', '')[:19]}Z")
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
    # Convert to 2-bit grayscale (TRMNL X native)
    return img.convert("1").convert("L")
