#!/usr/bin/env python3
"""
Apple Calendar → JSON extractor for TRMNL dashboard.
Queries each calendar individually (one at a time) so a slow iCloud calendar
can't hang the whole run. Each calendar query has its own timeout.
Writes ~/trmnl/calendar-events.json and SCPs to deepthought.
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

SKIP_CALENDARS = {"Siri Suggestions", "Scheduled Reminders"}
DAYS_AHEAD = 14
OUTPUT_FILE = Path.home() / "trmnl" / "calendar-events.json"
DEEPTHOUGHT_DEST = "deepthought:~/trmnl/calendar-events.json"
PACIFIC = ZoneInfo("America/Los_Angeles")
PER_CALENDAR_TIMEOUT = 20   # seconds per calendar before skipping
NAMES_TIMEOUT = 30          # seconds for initial calendar names query

# Field separator (ASCII 28) and row separator (ASCII 30)
FSEP = chr(28)
RSEP = chr(30)

# Activate Calendar.app first so it's running, then wait briefly before querying
ACTIVATE_CALENDAR_SCRIPT = '''
tell application "Calendar" to activate
delay 3
tell application "Calendar" to return name of every calendar
'''

GET_CALENDAR_NAMES_SCRIPT = 'tell application "Calendar" to return name of every calendar'

# Template: query one named calendar. Calendar name is passed as a shell-safe arg.
SINGLE_CAL_SCRIPT_TEMPLATE = r"""
set FSEP to ASCII character 28
set RSEP to ASCII character 30
set calName to "{cal_name}"
set startDate to current date
set endDate to startDate + ({days} * days)
set allRows to ""

tell application "Calendar"
    tell calendar calName
        set calEvents to (every event whose start date >= startDate and start date <= endDate)
        repeat with evt in calEvents
            try
                set evtTitle to summary of evt
                set evtAllDay to allday event of evt
                set evtStart to start date of evt
                set evtEnd to end date of evt

                try
                    set evtLoc to location of evt
                    if evtLoc is missing value then
                        set evtLoc to ""
                    end if
                on error
                    set evtLoc to ""
                end try

                -- Start date components (all integers)
                set sY to (year of evtStart) as text
                set sMInt to (month of evtStart) as integer
                set sDInt to (day of evtStart) as integer
                set sHInt to (hours of evtStart) as integer
                set sMiInt to (minutes of evtStart) as integer

                set sMStr to sMInt as text
                if sMInt < 10 then set sMStr to "0" & sMStr
                set sDStr to sDInt as text
                if sDInt < 10 then set sDStr to "0" & sDStr
                set sHStr to sHInt as text
                if sHInt < 10 then set sHStr to "0" & sHStr
                set sMiStr to sMiInt as text
                if sMiInt < 10 then set sMiStr to "0" & sMiStr

                set startStr to sY & "-" & sMStr & "-" & sDStr & "T" & sHStr & ":" & sMiStr & ":00"

                -- End date components
                set eY to (year of evtEnd) as text
                set eMInt to (month of evtEnd) as integer
                set eDInt to (day of evtEnd) as integer
                set eHInt to (hours of evtEnd) as integer
                set eMiInt to (minutes of evtEnd) as integer

                set eMStr to eMInt as text
                if eMInt < 10 then set eMStr to "0" & eMStr
                set eDStr to eDInt as text
                if eDInt < 10 then set eDStr to "0" & eDStr
                set eHStr to eHInt as text
                if eHInt < 10 then set eHStr to "0" & eHStr
                set eMiStr to eMiInt as text
                if eMiInt < 10 then set eMiStr to "0" & eMiStr

                set endStr to eY & "-" & eMStr & "-" & eDStr & "T" & eHStr & ":" & eMiStr & ":00"

                if evtAllDay then
                    set allDayFlag to "1"
                else
                    set allDayFlag to "0"
                end if

                set row to evtTitle & FSEP & startStr & FSEP & endStr & FSEP & allDayFlag & FSEP & evtLoc
                set allRows to allRows & row & RSEP
            on error
                -- skip problematic events silently
            end try
        end repeat
    end tell
end tell

return allRows
"""


def run_applescript(script: str, timeout: int = 10) -> tuple[bool, str]:
    """Returns (success, output). On timeout or error returns (False, error_msg)."""
    try:
        result = subprocess.run(
            ["osascript", "-"],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except Exception as e:
        return False, str(e)


def get_calendar_names() -> list[str]:
    # First try without activating (fast if Calendar.app is already running)
    ok, output = run_applescript(GET_CALENDAR_NAMES_SCRIPT, timeout=10)
    if not ok:
        print(f"Calendar.app not responsive, activating it first...")
        ok, output = run_applescript(ACTIVATE_CALENDAR_SCRIPT, timeout=NAMES_TIMEOUT)
    if not ok:
        print(f"ERROR: Could not get calendar names: {output}", file=sys.stderr)
        sys.exit(1)
    # AppleScript returns comma-separated list
    names = [n.strip() for n in output.split(",") if n.strip()]
    return [n for n in names if n not in SKIP_CALENDARS]


def parse_cal_rows(raw: str, cal_name: str) -> list[dict]:
    now_pacific = datetime.now(PACIFIC)
    window_end = now_pacific + timedelta(days=DAYS_AHEAD)
    events = []

    for row in raw.split(RSEP):
        row = row.strip()
        if not row:
            continue
        parts = row.split(FSEP)
        if len(parts) < 4:
            continue

        summary   = parts[0].strip()
        start_str = parts[1].strip()
        end_str   = parts[2].strip()
        all_day   = parts[3].strip() == "1"
        location  = parts[4].strip() if len(parts) > 4 and parts[4].strip() else None

        try:
            start_naive = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S")
            start_local = start_naive.replace(tzinfo=PACIFIC)
            end_naive   = datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S")
            end_local   = end_naive.replace(tzinfo=PACIFIC)
        except ValueError:
            continue

        if start_local > window_end:
            continue

        events.append({
            "summary":  summary,
            "start":    start_local.isoformat(),
            "end":      end_local.isoformat(),
            "location": location,
            "all_day":  all_day,
            "calendar": cal_name,
        })

    return events


def main() -> int:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running Apple Calendar sync...")

    calendar_names = get_calendar_names()
    print(f"Found {len(calendar_names)} calendars to query: {', '.join(calendar_names)}")

    all_events: list[dict] = []
    skipped = []

    for cal_name in calendar_names:
        # Escape any double-quotes in the calendar name for AppleScript string embedding
        safe_name = cal_name.replace('"', '\\"')
        script = SINGLE_CAL_SCRIPT_TEMPLATE.format(cal_name=safe_name, days=DAYS_AHEAD)
        ok, output = run_applescript(script, timeout=PER_CALENDAR_TIMEOUT)

        if not ok:
            print(f"  SKIP [{cal_name}]: {output}")
            skipped.append(cal_name)
            continue

        events = parse_cal_rows(output, cal_name)
        print(f"  [{cal_name}]: {len(events)} events")
        all_events.extend(events)

    all_events.sort(key=lambda e: e["start"])

    # Deduplicate: two calendars named "Home" (local + iCloud) produce identical
    # events. Keep the first occurrence by (summary, start, end).
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for evt in all_events:
        key = (evt["summary"], evt["start"], evt["end"])
        if key not in seen:
            seen.add(key)
            deduped.append(evt)
    if len(deduped) < len(all_events):
        print(f"Deduped {len(all_events) - len(deduped)} duplicate event(s)")
    all_events = deduped

    if skipped:
        print(f"Skipped {len(skipped)} calendars (timeout/error): {', '.join(skipped)}")

    print(f"Total: {len(all_events)} events across {len(calendar_names) - len(skipped)} calendars")

    output_data = {
        "events":     all_events[:40],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source":     "apple_calendar",
        "skipped_calendars": skipped,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output_data, indent=2))
    print(f"Wrote {OUTPUT_FILE}")

    # SCP to deepthought — SSH config handles key + host resolution
    result = subprocess.run(
        ["scp", str(OUTPUT_FILE), DEEPTHOUGHT_DEST],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"WARNING: SCP to deepthought failed: {result.stderr.strip()}", file=sys.stderr)
        return 2

    print(f"Synced to {DEEPTHOUGHT_DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
