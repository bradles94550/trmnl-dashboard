# 02 — TRMNL X Device Pairing

## First-Time Setup

### Step 1 — Power on and connect to captive portal
1. Plug TRMNL X into USB-C power (or seat in dock)
2. Device broadcasts a WiFi network: `TRMNL-XXXXXX`
3. Connect your phone/laptop to that network
4. A captive portal page opens automatically (or navigate to `192.168.4.1`)

### Step 2 — Configure WiFi + server
Fill in:
- **WiFi SSID**: your home network SSID
- **WiFi Password**: your password
- **Custom Server URL**: `http://192.168.86.69:8080`
  (deepthought's LAN IP — must match exactly what Inker is listening on)

### Step 3 — Complete pairing in Inker
1. In Inker UI → **Devices** → note the device ID shown
2. TRMNL X will start polling `/api/display` — you should see activity in `docker compose logs inker`

## Static DHCP (Recommended)
Assign deepthought a static IP on your router so the server URL never changes.
deepthought's MAC address: check with `ssh deepthought "ip link show eth0 | grep ether"` (or wlan0 if on WiFi).
Current Tailscale IP: `100.95.141.6` (stable, alternative for same-network access).

## Refresh Interval
Set in Inker per-screen. Suggested:
- HA Status: 300s (5 min)
- Calendar: 900s (15 min)
- Sports/Weather: 1800s (30 min)

## Firmware Updates
- Inker can push firmware OTA — check `update_firmware` flag in the `/api/display` response
- TRMNL X open firmware: https://github.com/usetrmnl/firmware

## Troubleshooting
- **Device shows blank screen**: Inker returned no content — check `docker compose logs inker`
- **"Cannot reach server"**: Verify device and deepthought are on the same VLAN/subnet
- **Image looks wrong**: TRMNL X expects 1872×1404 1- or 2-bit PNG — Inker handles this automatically
