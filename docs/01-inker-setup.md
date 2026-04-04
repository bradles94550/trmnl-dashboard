# 01 — Inker Docker Setup

## What is Inker?
Inker is a self-hosted e-ink device management server built for the homelab community.
It implements the TRMNL BYOS protocol and provides a drag-and-drop screen designer.
- GitHub: https://github.com/robintibor/inker (community fork)
- Image: `wojooo/inker:latest` on Docker Hub

## Deploy

The full stack is in `docker-compose.yml` at the repo root. Deploy to deepthought:

```bash
cd ~/trmnl
docker compose up -d inker
```

Inker includes its own PostgreSQL 17 and Redis — no external databases needed.

## First Boot
1. Navigate to `http://192.168.86.69:8080`
2. Enter the PIN you set in `.env` (`INKER_ADMIN_PIN`)
3. Click **Devices** → **Add Device** — you'll get a device ID to use during TRMNL pairing

## Volumes (persist across restarts)
| Volume | Contents |
|--------|----------|
| `inker_postgres` | Device configs, screen layouts, widget configs |
| `inker_redis` | Session cache |
| `inker_uploads` | Custom images/assets |

## Backup
```bash
docker run --rm \
  -v inker_postgres:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/inker-postgres-$(date +%Y%m%d).tar.gz -C /data .
```

## Update Inker
```bash
docker compose pull inker
docker compose up -d inker
```
The volumes survive image updates.

## Ports
- `8080` → Inker web UI + TRMNL `/api/display` endpoint

## Troubleshooting
- If Inker refuses to start: `docker compose logs inker` — PostgreSQL init takes ~15s on first boot
- If device shows "offline": verify the server URL in the TRMNL captive portal matches exactly `http://192.168.86.69:8080`
