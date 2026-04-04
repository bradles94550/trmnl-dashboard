"""
TRMNL Dashboard Aggregator
Fetches data from HA, Open-Meteo, ESPN, and Google Calendar.
Implements the TRMNL BYOS /api/display protocol directly — no Inker required.
Renders 1872×1404 PNG images with Pillow (ARM64 native).
APScheduler refreshes data caches on configurable TTLs.
"""
import hashlib
import io
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from icalendar import Calendar
from dotenv import load_dotenv
from renderer import render_screen

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="TRMNL Aggregator", version="1.0.0")

# ── Config ────────────────────────────────────────────────────────────────────
HA_URL = os.getenv("HA_URL", "http://192.168.86.69:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "37.6879"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "-121.7721"))
ESPN_SPORT = os.getenv("ESPN_SPORT", "basketball")
ESPN_LEAGUE = os.getenv("ESPN_LEAGUE", "nba")
ESPN_TEAM_ID = os.getenv("ESPN_TEAM_ID", "11")
ICAL_URLS = [u.strip() for u in os.getenv("ICAL_URL", "").split(",") if u.strip()]
TRMNL_ACCESS_TOKEN = os.getenv("TRMNL_ACCESS_TOKEN", "")  # optional: set to enforce device auth

# Playlist rotation: screens cycle in this order
PLAYLIST = ["ha", "weather", "sports", "calendar"]
TTL_HA = int(os.getenv("CACHE_TTL_HA", "300"))
TTL_CALENDAR = int(os.getenv("CACHE_TTL_CALENDAR", "900"))
TTL_WEATHER = int(os.getenv("CACHE_TTL_WEATHER", "1800"))
TTL_SPORTS = int(os.getenv("CACHE_TTL_SPORTS", "1800"))

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

# ── Fetchers ──────────────────────────────────────────────────────────────────
async def fetch_ha() -> dict:
    if not HA_TOKEN:
        log.warning("HA_TOKEN not set — skipping HA fetch")
        return {"error": "HA_TOKEN not configured"}
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    # Fetch a curated set of entity domains — add more as needed
    domains = ["binary_sensor", "sensor", "switch", "light", "lock", "cover", "alarm_control_panel", "person"]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{HA_URL}/api/states", headers=headers)
        resp.raise_for_status()
        all_states = resp.json()

    # Filter to relevant entities and simplify
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

    # Quick summary stats
    lights_on = sum(1 for e in filtered if e["entity_id"].startswith("light.") and e["state"] == "on")
    switches_on = sum(1 for e in filtered if e["entity_id"].startswith("switch.") and e["state"] == "on")
    locks_locked = sum(1 for e in filtered if e["entity_id"].startswith("lock.") and e["state"] == "locked")
    locks_total = sum(1 for e in filtered if e["entity_id"].startswith("lock."))
    doors_open = sum(1 for e in filtered if e["device_class"] in ("door", "garage_door") and e["state"] == "on")
    alarms = [e for e in filtered if e["entity_id"].startswith("alarm_control_panel.")]

    return {
        "summary": {
            "lights_on": lights_on,
            "switches_on": switches_on,
            "locks_locked": f"{locks_locked}/{locks_total}",
            "doors_open": doors_open,
            "alarm": alarms[0]["state"] if alarms else "unknown",
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
            "temp_f": cur["temperature_2m"],
            "feels_like_f": cur["apparent_temperature"],
            "humidity_pct": cur["relative_humidity_2m"],
            "wind_mph": cur["wind_speed_10m"],
            "precip_in": cur["precipitation"],
            "condition": wmo_codes.get(cur["weather_code"], "Unknown"),
        },
        "forecast": forecast,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_sports() -> dict:
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports"
        f"/{ESPN_SPORT}/{ESPN_LEAGUE}/scoreboard"
        f"?dates={datetime.now().strftime('%Y%m%d')}"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    games = []
    for event in data.get("events", []):
        competition = event["competitions"][0]
        home = competition["competitors"][0]
        away = competition["competitors"][1]
        if home.get("homeAway") == "away":
            home, away = away, home

        our_team = None
        for comp in competition["competitors"]:
            if comp["team"].get("id") == ESPN_TEAM_ID:
                our_team = comp
                break

        status = competition["status"]["type"]
        games.append({
            "id": event["id"],
            "name": event["name"],
            "date": event["date"],
            "status": status["description"],
            "completed": status["completed"],
            "home_team": home["team"]["displayName"],
            "home_score": home.get("score"),
            "away_team": away["team"]["displayName"],
            "away_score": away.get("score"),
            "our_team": our_team["team"]["displayName"] if our_team else None,
            "our_score": our_team.get("score") if our_team else None,
            "our_winner": our_team.get("winner") if our_team else None,
        })

    # Also fetch tomorrow's schedule
    tomorrow_url = (
        f"https://site.api.espn.com/apis/site/v2/sports"
        f"/{ESPN_SPORT}/{ESPN_LEAGUE}/scoreboard"
        f"?dates={(datetime.now() + timedelta(days=1)).strftime('%Y%m%d')}"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp2 = await client.get(tomorrow_url)
        resp2.raise_for_status()
        tomorrow_data = resp2.json()

    tomorrow_games = []
    for event in tomorrow_data.get("events", []):
        competition = event["competitions"][0]
        has_our_team = any(
            c["team"].get("id") == ESPN_TEAM_ID
            for c in competition["competitors"]
        )
        tomorrow_games.append({
            "name": event["name"],
            "date": event["date"],
            "has_our_team": has_our_team,
        })

    return {
        "today": games,
        "tomorrow": tomorrow_games,
        "sport": ESPN_SPORT,
        "league": ESPN_LEAGUE.upper(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def fetch_calendar() -> dict:
    if not ICAL_URLS:
        return {"error": "ICAL_URL not configured", "events": []}

    now = datetime.now(timezone.utc)
    window_end = now + timedelta(days=14)
    all_events = []

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for url in ICAL_URLS:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                cal = Calendar.from_ical(resp.content)
                for component in cal.walk():
                    if component.name != "VEVENT":
                        continue
                    dtstart = component.get("DTSTART")
                    if not dtstart:
                        continue
                    start = dtstart.dt
                    # Handle date-only events
                    if not hasattr(start, "hour"):
                        start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
                    elif start.tzinfo is None:
                        start = start.replace(tzinfo=timezone.utc)

                    if now <= start <= window_end:
                        dtend = component.get("DTEND")
                        end = dtend.dt if dtend else None
                        if end and not hasattr(end, "hour"):
                            end = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
                        elif end and end.tzinfo is None:
                            end = end.replace(tzinfo=timezone.utc)

                        all_events.append({
                            "summary": str(component.get("SUMMARY", "")),
                            "start": start.isoformat(),
                            "end": end.isoformat() if end else None,
                            "location": str(component.get("LOCATION", "")) or None,
                            "all_day": not hasattr(dtstart.dt, "hour"),
                        })
            except Exception as e:
                log.warning(f"Failed to fetch iCal {url}: {e}")

    all_events.sort(key=lambda e: e["start"])

    return {
        "events": all_events[:20],  # next 20 events max
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

async def refresh_sports():
    try:
        _set("sports", await fetch_sports())
        log.info("Sports cache refreshed")
    except Exception as e:
        log.error(f"Sports refresh failed: {e}")

async def refresh_calendar():
    try:
        _set("calendar", await fetch_calendar())
        log.info("Calendar cache refreshed")
    except Exception as e:
        log.error(f"Calendar refresh failed: {e}")

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup():
    scheduler.add_job(refresh_ha, "interval", seconds=TTL_HA, id="ha")
    scheduler.add_job(refresh_weather, "interval", seconds=TTL_WEATHER, id="weather")
    scheduler.add_job(refresh_sports, "interval", seconds=TTL_SPORTS, id="sports")
    scheduler.add_job(refresh_calendar, "interval", seconds=TTL_CALENDAR, id="calendar")
    scheduler.start()
    # Warm the cache on boot
    await refresh_weather()
    await refresh_sports()
    await refresh_calendar()
    await refresh_ha()
    log.info("Aggregator started — all caches warmed")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()

# ── API Endpoints ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "cache_ages": {k: _age(k) for k in ["ha", "weather", "sports", "calendar"]},
    }

@app.get("/data/ha")
async def data_ha():
    data = _get("ha", TTL_HA * 2) or await fetch_ha()
    return data

@app.get("/data/weather")
async def data_weather():
    data = _get("weather", TTL_WEATHER * 2) or await fetch_weather()
    return data

@app.get("/data/sports")
async def data_sports():
    data = _get("sports", TTL_SPORTS * 2) or await fetch_sports()
    return data

@app.get("/data/calendar")
async def data_calendar():
    data = _get("calendar", TTL_CALENDAR * 2) or await fetch_calendar()
    return data

@app.post("/refresh/{source}")
async def manual_refresh(source: str):
    """Trigger an immediate cache refresh for a data source."""
    refreshers = {
        "ha": refresh_ha,
        "weather": refresh_weather,
        "sports": refresh_sports,
        "calendar": refresh_calendar,
    }
    if source not in refreshers:
        raise HTTPException(404, f"Unknown source: {source}. Valid: {list(refreshers)}")
    await refreshers[source]()
    return {"status": "refreshed", "source": source, "age": _age(source)}


# ── TRMNL BYOS Protocol ───────────────────────────────────────────────────────
# Device state: tracks which playlist screen each device is on
_device_state: dict[str, int] = {}

# Image cache: filename → PNG bytes (so /images/<filename> can serve it)
_image_cache: dict[str, bytes] = {}

@app.get("/api/display")
async def trmnl_display(request: Request):
    """
    TRMNL BYOS /api/display endpoint.
    Device sends: ID header (MAC), Access-Token header.
    Returns: JSON with image_url, filename, refresh_rate.
    """
    device_id = request.headers.get("ID") or request.headers.get("X-Device-ID", "unknown")
    token = request.headers.get("Access-Token", "")

    if TRMNL_ACCESS_TOKEN and token != TRMNL_ACCESS_TOKEN:
        log.warning(f"TRMNL device {device_id} sent wrong token")
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    log.info(f"TRMNL display request from device {device_id}")

    # Advance to next screen in playlist
    idx = _device_state.get(device_id, -1)
    idx = (idx + 1) % len(PLAYLIST)
    _device_state[device_id] = idx
    screen = PLAYLIST[idx]

    # Fetch data for this screen
    source_getters = {
        "ha": lambda: _get("ha", TTL_HA * 2),
        "weather": lambda: _get("weather", TTL_WEATHER * 2),
        "sports": lambda: _get("sports", TTL_SPORTS * 2),
        "calendar": lambda: _get("calendar", TTL_CALENDAR * 2),
    }
    data = source_getters[screen]() or {}

    # Render PNG
    try:
        img = render_screen(screen, data)
    except Exception as e:
        log.error(f"Render failed for {screen}: {e}")
        return JSONResponse({"error": "render failed"}, status_code=500)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    # Unique filename based on content hash (device uses this for change detection)
    filename = f"{screen}-{hashlib.md5(png_bytes).hexdigest()[:8]}.png"
    _image_cache[filename] = png_bytes

    # Prune old images (keep last 20)
    if len(_image_cache) > 20:
        oldest = list(_image_cache.keys())[:-20]
        for k in oldest:
            del _image_cache[k]

    # Determine refresh interval for this screen (seconds)
    refresh_map = {"ha": TTL_HA, "weather": TTL_WEATHER, "sports": TTL_SPORTS, "calendar": TTL_CALENDAR}
    refresh_rate = refresh_map.get(screen, 300)

    # Build base URL from request
    base_url = str(request.base_url).rstrip("/")
    image_url = f"{base_url}/images/{filename}"

    log.info(f"Serving {screen} → {filename} to device {device_id}")
    return {
        "image_url": image_url,
        "filename": filename,
        "refresh_rate": refresh_rate,
        "update_firmware": False,
    }


@app.get("/images/{filename}")
async def serve_image(filename: str):
    """Serve pre-rendered PNG images to the TRMNL device."""
    png = _image_cache.get(filename)
    if not png:
        raise HTTPException(404, "Image not found or expired")
    return Response(content=png, media_type="image/png")
