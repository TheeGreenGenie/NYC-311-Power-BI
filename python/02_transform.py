"""Step 2: clean the raw 311 pull and write the star-schema CSVs that Power BI reads.

Outputs in data/model/:
  fact_requests_daily.csv  date x complaint type x agency x borough: counts and response-time sums
  fact_zip_monthly.csv     month x ZIP x category: same measures, for the map
  fact_open_backlog.csv    requests still open today, by age bucket x complaint type x agency x borough
  dim_date.csv, dim_complaint.csv, dim_category.csv, dim_agency.csv, dim_borough.csv, dim_location.csv
  refresh_info.csv         when the data was pulled and how fresh it is

Averages and percentages are never stored. Power BI divides the sums, so they stay correct at any level.
"""
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from common import MODEL_DIR, RAW_DIR, WITHIN_DAYS, complaint_category, season

BOROUGHS = ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island", "Unspecified"]
MATURE_DAYS = 30   # a day's requests count as "mature" once they are this old, so most have had time to close


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates("unique_key").copy()
    df["created"] = pd.to_datetime(df["created_date"], format="ISO8601")
    df["closed"] = pd.to_datetime(df["closed_date"], format="ISO8601", errors="coerce")
    df["Date"] = df["created"].dt.normalize()

    df["ComplaintType"] = df["complaint_type"].fillna("Unknown").str.strip().str.title()
    df["AgencyKey"] = df["agency"].fillna("UNKNOWN").str.strip().str.upper()
    df["agency_name"] = df["agency_name"].fillna("Unknown").str.strip()

    b = df["borough"].fillna("").str.strip().str.title()
    df["Borough"] = b.where(b.isin(BOROUGHS[:-1]), "Unspecified")

    z = df["incident_zip"].fillna("").str.extract(r"^(\d{5})")[0]
    zn = pd.to_numeric(z, errors="coerce")
    nyc = zn.between(10001, 10499) | zn.between(11001, 11697)
    df["ZIP"] = z.where(nyc, "Unknown")

    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")

    # Response time: only for closed requests whose close time is not before the open time
    df["IsClosed"] = (df["status"].fillna("") == "Closed").astype(int)
    hours = (df["closed"] - df["created"]).dt.total_seconds() / 3600
    timed = (df["IsClosed"] == 1) & hours.notna() & (hours >= 0)
    df["TimedClosed"] = timed.astype(int)
    df["ResponseHours"] = hours.where(timed, 0.0)
    for n in WITHIN_DAYS:
        df[f"Within{n}d"] = (timed & (hours <= n * 24)).astype(int)
    return df


MEASURES = ["Requests", "Closed", "TimedClosed", "ResponseHoursSum"] + [f"Within{n}d" for n in WITHIN_DAYS]


def aggregate(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    out = df.groupby(keys, observed=True).agg(
        Requests=("unique_key", "size"),
        Closed=("IsClosed", "sum"),
        TimedClosed=("TimedClosed", "sum"),
        ResponseHoursSum=("ResponseHours", "sum"),
        **{f"Within{n}d": (f"Within{n}d", "sum") for n in WITHIN_DAYS},
    ).reset_index()
    out["ResponseHoursSum"] = out["ResponseHoursSum"].round(2)
    return out


def build_dim_date(start, end, as_of) -> pd.DataFrame:
    d = pd.DataFrame({"Date": pd.date_range(start, end, freq="D")})
    holidays = USFederalHolidayCalendar().holidays(start, end)
    d["Year"] = d.Date.dt.year
    d["Quarter"] = "Q" + d.Date.dt.quarter.astype(str)
    d["MonthNum"] = d.Date.dt.month
    d["MonthName"] = d.Date.dt.strftime("%b")
    d["YearMonth"] = d.Date.dt.strftime("%Y-%m")
    d["MonthStart"] = d.Date.dt.to_period("M").dt.start_time
    d["WeekStart"] = d.Date - pd.to_timedelta(d.Date.dt.weekday, unit="D")
    d["Weekday"] = d.Date.dt.strftime("%a")
    d["WeekdayNum"] = d.Date.dt.weekday + 1          # Monday = 1, for sorting
    d["IsWeekend"] = (d.Date.dt.weekday >= 5).astype(int)
    d["IsHoliday"] = d.Date.isin(holidays).astype(int)
    d["Season"] = d.MonthNum.map(season)
    d["IsMatureCohort"] = (d.Date <= as_of - pd.Timedelta(days=MATURE_DAYS)).astype(int)
    d["IsCompleteMonth"] = (d.MonthStart < as_of.to_period("M").start_time).astype(int)
    return d


def main():
    months = sorted(RAW_DIR.glob("created_*.parquet"))
    if not months:
        raise SystemExit("No raw files found. Run python\\01_fetch.py first.")
    raw = pd.concat([pd.read_parquet(f) for f in months], ignore_index=True)
    open_raw = pd.read_parquet(RAW_DIR / "open_requests.parquet")
    fetched_at = pd.Timestamp((RAW_DIR / "fetched_at.txt").read_text().strip())
    print(f"Read {len(raw):,} requests from {len(months)} monthly files, {len(open_raw):,} open requests")

    df = clean(raw)
    op = clean(open_raw)
    op = op[op["IsClosed"] == 0]
    window_start = pd.Timestamp(months[0].stem.replace("created_", "") + "-01")
    latest = df["created"].max()
    as_of = latest.normalize()

    # ---------- dimensions (built from both pulls so every key in every fact exists) ----------
    both = pd.concat([df, op], ignore_index=True)

    types = sorted(both["ComplaintType"].unique())
    dim_complaint = pd.DataFrame({"ComplaintKey": range(1, len(types) + 1), "ComplaintType": types})
    dim_complaint["Category"] = dim_complaint["ComplaintType"].map(complaint_category)
    key_of = dict(zip(dim_complaint.ComplaintType, dim_complaint.ComplaintKey))
    df["ComplaintKey"] = df["ComplaintType"].map(key_of)
    op["ComplaintKey"] = op["ComplaintType"].map(key_of)
    df["Category"] = df["ComplaintType"].map(complaint_category)

    dim_category = pd.DataFrame({"Category": sorted(dim_complaint["Category"].unique())})

    dim_agency = (both.groupby("AgencyKey")["agency_name"].agg(lambda s: s.mode().iat[0])
                  .rename("AgencyName").reset_index())

    dim_borough = pd.DataFrame({"Borough": BOROUGHS, "BoroughSort": range(1, len(BOROUGHS) + 1)})

    loc = df[df["ZIP"] != "Unknown"]
    dim_location = loc.groupby("ZIP").agg(
        Borough=("Borough", lambda s: s[s != "Unspecified"].mode().iat[0] if (s != "Unspecified").any() else "Unspecified"),
        Latitude=("lat", "median"),
        Longitude=("lon", "median"),
    ).reset_index()
    dim_location = pd.concat([dim_location, pd.DataFrame(
        {"ZIP": ["Unknown"], "Borough": ["Unspecified"], "Latitude": [None], "Longitude": [None]})], ignore_index=True)
    dim_location[["Latitude", "Longitude"]] = dim_location[["Latitude", "Longitude"]].round(5)

    dim_date = build_dim_date(window_start, as_of, as_of)

    # ---------- facts ----------
    fact_daily = aggregate(df, ["Date", "ComplaintKey", "AgencyKey", "Borough"])

    df["MonthStart"] = df["Date"].dt.to_period("M").dt.start_time
    fact_zip = aggregate(df, ["MonthStart", "ZIP", "Category"])

    age = (fetched_at.tz_localize(None) - op["created"]).dt.days
    op["AgeBucket"] = pd.cut(age, [-1, 7, 30, 90, 10_000], labels=["0-7 days", "8-30 days", "31-90 days", "91+ days"])
    op["AgeDays"] = age
    fact_backlog = op.groupby(["AgeBucket", "ComplaintKey", "AgencyKey", "Borough"], observed=True).agg(
        OpenRequests=("unique_key", "size"), AgeDaysSum=("AgeDays", "sum")).reset_index()
    fact_backlog["AgeBucketSort"] = fact_backlog["AgeBucket"].cat.codes + 1

    refresh = pd.DataFrame([{
        "FetchedAt": fetched_at.strftime("%Y-%m-%d %H:%M"),
        "LatestRequest": latest.strftime("%Y-%m-%d %H:%M"),
        "DataAsOf": as_of.strftime("%Y-%m-%d"),
        "WindowStart": window_start.strftime("%Y-%m-%d"),
        "TotalRequests": len(df),
        "OpenRequests": len(op),
    }])

    # ---------- write ----------
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "fact_requests_daily": fact_daily, "fact_zip_monthly": fact_zip, "fact_open_backlog": fact_backlog,
        "dim_date": dim_date, "dim_complaint": dim_complaint, "dim_category": dim_category,
        "dim_agency": dim_agency, "dim_borough": dim_borough, "dim_location": dim_location,
        "refresh_info": refresh,
    }
    for name, table in out.items():
        path = MODEL_DIR / f"{name}.csv"
        table.to_csv(path, index=False, date_format="%Y-%m-%d")
        print(f"  {name}.csv: {len(table):,} rows, {path.stat().st_size / 1e6:.1f} MB")
    print(f"Data as of {as_of:%Y-%m-%d}: {len(df):,} requests, {len(op):,} still open")


if __name__ == "__main__":
    main()
