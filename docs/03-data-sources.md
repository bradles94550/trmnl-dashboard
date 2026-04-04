# 03 — Data Sources Setup

## Home Assistant — Long-Lived Token

### Create a dedicated read-only HA user (recommended)
1. In HA → **Settings → People → Add Person**
   - Name: `trmnl-reader`
   - Role: **Read-only** (or leave default and scope via token)
2. Log in as that user at `http://192.168.86.69:8123`
3. Click the user avatar (bottom left) → **Security → Long-Lived Access Tokens → Create Token**
4. Name it `trmnl-dashboard`, copy the token — **it's shown once**
5. Paste into `.env`:
   ```
   HA_TOKEN=eyJ0eXAiOiJKV1Q...
   ```

### Verify the token works
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://192.168.86.69:8123/api/states | head -c 500
```
You should see JSON entity states.

### Entities the aggregator pulls
By default: `binary_sensor`, `sensor`, `switch`, `light`, `lock`, `cover`,
`alarm_control_panel`, `person`. Customize the `domains` list in `aggregator/main.py`.

---

## Open-Meteo — Weather

No API key required. Just set your coordinates in `.env`:
```
WEATHER_LAT=37.6879
WEATHER_LON=-121.7721
```
These are the Livermore, CA coordinates. For the Walnut Creek location (marvin), use:
```
WEATHER_LAT=37.9101
WEATHER_LON=-122.0652
```
API docs: https://open-meteo.com/en/docs

---

## ESPN — Sports Scores

No API key or auth required.

### Finding your team ID
```bash
# List all NBA teams
curl "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams" | \
  python3 -c "import sys,json; [print(t['team']['id'], t['team']['displayName']) for t in json.load(sys.stdin)['sports'][0]['leagues'][0]['teams']]"
```

### Common team IDs
| Team | Sport | League | ID |
|------|-------|--------|----|
| Golden State Warriors | basketball | nba | 9 |
| San Francisco Giants | baseball | mlb | 26 |
| San Francisco 49ers | football | nfl | 25 |
| San Jose Sharks | hockey | nhl | 28 |
| LA Lakers | basketball | nba | 13 |

Update `.env`:
```
ESPN_SPORT=basketball
ESPN_LEAGUE=nba
ESPN_TEAM_ID=9
```

---

## Google Calendar — iCal URL

No OAuth required — just a private iCal URL.

### Get the iCal URL
1. Open Google Calendar on desktop
2. Click ⚙️ Settings → select your calendar from the left sidebar
3. Scroll to **"Integrate calendar"**
4. Copy **"Secret address in iCal format"** — looks like:
   `https://calendar.google.com/calendar/ical/XXXXXXXXXX%40group.calendar.google.com/private-HASH/basic.ics`

### Multiple calendars
Comma-separate multiple URLs in `.env` for family member calendars:
```
ICAL_URL=https://calendar.google.com/.../basic.ics,https://calendar.google.com/.../basic.ics
```

### Security note
This URL grants read access to all events — treat it like a password.
It's in `.env` which is gitignored and never committed.
