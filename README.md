# TRMNL X Family Dashboard

BYOS (Bring Your Own Server) setup for the TRMNL X 10.3" e-ink display.
Runs on **deepthought** (Pi 5, Livermore house) as a Docker Compose stack.

## Architecture

```
TRMNL X device
    │  polls GET /api/display every N seconds
    ▼
Aggregator (port 8081)      ← Python/FastAPI — BYOS protocol + data + PNG renderer
    ├── Home Assistant REST API  (deepthought-ha:8123)
    ├── Open-Meteo               (free, no key)
    ├── ESPN unofficial API      (free, no key)
    └── Google Calendar iCal    (private URL, no OAuth)
```

> **Note on Inker:** The original plan used `wojooo/inker` as the BYOS server, but that image
> has no ARM64 build and won't run on deepthought (Pi 5). The aggregator implements the TRMNL
> BYOS `/api/display` protocol directly using Pillow for PNG rendering — fully ARM64 native.

## Quick Start

### 1. Clone and configure
```bash
git clone https://github.com/bradles94550/trmnl-dashboard.git ~/trmnl
cd ~/trmnl
cp .env.example .env
nano .env   # fill in HA_TOKEN and ICAL_URL — see docs/03-data-sources.md
```

### 2. Start the stack
```bash
docker compose up -d
```

### 3. Verify aggregator
```bash
curl http://localhost:8081/health
curl http://localhost:8081/data/weather
```

### 4. Pair TRMNL X
Connect device to WiFi via captive portal → set server URL to `http://192.168.86.69:8081`

The device will start polling `GET /api/display` and cycle through 4 screens automatically.
See **docs/02-trmnl-pairing.md** for full pairing instructions.

## Playlist (suggested rotation)
| Screen | Refresh |
|--------|---------|
| HA Status | 5 min |
| Family Calendar | 15 min |
| Sports Scores | 30 min |
| Weather | 30 min |

## Aggregator API
| Endpoint | Description |
|----------|-------------|
| `GET /health` | Cache ages + status |
| `GET /api/display` | **TRMNL BYOS endpoint** — returns PNG image_url + refresh_rate |
| `GET /images/{filename}` | Serves rendered PNG to the device |
| `GET /data/ha` | HA entity states + summary (JSON) |
| `GET /data/weather` | Current conditions + 5-day forecast (JSON) |
| `GET /data/sports` | Today's scores + tomorrow's schedule (JSON) |
| `GET /data/calendar` | Next 14 days of events (JSON) |
| `POST /refresh/{source}` | Force immediate cache refresh |

## Documentation
- [01 — Inker Docker Setup](docs/01-inker-setup.md)
- [02 — TRMNL X Pairing](docs/02-trmnl-pairing.md)
- [03 — Data Sources (HA token, iCal URL, ESPN IDs)](docs/03-data-sources.md)
- [04 — Aggregator Service](docs/04-aggregator.md)
- [05 — Screen Design & Playlist](docs/05-screen-design.md)
- [06 — Security](docs/06-security.md)

## Stack Management
```bash
# View logs
docker compose logs -f aggregator

# Restart a single service
docker compose restart aggregator

# Update images
docker compose pull && docker compose up -d

# Force refresh a data source
curl -X POST http://localhost:8081/refresh/ha
```
