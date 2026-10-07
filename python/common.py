"""Shared settings for the NYC 311 pipeline: paths, API details, the date window and category rules."""
from datetime import date
from pathlib import Path

# ---------- paths ----------
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"        # one Parquet file per month of raw API rows (git-ignored)
MODEL_DIR = ROOT / "data" / "model"    # star-schema CSVs that Power BI reads

# ---------- API ----------
DOMAIN = "data.cityofnewyork.us"
DATASET = "erm2-nwe9"                  # 311 Service Requests from 2010 to Present
PAGE_SIZE = 50_000                     # rows per API call
TIMEOUT = 300                          # seconds per API call; anonymous access can be slow
COLUMNS = [
    "unique_key", "created_date", "closed_date", "agency", "agency_name",
    "complaint_type", "status", "incident_zip", "borough", "latitude", "longitude",
]

# ---------- window ----------
MONTHS_BACK = 13      # full months kept before the current month (13 = same month last year + 12)
REFRESH_RECENT = 3    # the newest N months are re-downloaded every run, because open requests close later


def month_starts(months_back: int = MONTHS_BACK, today: date | None = None) -> list[date]:
    """First day of each month in the window, oldest first, ending with the current month."""
    today = today or date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(months_back + 1):
        out.append(date(y, m, 1))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def next_month(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


# ---------- response-time buckets ----------
WITHIN_DAYS = [1, 3, 7, 14, 30]        # "closed within N days" counts; Power BI picks the target with a slicer

# ---------- complaint categories ----------
# First matching keyword wins (case-insensitive). Anything unmatched is "Other".
CATEGORY_RULES = [
    ("Noise",                ["noise"]),
    ("Heat & Hot Water",     ["heat/hot water", "heating"]),
    ("Housing Conditions",   ["plumbing", "paint", "plaster", "door/window", "water leak", "general construction",
                              "unsanitary condition", "flooring", "electric", "mold", "appliance", "elevator",
                              "outside building", "safety", "general"]),
    ("Parking & Vehicles",   ["parking", "blocked driveway", "abandoned vehicle", "derelict vehicle", "vehicle",
                              "bike", "taxi", "for hire"]),
    ("Streets & Sidewalks",  ["street condition", "street light", "traffic", "sidewalk", "curb", "pothole",
                              "highway", "bridge", "street sign", "root/sewer", "obstruction", "bus stop"]),
    ("Sanitation & Litter",  ["dirty", "missed collection", "sanitation", "litter", "graffiti", "dumping",
                              "waste", "recycling", "snow", "sweeping", "disposal"]),
    ("Animals & Pests",      ["rodent", "pest", "mosquito", "animal"]),
    ("Environmental Health", ["lead", "air quality", "hazardous", "asbestos"]),
    ("Water & Sewer",        ["water", "sewer", "hydrant"]),
    ("Trees & Parks",        ["tree", "park", "plant", "maintenance or facility"]),
    ("Homelessness",         ["homeless", "encampment"]),
    ("Public Safety & Conduct", ["police", "panhandling", "drug", "drinking", "urinating", "fireworks",
                                "lost property", "disorderly"]),
    ("Buildings & Permits",  ["building", "construction", "illegal conversion", "scaffold", "permit"]),
    ("Consumer & Business",  ["consumer", "vendor", "food", "smoking", "restaurant", "dca", "outdoor dining",
                              "cannabis", "illegal posting"]),
]


def complaint_category(complaint_type: str) -> str:
    t = (complaint_type or "").lower()
    for category, keywords in CATEGORY_RULES:
        if any(k in t for k in keywords):
            return category
    return "Other"


def season(month: int) -> str:
    return {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
            6: "Summer", 7: "Summer", 8: "Summer"}.get(month, "Fall")
