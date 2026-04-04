# TRMNL X Family Dashboard

BYOS (Bring Your Own Server) setup for the TRMNL X 10.3" e-ink display.
Runs on **deepthought** (Pi 5, Livermore house) as a Docker Compose stack.

## Architecture

```
TRMNL X device
    │  polls /api/display every N seconds
    ▼
Inker (port 8080)           ← screen designer + TRMNL protocol server
    │  custom widget JSON fetch
    ▼
Aggregator (port 8081)      ← Python/FastAPI, caches data from 4 sources
    ├── Home Assistant REST API  (deepthought-ha:8123)
    ├── Open-Meteo               (free, no key)
    ├── ESPN unofficial API      (free, no key)
    └── Google Calendar iCal    (private URL, no OAuth)
```

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

### 4. Open Inker UI
Navigate to `http://deepthought-ip:8080` and enter your `INKER_ADMIN_PIN`.

### 5. Pair TRMNL X
Connect device to WiFi via captive portal → set server URL to `http://192.168.86.69:8080`

See **docs/02-trmnl-pairing.md** for full pairing instructions.

### 6. Configure custom widgets in Inker
For each data source, create a Custom Widget pointing at:
- HA Status: `http://trmnl-aggregator:8081/data/ha`
- Weather: `http://trmnl-aggregator:8081/data/weather`
- Sports: `http://trmnl-aggregator:8081/data/sports`
- Calendar: `http://trmnl-aggregator:8081/data/calendar`

HTML templates for each screen are in `aggregator/templates/`.

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
| `GET /data/ha` | HA entity states + summary |
| `GET /data/weather` | Current conditions + 5-day forecast |
| `GET /data/sports` | Today's scores + tomorrow's schedule |
| `GET /data/calendar` | Next 14 days of events |
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
