# 06 — Security

## Threat Model

**What's exposed:**
- Inker UI (`:8080`) — no built-in auth, protected only by network placement
- Aggregator API (`:8081`) — no auth, read-only data
- HA long-lived token — stored in `.env`, never committed to git

**What's NOT exposed:**
- TRMNL X uses one-way polling — the device initiates all connections outbound
  (no inbound network path from the display back to your network)
- MariaDB, HA internals, MQTT — all on separate ports, not part of this stack

## Network Recommendations

### Keep both ports LAN-only
Ports 8080 and 8081 are bound to all interfaces by default. If deepthought
is ever accessible from outside your LAN, add firewall rules:
```bash
# On deepthought — allow only LAN subnet
sudo ufw allow from 192.168.86.0/24 to any port 8080
sudo ufw allow from 192.168.86.0/24 to any port 8081
```

### Remote access — use Tailscale
If you need to access the Inker UI remotely, use Tailscale (already installed on deepthought):
`http://100.95.141.6:8080` — only accessible to Tailscale peers, no port forwarding needed.

**Never port-forward 8080 to the internet.** Inker has no authentication.

## Secrets Management

All secrets live in `.env`:
- `INKER_ADMIN_PIN` — UI access PIN
- `HA_TOKEN` — Home Assistant long-lived token (read-only)
- `ICAL_URL` — Google Calendar private iCal URL

`.env` is in `.gitignore` — it is never committed to the repo.

If you need to share the `.env` with another admin, use 1Password or your existing secret store.

## HA Token Scoping
The HA long-lived token has the same permissions as the user that created it.
For maximum safety, create a dedicated `trmnl-reader` user in HA with read-only access
(see docs/03-data-sources.md) before generating the token.

The aggregator only calls `GET /api/states` — it never writes to HA.

## Log Exposure
The aggregator logs fetch activity to stdout. These are visible in:
```bash
docker compose logs aggregator
```
Logs contain URLs and response sizes but NOT the HA token or iCal URL values.
