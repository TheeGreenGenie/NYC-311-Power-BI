"""Step 3: independent checks on the model CSVs. Recomputes totals from the raw files and checks every key.

Usage: python python\\verify.py     (must end with: ALL CHECKS PASSED)
"""
import pandas as pd

from common import MODEL_DIR, RAW_DIR, WITHIN_DAYS

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def load(name, **kw):
    return pd.read_csv(MODEL_DIR / f"{name}.csv", **kw)


raw = pd.concat([pd.read_parquet(f, columns=["unique_key", "status"])
                 for f in sorted(RAW_DIR.glob("created_*.parquet"))], ignore_index=True)
raw = raw.drop_duplicates("unique_key")
open_raw = pd.read_parquet(RAW_DIR / "open_requests.parquet", columns=["unique_key", "status"])
open_raw = open_raw.drop_duplicates("unique_key")

daily = load("fact_requests_daily", parse_dates=["Date"], dtype={"AgencyKey": str})
zipm = load("fact_zip_monthly", parse_dates=["MonthStart"], dtype={"ZIP": str})
backlog = load("fact_open_backlog", dtype={"AgencyKey": str})
dim_date = load("dim_date", parse_dates=["Date"])
dim_complaint = load("dim_complaint")
dim_category = load("dim_category")
dim_agency = load("dim_agency", dtype={"AgencyKey": str})
dim_borough = load("dim_borough")
dim_location = load("dim_location", dtype={"ZIP": str})
info = load("refresh_info").iloc[0]

# ---------- totals ----------
check("Daily fact total = raw request count", daily.Requests.sum() == len(raw),
      f"{daily.Requests.sum():,} vs {len(raw):,}")
check("ZIP fact total = daily fact total", zipm.Requests.sum() == daily.Requests.sum())
check("Closed count = raw rows with status Closed", daily.Closed.sum() == (raw.status == "Closed").sum())
check("Backlog total = open rows in raw pull", backlog.OpenRequests.sum() == (open_raw.status != "Closed").sum(),
      f"{backlog.OpenRequests.sum():,}")
check("refresh_info TotalRequests matches", int(info.TotalRequests) == len(raw))

# ---------- sanity ----------
check("No negative response hours", (daily.ResponseHoursSum >= 0).all())
check("Timed closed <= closed <= requests",
      ((daily.TimedClosed <= daily.Closed) & (daily.Closed <= daily.Requests)).all())
cols = [f"Within{n}d" for n in WITHIN_DAYS]
mono = all((daily[a] <= daily[b]).all() for a, b in zip(cols, cols[1:])) and (daily[cols[-1]] <= daily.TimedClosed).all()
check("Within-N-days counts only grow with N, and never exceed timed closed", mono)
avg_h = daily.ResponseHoursSum.sum() / daily.TimedClosed.sum()
check("Average response time is plausible (1 hour to 60 days)", 1 <= avg_h <= 24 * 60, f"{avg_h:.1f} hours")

# ---------- keys: every fact key exists in its dimension ----------
check("Fact dates all in dim_date", daily.Date.isin(dim_date.Date).all())
check("ZIP-fact months all in dim_date", zipm.MonthStart.isin(dim_date.Date).all())
check("Dim_date has no gaps", dim_date.Date.diff().dropna().dt.days.eq(1).all())
for fact, label in [(daily, "daily"), (backlog, "backlog")]:
    check(f"Complaint keys ({label}) all in dim_complaint", fact.ComplaintKey.isin(dim_complaint.ComplaintKey).all())
    check(f"Agency keys ({label}) all in dim_agency", fact.AgencyKey.isin(dim_agency.AgencyKey).all())
    check(f"Boroughs ({label}) all in dim_borough", fact.Borough.isin(dim_borough.Borough).all())
check("ZIPs all in dim_location", zipm.ZIP.isin(dim_location.ZIP).all())
check("Categories all in dim_category", zipm.Category.isin(dim_category.Category).all()
      and dim_complaint.Category.isin(dim_category.Category).all())
check("Dimension keys are unique", dim_complaint.ComplaintKey.is_unique and dim_agency.AgencyKey.is_unique
      and dim_location.ZIP.is_unique and dim_date.Date.is_unique)

# ---------- freshness ----------
fetched = pd.Timestamp(info.FetchedAt)
latest = pd.Timestamp(info.LatestRequest)
check("Latest request is within 3 days of the fetch time", (fetched - latest) <= pd.Timedelta(days=3),
      f"latest {latest}, fetched {fetched}")

# ---------- headline numbers (the build tutorial uses these as check numbers) ----------
print()
print(f"Data as of {info.DataAsOf}; window starts {info.WindowStart}")
print(f"Total requests: {daily.Requests.sum():,}   Closed: {daily.Closed.sum():,}   Open now: {backlog.OpenRequests.sum():,}")
print(f"Average response time (closed requests): {avg_h:.1f} hours")
print(f"Closed within 7 days: {daily.Within7d.sum() / daily.TimedClosed.sum():.1%}")
top = (daily.merge(dim_complaint, on="ComplaintKey").groupby("ComplaintType").Requests.sum()
       .sort_values(ascending=False).head(5))
print("Top 5 complaint types:")
for t, n in top.items():
    print(f"  {t}: {n:,}")
print()
print("ALL CHECKS PASSED" if all(results) else f"{results.count(False)} CHECK(S) FAILED")
