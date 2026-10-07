"""Step 1: download NYC 311 service requests from the NYC Open Data API with sodapy.

Pulls one month at a time into data/raw/created_YYYY-MM.parquet.
- Months already on disk are skipped, except the newest REFRESH_RECENT months, which are always
  re-downloaded because requests opened recently keep getting closed.
- Also saves open_requests.parquet: every request in the window that is still open today.
- No API key is used. Anonymous access is throttled, so each call is retried with backoff.

Usage:  python python\\01_fetch.py            (full 13-month window, about 4 million rows)
        python python\\01_fetch.py --months 1 (quick test: current and previous month only)
"""
import argparse
import logging
import time
from datetime import date

import pandas as pd
from sodapy import Socrata

from common import (COLUMNS, DATASET, DOMAIN, MONTHS_BACK, PAGE_SIZE, RAW_DIR, REFRESH_RECENT, TIMEOUT,
                    month_starts, next_month)

RETRY_WAITS = [10, 30, 60, 120, 300]   # seconds to wait before each retry


def get_page(client, **query):
    for attempt, wait in enumerate([0] + RETRY_WAITS):
        if wait:
            print(f"    retry {attempt} in {wait}s ...", flush=True)
            time.sleep(wait)
        try:
            return client.get(DATASET, **query)
        except Exception as e:  # network errors, timeouts and HTTP 429/5xx all get the same retry
            print(f"    API error: {str(e)[:150]}", flush=True)
    raise RuntimeError("API still failing after all retries. Run the script again later; finished months are kept.")


def fetch_all(client, where: str) -> pd.DataFrame:
    """Page through every row matching `where`, in a stable order."""
    frames, offset = [], 0
    while True:
        rows = get_page(client, select=",".join(COLUMNS), where=where, order=":id",
                        limit=PAGE_SIZE, offset=offset)
        if rows:
            frames.append(pd.DataFrame.from_records(rows))
        print(f"    {offset + len(rows):,} rows", flush=True)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    # The API leaves out fields that are empty, so make sure every expected column exists
    return df.reindex(columns=COLUMNS).astype("string")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=MONTHS_BACK, help="full months before the current one")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    months = month_starts(args.months)
    keep = {f"created_{m:%Y-%m}.parquet" for m in months}
    recent = set(sorted(keep)[-REFRESH_RECENT:])

    # Remove months that have rolled out of the window
    for f in RAW_DIR.glob("created_*.parquet"):
        if f.name not in keep:
            print(f"Removing {f.name} (outside the window)")
            f.unlink()

    logging.getLogger().setLevel(logging.ERROR)   # hide sodapy's "no app_token" warning: anonymous is intended
    client = Socrata(DOMAIN, None, timeout=TIMEOUT)
    t0 = time.time()
    for m in months:
        path = RAW_DIR / f"created_{m:%Y-%m}.parquet"
        if path.exists() and path.name not in recent:
            print(f"{m:%Y-%m}: already downloaded, skipping")
            continue
        print(f"{m:%Y-%m}: downloading ...", flush=True)
        where = f"created_date >= '{m:%Y-%m-%d}T00:00:00' AND created_date < '{next_month(m):%Y-%m-%d}T00:00:00'"
        df = fetch_all(client, where)
        df.to_parquet(path.with_suffix(".tmp"), index=False)
        path.with_suffix(".tmp").replace(path)   # only replace the old file once the new one is complete
        print(f"{m:%Y-%m}: saved {len(df):,} rows", flush=True)

    print("Open requests (backlog snapshot): downloading ...", flush=True)
    where = f"created_date >= '{months[0]:%Y-%m-%d}T00:00:00' AND status != 'Closed'"
    df = fetch_all(client, where)
    df.to_parquet(RAW_DIR / "open_requests.parquet", index=False)
    print(f"Open requests: saved {len(df):,} rows")

    (RAW_DIR / "fetched_at.txt").write_text(pd.Timestamp.now(tz="America/New_York").isoformat())
    client.close()
    print(f"Done in {(time.time() - t0) / 60:.1f} minutes. Window: {months[0]:%Y-%m-%d} to {date.today()}")


if __name__ == "__main__":
    main()
