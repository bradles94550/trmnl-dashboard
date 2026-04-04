# 05 — Screen Design & Playlist in Inker

## Configuring Custom Widgets

For each of the 4 screens, create a **Custom Widget** in Inker:
1. Inker UI → **Widgets** → **New Widget** → **Custom**
2. Set **Data URL** to the aggregator endpoint
3. Paste the HTML template from `aggregator/templates/` into the template editor
4. Inker fetches the JSON, injects it into the template via Jinja2-style variables

### Widget → endpoint mapping
| Screen | Inker Data URL |
|--------|---------------|
| HA Status | `http://trmnl-aggregator:8081/data/ha` |
| Weather | `http://trmnl-aggregator:8081/data/weather` |
| Sports | `http://trmnl-aggregator:8081/data/sports` |
| Calendar | `http://trmnl-aggregator:8081/data/calendar` |

**Note:** Use `trmnl-aggregator` (container name) as the hostname — Inker and the aggregator
share the same Docker Compose network (`trmnl_default`), so they can address each other by name.

## Playlist Setup
1. Inker UI → **Screens** → **New Playlist**
2. Add each widget, set refresh interval per screen
3. Assign the playlist to your TRMNL X device

## E-ink Design Rules
The TRMNL X display is 1872×1404 at 16 grayscale levels. Inker converts your HTML to PNG automatically.

Key constraints:
- **No color** — grayscale only. Use `#000`, `#555`, `#999`, `#eee`, `#fff`
- **Bold text** for hierarchy — thin fonts wash out at e-ink contrast levels
- **High contrast** — avoid gradients and subtle shading
- **Fixed-width fonts** work well for data tables (use `font-family: monospace`)
- **Large tap targets** — the touch bar is at the bottom edge
- **Avoid images** unless they're high-contrast illustrations; photos look muddy

## Refresh Strategy
E-ink full refresh causes a flash. Keep refresh intervals appropriate:
- Fast-changing data (HA): 5 min
- Medium (calendar): 15 min
- Slow (weather/sports): 30 min

Inker supports partial refresh for minor updates (check firmware capabilities in your device).

## Testing layouts
Preview your HTML templates in a browser before pushing to the device.
The aggregator's JSON responses can be piped into a local HTML file for rapid iteration:
```bash
curl http://localhost:8081/data/weather | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2))"
```
