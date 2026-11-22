"""
collect.py - pulls Swindon -> Bath Spa delay data from the HSP API
and saves it to delays_raw.csv (one row per train per day).

Safe to re-run: it skips trains it already saved, so you can collect
a few weeks at a time without repeating requests.
"""
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

# ---------- settings you can change ----------
DATE_FROM = date(2026, 10, 1)    # start of the period to collect
DATE_TO = date(2026, 10, 31)     # end of the period to collect
FROM_TIME = "0630"               # earliest departure from Swindon
TO_TIME = "0930"                 # latest departure from Swindon
OUTPUT_FILE = "delays_raw.csv"
PAUSE_SECONDS = 1.5              # wait between requests (keeps us under the rate limit)
# ---------------------------------------------

BASE = "https://api1.raildata.org.uk/1010-historical-service-performance-_hsp_1_1"
METRICS_URL = f"{BASE}/serviceMetrics"
DETAILS_URL = f"{BASE}/serviceDetails"
FROM_STATION = "SWI"
TO_STATION = "BTH"

if "RDM_API_KEY" not in os.environ:
    raise SystemExit("RDM_API_KEY is not set. Set your API key first, then run again.")

HEADERS = {
    "x-apikey": os.environ["RDM_API_KEY"],
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",  # without this the gateway returns 403
}


class RateLimited(Exception):
    pass


def post(url, body):
    """Send one request, retrying a few times if the server is flaky."""
    for attempt in range(3):
        try:
            r = requests.post(url, headers=HEADERS, json=body, timeout=60)
        except requests.RequestException as e:
            print(f"  network problem ({e}), retrying...")
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 429:
            raise RateLimited()
        if r.status_code in (502, 503, 504):
            print(f"  server error {r.status_code}, retrying...")
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code != 200:
            print(f"  unexpected status {r.status_code}: {r.text[:200]}")
            return None
        time.sleep(PAUSE_SECONDS)
        return r.json()
    print("  gave up after 3 tries")
    return None


def week_chunks(start, end):
    """Split the date range into chunks of up to 7 days."""
    while start <= end:
        chunk_end = min(start + timedelta(days=6), end)
        yield start, chunk_end
        start = chunk_end + timedelta(days=1)


def to_minutes(hhmm):
    """'0732' -> 452 minutes after midnight. Blank/invalid -> None."""
    if not hhmm or len(hhmm) < 4 or not hhmm[:4].isdigit():
        return None
    return int(hhmm[:2]) * 60 + int(hhmm[2:4])


def delay(planned, actual):
    p, a = to_minutes(planned), to_minutes(actual)
    if p is None or a is None:
        return None
    d = a - p
    if d < -720:      # crossed midnight
        d += 1440
    return d


def get_rids():
    """Ask serviceMetrics which trains ran, return a list of (rid, planned dep, planned arr, operator)."""
    found = []
    for start, end in week_chunks(DATE_FROM, DATE_TO):
        print(f"Finding trains for {start} to {end}...")
        data = post(METRICS_URL, {
            "from_loc": FROM_STATION, "to_loc": TO_STATION,
            "from_time": FROM_TIME, "to_time": TO_TIME,
            "from_date": start.isoformat(), "to_date": end.isoformat(),
            "days": "WEEKDAY",
        })
        if not data:
            continue
        for svc in data.get("Services", []):
            attrs = svc["serviceAttributesMetrics"]
            for rid in attrs.get("rids", []):
                found.append((rid, attrs.get("gbtt_ptd"), attrs.get("gbtt_pta"), attrs.get("toc_code")))
    return found


def get_row(rid, planned_dep, planned_arr, toc):
    """Ask serviceDetails for one train on one day and turn it into a row."""
    data = post(DETAILS_URL, {"rid": rid})
    if not data:
        return None
    details = data.get("serviceAttributesDetails", {})
    locations = details.get("locations", [])
    swi = next((l for l in locations if l.get("location") == FROM_STATION), {})
    bth = next((l for l in locations if l.get("location") == TO_STATION), {})
    return {
        "rid": rid,
        "date": f"{rid[0:4]}-{rid[4:6]}-{rid[6:8]}",
        "operator": toc,
        "planned_dep": swi.get("gbtt_ptd", planned_dep),
        "actual_dep": swi.get("actual_td", ""),
        "planned_arr": bth.get("gbtt_pta", planned_arr),
        "actual_arr": bth.get("actual_ta", ""),
        "dep_delay_mins": delay(swi.get("gbtt_ptd", planned_dep), swi.get("actual_td")),
        "arr_delay_mins": delay(bth.get("gbtt_pta", planned_arr), bth.get("actual_ta")),
        "reason_code": bth.get("late_canc_reason") or swi.get("late_canc_reason") or "",
    }


def save(rows):
    """Add rows to the end of the CSV (writes the header if the file is new)."""
    if rows:
        pd.DataFrame(rows).to_csv(OUTPUT_FILE, mode="a", header=not Path(OUTPUT_FILE).exists(), index=False)


def main():
    done = set()
    if Path(OUTPUT_FILE).exists():
        done = set(pd.read_csv(OUTPUT_FILE, dtype=str)["rid"])
        print(f"{len(done)} trains already saved, will skip those.")

    unsaved = []   # rows fetched but not written to the CSV yet
    saved = 0
    failed = 0
    try:
        trains = [t for t in get_rids() if t[0] not in done]
        print(f"{len(trains)} trains to fetch.")

        for n, (rid, dep, arr, toc) in enumerate(trains, 1):
            row = get_row(rid, dep, arr, toc)
            if row:
                unsaved.append(row)
            else:
                failed += 1
            if n % 10 == 0:
                # save every 10 trains, so a crash only loses the last few
                save(unsaved)
                saved += len(unsaved)
                unsaved = []
                print(f"  {n}/{len(trains)} done")
    except RateLimited:
        print("Hit the rate limit (429). Wait a while and run again - it carries on where it stopped.")
    except KeyboardInterrupt:
        print("Stopped by you (Ctrl+C).")
    finally:
        # runs no matter how the loop ended: saves whatever is left
        save(unsaved)
        saved += len(unsaved)
        print(f"Saved {saved} new rows to {OUTPUT_FILE}.")
        if failed:
            print(f"{failed} trains could not be fetched. Run again later to retry them.")


if __name__ == "__main__":
    main()
