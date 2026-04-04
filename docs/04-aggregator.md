# 04 — Aggregator Service

## Overview
Python FastAPI service that fetches data from all 4 sources on a schedule,
caches results, and exposes JSON endpoints for Inker's custom widgets.

## Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Cache freshness status |
| GET | `/data/ha` | HA entities + summary stats |
| GET | `/data/weather` | Current + 5-day forecast |
| GET | `/data/sports` | Today's scores + tomorrow's schedule |
| GET | `/data/calendar` | Next 14 days of events |
| POST | `/refresh/{source}` | Force cache refresh |

## Cache TTLs (configurable in .env)
| Source | Default TTL | Variable |
|--------|-------------|----------|
| HA | 5 min | `CACHE_TTL_HA` |
| Calendar | 15 min | `CACHE_TTL_CALENDAR` |
| Weather | 30 min | `CACHE_TTL_WEATHER` |
| Sports | 30 min | `CACHE_TTL_SPORTS` |

## Build and run locally (dev)
```bash
cd aggregator
pip install -r requirements.txt
cp ../.env.example ../.env  # fill in values
uvicorn main:app --reload --port 8081
```

## Building the Docker image
```bash
docker compose build aggregator
```

## Checking the cache
```bash
curl http://localhost:8081/health
# {"status":"ok","cache_ages":{"ha":"45s ago","weather":"120s ago",...}}
```

## Force a refresh
```bash
curl -X POST http://localhost:8081/refresh/ha
curl -X POST http://localhost:8081/refresh/calendar
```

## Adding entities to the HA summary
Edit `aggregator/main.py` → `fetch_ha()` function.
The `domains` list controls which entity types are included.
The `summary` block computes quick stats — add your own counters here.

## Dependencies
| Package | Purpose |
|---------|---------|
| `fastapi` | API framework |
| `uvicorn` | ASGI server |
| `apscheduler` | Background job scheduler |
| `httpx` | Async HTTP client |
| `icalendar` | iCal/ICS parser |
| `python-dotenv` | .env file loader |
