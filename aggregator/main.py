"""
TRMNL Dashboard Aggregator
Fetches data from HA, Open-Meteo, Jolpica F1 API, ESPN, and Google Calendar.
Implements the TRMNL BYOS /api/display protocol directly — no Inker required.
Renders 1872×1404 PNG images with Pillow (ARM64 native).
APScheduler refreshes data caches on configurable TTLs.
"""
import asyncio
import hashlib
import io
import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from icalendar import Calendar
import recurring_ical_events
from dotenv import load_dotenv
from renderer import render_screen

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="TRMNL Aggregator", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────────────────
HA_URL = os.getenv("HA_URL", "http://192.168.86.69:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "37.6879"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "-121.7721"))
ICAL_URLS = [
    u.strip() for u in os.getenv("ICAL_URL", "").split(",")
    if u.strip() and u.strip() != "REPLACE_WITH_ICAL_URL"
]
ICAL_LABELS = [
    l.strip() for l in os.getenv("ICAL_URL_LABELS", "").split(",")
    if l.strip()
]
TRMNL_ACCESS_TOKEN = os.getenv("TRMNL_ACCESS_TOKEN", "")
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "").rstrip("/")

PACIFIC = ZoneInfo("America/Los_Angeles")

# Apple Calendar JSON feed (synced from Mac Mini every 15 min by calendar-sync.py)
APPLE_CAL_JSON_PATH = "/data/calendar-events.json"
APPLE_CAL_MAX_AGE   = 1800  # 30 minutes; fall back to iCal if staler than this

# Playlist rotation: screens cycle in this order
PLAYLIST = ["main", "ha", "weather", "sports_all", "calendar"]

TTL_HA       = int(os.getenv("CACHE_TTL_HA",       "300"))
TTL_CALENDAR = int(os.getenv("CACHE_TTL_CALENDAR", "900"))
TTL_WEATHER  = int(os.getenv("CACHE_TTL_WEATHER",  "1800"))
TTL_SPORTS   = int(os.getenv("CACHE_TTL_SPORTS",   "1800"))
TTL_MAIN     = int(os.getenv("CACHE_TTL_MAIN",     "900"))

# F1 API (Jolpica — Ergast mirror)
JOLPICA_F1_URL = "https://api.jolpi.ca/ergast/f1/current/next.json"

# Soccer competitions to query per club
LEAGUE_DISPLAY = {
    "eng.1":                 "PL",
    "mlb":                   "MLB",
    "nfl":                   "NFL",
}

# Map playlist screen → (cache key, ttl)
_SCREEN_CACHE: dict[str, tuple[str, int]] = {
    "ha":          ("ha",          TTL_HA),
    "weather":     ("weather",     TTL_WEATHER),
    "sports_all":  ("sports_all",  TTL_SPORTS),
    "calendar":    ("calendar",    TTL_CALENDAR),
    "main":        ("main",        TTL_MAIN),
}

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[str, dict[str, Any]] = {}

def _set(key: str, data: Any) -> None:
    _cache[key] = {"data": data, "ts": time.time()}

def _get(key: str, ttl: int) -> Any | None:
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["data"]
    return None

def _age(key: str) -> str:
    entry = _cache.get(key)
    if not entry:
        return "never"
    secs = int(time.time() - entry["ts"])
    return f"{secs}s ago"

# ── Pre-render cache ──────────────────────────────────────────────────────────
_pre_render_cache: dict[str, bytes] = {}

async def pre_render_all_screens() -> None:
    """Pre-render all playlist screens and cache PNG bytes for instant serving."""
    rendered = 0
    for screen in PLAYLIST:
        try:
            cache_key, ttl = _SCREEN_CACHE[screen]
            data = _get(cache_key, ttl * 4) or {}
            img = render_screen(screen, data)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            _pre_render_cache[screen] = buf.getvalue()
            rendered += 1
        except Exception as e:
            log.error(f"Pre-render failed for {screen}: {e}")
    log.info(f"Pre-rendered {rendered}/{len(PLAYLIST)} screens")

# ── Time helpers ──────────────────────────────────────────────────────────────
def _to_pt(dt_str: str) -> datetime | None:
    """Parse UTC ISO string, return datetime in Pacific time."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.astimezone(PACIFIC)
    except Exception:
        return None

# ── Fetchers ──────────────────────────────────────────────────────────────────
async def fetch_ha() -> dict:
    if not HA_TOKEN:
        log.warning("HA_TOKEN not set — skipping HA fetch")
        return {"error": "HA_TOKEN not configured"}
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    domains = ["binary_sensor", "sensor", "switch", "light", "lock", "cover", "alarm_control_panel", "person"]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{HA_URL}/api/states", headers=headers)
        resp.raise_for_status()
        all_states = resp.json()

    filtered = []
    for state in all_states:
        domain = state["entity_id"].split(".")[0]
        if domain in domains:
            filtered.append({
                "entity_id": state["entity_id"],
                "state": state["state"],
                "name": state["attributes"].get("friendly_name", state["entity_id"]),
                "unit": state["attributes"].get("unit_of_measurement"),
                "device_class": state["attributes"].get("device_class"),
                "last_changed": state["last_changed"],
            })

    lights_on    = sum(1 for e in filtered if e["entity_id"].startswith("light.") and e["state"] == "on")
    switches_on  = sum(1 for e in filtered if e["entity_id"].startswith("switch.") and e["state"] == "on")
    locks_locked = sum(1 for e in filtered if e["entity_id"].startswith("lock.") and e["state"] == "locked")
    locks_total  = sum(1 for e in filtered if e["entity_id"].startswith("lock."))
    doors_open   = sum(1 for e in filtered if e["device_class"] in ("door", "garage_door") and e["state"] == "on")
    alarms       = [e for e in filtered if e["entity_id"].startswith("alarm_control_panel.")]

    return {
        "summary": {
            "lights_on":    lights_on,
            "switches_on":  switches_on,
            "locks_locked": f"{locks_locked}/{locks_total}",
            "doors_open":   doors_open,
            "alarm":        alarms[0]["state"] if alarms else "unknown",
        },
        "entities": filtered,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_weather() -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        f"precipitation,weather_code,wind_speed_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
        f"&timezone=America%2FLos_Angeles&forecast_days=5"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    wmo_codes = {
        0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
        45: "Foggy", 48: "Icy Fog", 51: "Light Drizzle", 53: "Drizzle",
        55: "Heavy Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
        71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow Grains",
        80: "Showers", 81: "Heavy Showers", 82: "Violent Showers",
        85: "Snow Showers", 86: "Heavy Snow Showers",
        95: "Thunderstorm", 96: "Thunderstorm+Hail", 99: "Thunderstorm+Heavy Hail",
    }

    cur = data["current"]
    daily = data["daily"]

    forecast = []
    for i in range(len(daily["time"])):
        forecast.append({
            "date": daily["time"][i],
            "condition": wmo_codes.get(daily["weather_code"][i], "Unknown"),
            "high": daily["temperature_2m_max"][i],
            "low": daily["temperature_2m_min"][i],
            "precip_in": daily["precipitation_sum"][i],
        })

    return {
        "current": {
            "temp_f":       cur["temperature_2m"],
            "feels_like_f": cur["apparent_temperature"],
            "humidity_pct": cur["relative_humidity_2m"],
            "wind_mph":     cur["wind_speed_10m"],
            "precip_in":    cur["precipitation"],
            "condition":    wmo_codes.get(cur["weather_code"], "Unknown"),
        },
        "forecast": forecast,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Sports: F1 ────────────────────────────────────────────────────────────────
async def fetch_sports_f1() -> dict:
    """Fetch next F1 race weekend from Jolpica (Ergast mirror)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(JOLPICA_F1_URL)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.error(f"F1 fetch failed: {e}")
        return {"error": str(e), "sessions": []}

    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return {"error": "No upcoming F1 race found", "sessions": []}

    race = races[0]

    session_defs = [
        ("FirstPractice",    "P1"),
        ("SecondPractice",   "P2"),
        ("ThirdPractice",    "P3"),
        ("SprintQualifying", "Sprint Qual"),
        ("Sprint",           "Sprint Race"),
        ("Qualifying",       "Qualifying"),
    ]

    sessions = []
    for key, label in session_defs:
        s = race.get(key)
        if not s:
            continue
        raw = f"{s['date']}T{s.get('time', '00:00:00Z')}"
        dt = _to_pt(raw)
        if dt:
            sessions.append({
                "name":         label,
                "sort_key":     raw,
                "display_date": dt.strftime("%a %b %-d"),
                "display_time": dt.strftime("%-I:%M %p PT"),
                "past":         dt < datetime.now(PACIFIC),
            })

    raw_race = f"{race.get('date', '')}T{race.get('time', '00:00:00Z')}"
    dt_race = _to_pt(raw_race)
    if dt_race:
        sessions.append({
            "name":         "Race",
            "sort_key":     raw_race,
            "display_date": dt_race.strftime("%a %b %-d"),
            "display_time": dt_race.strftime("%-I:%M %p PT"),
            "past":         dt_race < datetime.now(PACIFIC),
        })

    sessions.sort(key=lambda s: s["sort_key"])
    for s in sessions:
        del s["sort_key"]

    return {
        "race_name": race.get("raceName", ""),
        "round":     race.get("round", "?"),
        "season":    race.get("season", ""),
        "sessions":  sessions,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Sports: ESPN helpers ───────────────────────────────────────────────────────
async def _scoreboard_team_games(
    client: httpx.AsyncClient,
    sport: str,
    league: str,
    team_id: str,
    days_ahead: int = 45,
    max_games: int = 8,
) -> list[dict]:
    """
    Query ESPN scoreboard for a date range and filter upcoming games for a team.
    More reliable than the team schedule endpoint which caps out on future events.
    """
    today  = datetime.now(PACIFIC).strftime("%Y%m%d")
    future = (datetime.now(PACIFIC) + timedelta(days=days_ahead)).strftime("%Y%m%d")
    url    = (
        f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
        f"?dates={today}-{future}"
    )
    try:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning(f"ESPN scoreboard {sport}/{league} failed: {e}")
        return []

    now_utc = datetime.now(timezone.utc)
    results = []

    for event in data.get("events", []):
        competition = (event.get("competitions") or [{}])[0]
        status_type = competition.get("status", {}).get("type", {})
        if status_type.get("completed", False):
            continue

        competitors = competition.get("competitors", [])
        if not any(c["team"]["id"] == team_id for c in competitors):
            continue

        date_str = event.get("date", "")
        try:
            dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt_utc < now_utc - timedelta(hours=6):
            continue

        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)

        is_home  = bool(home and home["team"]["id"] == team_id)
        opponent = home if not is_home else away
        opp_name = opponent["team"]["displayName"] if opponent else "TBD"
        opp_abbr = opponent["team"].get("abbreviation", "") if opponent else ""

        pt = dt_utc.astimezone(PACIFIC)

        results.append({
            "date_iso":      dt_utc.isoformat(),
            "display_date":  pt.strftime("%a %b %-d"),
            "display_time":  pt.strftime("%-I:%M %p"),
            "opponent":      opp_name,
            "opponent_abbr": opp_abbr,
            "is_home":       is_home,
            "venue_flag":    "vs" if is_home else "@",
            "competition":   LEAGUE_DISPLAY.get(league, league.upper()),
        })

        if len(results) >= max_games:
            break

    return results


def _detect_series(games: list[dict]) -> list[dict]:
    """Group consecutive games against the same opponent as a series."""
    if not games:
        return []
    series_list: list[dict] = []
    i = 0
    while i < len(games):
        opp = games[i]["opponent"]
        grp = [games[i]]
        j = i + 1
        while j < len(games) and games[j]["opponent"] == opp:
            grp.append(games[j])
            j += 1
        series_list.append({
            "opponent":   opp,
            "venue_flag": grp[0]["venue_flag"],
            "is_home":    grp[0]["is_home"],
            "num_games":  len(grp),
            "start_date": grp[0]["display_date"],
            "end_date":   grp[-1]["display_date"],
            "games":      grp,
        })
        i = j
    return series_list


# ── Sports: US ────────────────────────────────────────────────────────────────
async def fetch_sports_us() -> dict:
    """Fetch upcoming SF Giants (series view) and SF 49ers games."""
    async with httpx.AsyncClient(timeout=15) as client:
        giants_games, niners_games = await asyncio.gather(
            # Giants ESPN team ID = 26; query scoreboard for upcoming 30 days
            _scoreboard_team_games(client, "baseball", "mlb", "26", days_ahead=30, max_games=12),
            # 49ers ESPN team ID = 25; NFL off-season Apr–Jul; show next 3 if any
            _scoreboard_team_games(client, "football", "nfl", "25", days_ahead=180, max_games=3),
        )

    giants_series = _detect_series(giants_games)[:2]  # show next 2 series

    return {
        "giants": {"label": "SF Giants",   "series": giants_series},
        "niners": {"label": "SF 49ers",    "games":  niners_games[:3]},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Sports: Soccer ────────────────────────────────────────────────────────────
async def fetch_sports_soccer() -> dict:
    """
    Fetch upcoming Tottenham and Man City games from the EPL scoreboard.
    UCL/FA Cup are not accessible through ESPN's public scoreboard API;
    EPL covers the most relevant remaining fixtures (April–May run-in).
    """
    async with httpx.AsyncClient(timeout=15) as client:
        spurs_games, city_games = await asyncio.gather(
            _scoreboard_team_games(client, "soccer", "eng.1", "367", days_ahead=60, max_games=5),
            _scoreboard_team_games(client, "soccer", "eng.1", "382", days_ahead=60, max_games=5),
        )

    return {
        "spurs":   {"label": "Tottenham Hotspur", "games": spurs_games},
        "mancity": {"label": "Manchester City",   "games": city_games},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Calendar ──────────────────────────────────────────────────────────────────
async def fetch_calendar() -> dict:
    # ── Primary: Apple Calendar JSON synced from Mac Mini ─────────────────────
    try:
        if os.path.exists(APPLE_CAL_JSON_PATH):
            age = time.time() - os.stat(APPLE_CAL_JSON_PATH).st_mtime
            if age < APPLE_CAL_MAX_AGE:
                with open(APPLE_CAL_JSON_PATH) as f:
                    data = json.load(f)
                log.info(f"Using Apple Calendar JSON (age {int(age)}s, {len(data.get('events', []))} events)")
                return data
            else:
                log.warning(f"Apple Calendar JSON is stale ({int(age)}s), falling back to iCal")
        else:
            log.info("Apple Calendar JSON not found, falling back to iCal")
    except Exception as e:
        log.warning(f"Apple Calendar JSON read error: {e}, falling back to iCal")

    # ── Fallback: iCal URL fetching ────────────────────────────────────────────
    if not ICAL_URLS:
        return {"error": "No calendar source available (JSON missing/stale, ICAL_URL not set)", "events": []}

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=14)
    all_events = []

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for idx, raw_url in enumerate(ICAL_URLS):
            # Convert webcal:// to https:// (Apple Calendar / iCloud uses webcal://)
            url = raw_url.replace("webcal://", "https://")
            cal_label = ICAL_LABELS[idx] if idx < len(ICAL_LABELS) else None
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                cal = Calendar.from_ical(resp.content)
                # recurring_ical_events expands RRULE recurring events in the window
                for component in recurring_ical_events.of(cal).between(now, window_end):
                    dtstart = component.get("DTSTART")
                    if not dtstart:
                        continue
                    start = dtstart.dt
                    all_day = not hasattr(start, "hour")
                    if all_day:
                        start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
                    elif start.tzinfo is None:
                        start = start.replace(tzinfo=timezone.utc)

                    dtend = component.get("DTEND")
                    end = dtend.dt if dtend else None
                    if end is not None:
                        if not hasattr(end, "hour"):
                            end = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
                        elif end.tzinfo is None:
                            end = end.replace(tzinfo=timezone.utc)

                    all_events.append({
                        "summary":  str(component.get("SUMMARY", "")),
                        "start":    start.isoformat(),
                        "end":      end.isoformat() if end else None,
                        "location": str(component.get("LOCATION", "")) or None,
                        "all_day":  all_day,
                        "calendar": cal_label,
                    })
            except Exception as e:
                log.warning(f"Failed to fetch iCal {raw_url}: {e}")

    all_events.sort(key=lambda e: e["start"])
    return {
        "events": all_events[:20],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Scheduled refresh ─────────────────────────────────────────────────────────
async def refresh_ha():
    try:
        _set("ha", await fetch_ha())
        log.info("HA cache refreshed")
    except Exception as e:
        log.error(f"HA refresh failed: {e}")

async def refresh_weather():
    try:
        _set("weather", await fetch_weather())
        log.info("Weather cache refreshed")
    except Exception as e:
        log.error(f"Weather refresh failed: {e}")

async def refresh_sports_f1():
    try:
        _set("sports_f1", await fetch_sports_f1())
        log.info("Sports F1 cache refreshed")
    except Exception as e:
        log.error(f"Sports F1 refresh failed: {e}")

async def refresh_sports_us():
    try:
        _set("sports_us", await fetch_sports_us())
        log.info("Sports US cache refreshed")
    except Exception as e:
        log.error(f"Sports US refresh failed: {e}")

async def refresh_sports_soccer():
    try:
        _set("sports_soccer", await fetch_sports_soccer())
        log.info("Sports Soccer cache refreshed")
    except Exception as e:
        log.error(f"Sports Soccer refresh failed: {e}")

async def refresh_sports_all():
    """Assemble combined sports data from the three individual caches."""
    try:
        f1_data = _get("sports_f1",    TTL_SPORTS * 4)
        us_data = _get("sports_us",    TTL_SPORTS * 4)
        sc_data = _get("sports_soccer",TTL_SPORTS * 4)
        tasks = []
        if f1_data is None:
            tasks.append(refresh_sports_f1())
        if us_data is None:
            tasks.append(refresh_sports_us())
        if sc_data is None:
            tasks.append(refresh_sports_soccer())
        if tasks:
            await asyncio.gather(*tasks)
            f1_data = _get("sports_f1",    TTL_SPORTS * 4) or {}
            us_data = _get("sports_us",    TTL_SPORTS * 4) or {}
            sc_data = _get("sports_soccer",TTL_SPORTS * 4) or {}
        combined = {
            "f1":      f1_data or {},
            "giants":  (us_data or {}).get("giants", {}),
            "niners":  (us_data or {}).get("niners", {}),
            "spurs":   (sc_data or {}).get("spurs", {}),
            "mancity": (sc_data or {}).get("mancity", {}),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        _set("sports_all", combined)
        log.info("Sports All cache refreshed")
    except Exception as e:
        log.error(f"Sports All refresh failed: {e}")

async def refresh_calendar():
    try:
        _set("calendar", await fetch_calendar())
        log.info("Calendar cache refreshed")
    except Exception as e:
        log.error(f"Calendar refresh failed: {e}")

async def refresh_main():
    try:
        combined = {
            "weather":   _get("weather",   TTL_WEATHER  * 4) or await fetch_weather(),
            "sports_us": _get("sports_us", TTL_SPORTS   * 4) or await fetch_sports_us(),
            "sports_f1": _get("sports_f1", TTL_SPORTS   * 4) or await fetch_sports_f1(),
            "calendar":  _get("calendar",  TTL_CALENDAR * 4) or await fetch_calendar(),
        }
        _set("main", combined)
        log.info("Main dashboard cache refreshed")
    except Exception as e:
        log.error(f"Main refresh failed: {e}")


scheduler = AsyncIOScheduler()

# ── Static image cache ─────────────────────────────────────────────────────────
_static_images: dict[str, bytes] = {}

def _build_welcome_image() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("L", (1872, 1404), 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 1872, 120], fill=0)
    draw.text((40, 35), "TRMNL X — Setup Complete", fill=255)
    draw.text((40, 300), "Connected to local BYOS server.", fill=0)
    draw.text((40, 380), "Display will update shortly.", fill=0)
    mono = img.convert("1")
    buf = io.BytesIO()
    mono.save(buf, format="PNG")
    return buf.getvalue()

def _build_error_image(message: str = "Render error — retrying next cycle") -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("L", (1872, 1404), 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 1872, 120], fill=0)
    draw.text((40, 35), "TRMNL — Display Error", fill=255)
    draw.text((40, 300), message[:80], fill=0)
    draw.text((40, 380), "Will retry on next refresh cycle.", fill=0)
    mono = img.convert("1")
    buf = io.BytesIO()
    mono.save(buf, format="PNG")
    return buf.getvalue()


@app.on_event("startup")
async def startup():
    scheduler.add_job(refresh_ha,             "interval", seconds=TTL_HA,      id="ha")
    scheduler.add_job(refresh_weather,        "interval", seconds=TTL_WEATHER,  id="weather")
    scheduler.add_job(refresh_sports_f1,      "interval", seconds=TTL_SPORTS,   id="sports_f1")
    scheduler.add_job(refresh_sports_us,      "interval", seconds=TTL_SPORTS,   id="sports_us")
    scheduler.add_job(refresh_sports_soccer,  "interval", seconds=TTL_SPORTS,   id="sports_soccer")
    scheduler.add_job(refresh_sports_all,     "interval", seconds=TTL_SPORTS,   id="sports_all")
    scheduler.add_job(refresh_calendar,       "interval", seconds=TTL_CALENDAR, id="calendar")
    scheduler.add_job(refresh_main,           "interval", seconds=TTL_MAIN,     id="main")
    scheduler.add_job(pre_render_all_screens, "interval", seconds=600,          id="pre_render")
    scheduler.start()

    # Warm caches on boot
    await refresh_weather()
    await asyncio.gather(refresh_sports_f1(), refresh_sports_us(), refresh_sports_soccer())
    await refresh_sports_all()
    await refresh_calendar()
    await refresh_main()
    await refresh_ha()
    await pre_render_all_screens()

    try:
        _static_images["welcome.png"] = _build_welcome_image()
        log.info("Welcome image generated")
    except Exception as e:
        log.error(f"Failed to generate welcome image: {e}")
    try:
        _static_images["error.png"] = _build_error_image()
        log.info("Error fallback image generated")
    except Exception as e:
        log.error(f"Failed to generate error image: {e}")

    log.info("Aggregator started — all caches warmed")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()


# ── Base URL helper ────────────────────────────────────────────────────────────
def _base_url(request: Request) -> str:
    if SERVER_BASE_URL:
        return SERVER_BASE_URL
    return str(request.base_url).rstrip("/")


# ── API Endpoints ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "cache_ages": {k: _age(k) for k in ["ha", "weather", "sports_f1", "sports_us", "sports_soccer", "sports_all", "calendar"]},
        "pre_rendered_screens": list(_pre_render_cache.keys()),
        "server_base_url": SERVER_BASE_URL or "(auto from Host header)",
    }

@app.get("/data/ha")
async def data_ha():
    return _get("ha", TTL_HA * 2) or await fetch_ha()

@app.get("/data/weather")
async def data_weather():
    return _get("weather", TTL_WEATHER * 2) or await fetch_weather()

@app.get("/data/sports/f1")
async def data_sports_f1():
    return _get("sports_f1", TTL_SPORTS * 2) or await fetch_sports_f1()

@app.get("/data/sports/us")
async def data_sports_us():
    return _get("sports_us", TTL_SPORTS * 2) or await fetch_sports_us()

@app.get("/data/sports/soccer")
async def data_sports_soccer():
    return _get("sports_soccer", TTL_SPORTS * 2) or await fetch_sports_soccer()

@app.get("/data/calendar")
async def data_calendar():
    return _get("calendar", TTL_CALENDAR * 2) or await fetch_calendar()

@app.get("/data/main")
async def data_main():
    return _get("main", TTL_MAIN * 2) or {}

@app.post("/refresh/{source}")
async def manual_refresh(source: str):
    refreshers = {
        "ha":           refresh_ha,
        "weather":      refresh_weather,
        "sports_f1":    refresh_sports_f1,
        "sports_us":    refresh_sports_us,
        "sports_soccer":refresh_sports_soccer,
        "sports_all":   refresh_sports_all,
        "calendar":     refresh_calendar,
        "main":         refresh_main,
        "pre_render":   pre_render_all_screens,
    }
    if source not in refreshers:
        raise HTTPException(404, f"Unknown source: {source}. Valid: {list(refreshers)}")
    await refreshers[source]()
    return {"status": "refreshed", "source": source, "age": _age(source)}


# ── TRMNL BYOS Protocol ───────────────────────────────────────────────────────
_device_state: dict[str, int] = {}
_image_cache: dict[str, bytes] = {}


@app.get("/api/setup")
async def trmnl_setup(request: Request):
    device_id = request.headers.get("ID") or request.headers.get("X-Device-ID", "unknown")
    log.info(f"TRMNL setup request from device {device_id}")
    api_key = TRMNL_ACCESS_TOKEN if TRMNL_ACCESS_TOKEN else "byos-local-key"
    friendly_id = device_id.replace(":", "")[-6:].upper() if device_id != "unknown" else "BYOS01"
    base_url = _base_url(request)
    return {
        "status": 200,
        "api_key": api_key,
        "friendly_id": friendly_id,
        "image_url": f"{base_url}/images/welcome.png",
        "filename": "setup_complete",
        "message": "Connected to local BYOS server",
    }


@app.get("/api/display")
async def trmnl_display(request: Request):
    """
    TRMNL BYOS /api/display endpoint.
    Must always return HTTP 200 — non-200 shows firmware error on device.
    """
    device_id = request.headers.get("ID") or request.headers.get("X-Device-ID", "unknown")
    token = request.headers.get("Access-Token", "")

    if TRMNL_ACCESS_TOKEN and token != TRMNL_ACCESS_TOKEN:
        log.warning(f"TRMNL device {device_id} sent wrong token: '{token}'")
        base_url = _base_url(request)
        return JSONResponse({
            "status": 0,
            "image_url": f"{base_url}/images/error.png",
            "filename": "error.png",
            "refresh_rate": 300,
            "update_firmware": False,
            "firmware_url": "",
            "reset_firmware": False,
            "image_url_timeout": 0,
        })

    log.info(f"TRMNL display request from device {device_id}")

    idx = _device_state.get(device_id, -1)
    idx = (idx + 1) % len(PLAYLIST)
    _device_state[device_id] = idx
    screen = PLAYLIST[idx]

    cache_key, ttl = _SCREEN_CACHE[screen]
    data = _get(cache_key, ttl * 2) or {}

    base_url = _base_url(request)

    pre_rendered = _pre_render_cache.get(screen)
    if pre_rendered:
        img_bytes = pre_rendered
        filename  = f"{screen}-{hashlib.md5(img_bytes).hexdigest()[:8]}.png"
        log.debug(f"Serving pre-rendered {screen}")
    else:
        log.info(f"No pre-render for {screen}, rendering on demand")
        try:
            img = render_screen(screen, data)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            filename  = f"{screen}-{hashlib.md5(img_bytes).hexdigest()[:8]}.png"
        except Exception as e:
            log.error(f"Render failed for {screen}: {e}")
            filename  = "error.png"
            img_bytes = _static_images.get("error.png") or _build_error_image(str(e)[:80])

    _image_cache[filename] = img_bytes

    if len(_image_cache) > 20:
        pruneable = [k for k in list(_image_cache.keys()) if k not in _static_images]
        for k in pruneable[:-20]:
            del _image_cache[k]

    image_url = f"{base_url}/images/{filename}"
    log.info(f"Serving {screen} → {filename} to device {device_id}")

    return JSONResponse({
        "status": 0,
        "image_url": image_url,
        "filename": filename,
        "refresh_rate": ttl,
        "update_firmware": False,
        "firmware_url": "",
        "reset_firmware": False,
        "image_url_timeout": 0,
    })


@app.get("/images/{filename}")
async def serve_image(filename: str):
    img_data = _static_images.get(filename) or _image_cache.get(filename)
    if not img_data:
        raise HTTPException(404, "Image not found or expired")
    return Response(content=img_data, media_type="image/png")
