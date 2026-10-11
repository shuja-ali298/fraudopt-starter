"""Updated CFPB *complaint trend* observations. NOT fraud labels or bank transactions."""
from __future__ import annotations
import io
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
PRODUCT = "Money transfer, virtual currency, or money service"
EXPORT_CAP = 100000
FRAUD_WORDS = re.compile(r"\b(fraud|scam|scammed|unauthori[sz]ed|identity theft)\b", re.I)

# CFPB exports have user-facing headers; aliases permit a documented API-style schema too.
ALIASES = {
    "complaint_id": ["complaint id", "complaint_id"],
    "date_received": ["date received", "date_received"],
    "product": ["product"],
    "issue": ["issue"],
    "sub_issue": ["sub issue", "sub_issue"],
    "state": ["state"],
}

def canonical(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def clean_complaints(raw: pd.DataFrame, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    lookup = {canonical(name): name for name in raw.columns}
    renames = {}
    for name, alternatives in ALIASES.items():
        for alias in alternatives:
            original = lookup.get(canonical(alias))
            if original is not None:
                renames[original] = name
                break
        else:
            if name in {"complaint_id", "date_received", "product", "issue"}:
                raise ValueError(f"CFPB CSV missing mandatory header for {name}: {list(raw.columns)}")
    df = raw.rename(columns=renames).copy()
    for name in ALIASES:
        if name not in df.columns:
            df[name] = ""
    df = df[list(ALIASES)]
    df["complaint_id"] = df["complaint_id"].astype("string").str.strip()
    if df["complaint_id"].isna().any() or df["complaint_id"].eq("").any():
        raise ValueError("CFPB returned null/blank complaint identifiers")
    parsed_dates = pd.to_datetime(df["date_received"], errors="coerce", utc=True)
    if parsed_dates.isna().any():
        raise ValueError("Invalid CFPB date_received value")
    df["date_received"] = parsed_dates.dt.strftime("%Y-%m-%d")
    for col in ("product", "issue", "sub_issue", "state"):
        df[col] = df[col].fillna("").astype(str).str.strip()
    # Source API filter checked again as a defence against ignored/changed parameters.
    if not df.empty and not df["product"].eq(PRODUCT).all():
        raise ValueError("Source ignored/changed CFPB product filter")
    if start is not None and (df["date_received"] < start.isoformat()).any():
        raise ValueError("CFPB delivered records before requested date range")
    if end is not None and (df["date_received"] >= end.isoformat()).any():
        raise ValueError("CFPB delivered records beyond requested date range")
    df["potential_fraud_issue"] = [int(bool(FRAUD_WORDS.search(a + " " + b)))
                                     for a, b in zip(df["issue"], df["sub_issue"])]
    return df.drop_duplicates("complaint_id", keep="last").reset_index(drop=True)


def session_with_retries() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    # Keep Requests' standard User-Agent: the CFPB edge rejects the custom
    # fraudopt-portfolio-research/0.1 agent with 403 for valid public CSV queries.
    return s


def fetch_window(s: requests.Session, start: date, end: date) -> pd.DataFrame:
    if end <= start:
        raise ValueError("Complaint window end must be after start")
    # Export CSV explicitly; CFPB retired JSON exports in July 2026.
    # Live CSV exports include the maximum calendar date despite the API docs
    # describing it as exclusive. Convert our [start, end) window accordingly.
    response = s.get(API, params={"date_received_min": start.isoformat(),
                                  "date_received_max": (end - timedelta(days=1)).isoformat(),
                                  "product": PRODUCT, "format": "csv"}, timeout=90)
    response.raise_for_status()
    body = response.content.decode("utf-8-sig")
    if body.lstrip().startswith(("<", "{")):
        raise ValueError("Expected CFPB CSV export but received HTML/JSON")
    if not body.strip():
        raise ValueError("Blank CFPB response: ingestion completeness cannot be verified")
    raw = pd.read_csv(io.StringIO(body), dtype=str, keep_default_na=False, on_bad_lines="error")
    if len(raw) >= EXPORT_CAP:
        # Current filtered export cap is 100k; split date range to avoid truncation.
        if (end - start).days <= 1:
            raise ValueError("CFPB single-day export reached 100k cap; use narrower filters")
        middle = start + timedelta(days=max(1, (end - start).days // 2))
        return pd.concat([fetch_window(s, start, middle), fetch_window(s, middle, end)], ignore_index=True)
    return clean_complaints(raw, start, end)


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("""CREATE TABLE IF NOT EXISTS complaints (
        complaint_id TEXT PRIMARY KEY,
        date_received TEXT NOT NULL,
        product TEXT NOT NULL,
        issue TEXT NOT NULL,
        sub_issue TEXT NOT NULL,
        state TEXT NOT NULL,
        potential_fraud_issue INTEGER NOT NULL CHECK (potential_fraud_issue IN (0,1))
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_complaints_date ON complaints(date_received)")
    return conn


def upsert(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    sql = """INSERT INTO complaints
        (complaint_id,date_received,product,issue,sub_issue,state,potential_fraud_issue)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(complaint_id) DO UPDATE SET
        date_received=excluded.date_received,
        product=excluded.product, issue=excluded.issue,
        sub_issue=excluded.sub_issue, state=excluded.state,
        potential_fraud_issue=excluded.potential_fraud_issue"""
    with conn:
        conn.executemany(sql, list(df[["complaint_id", "date_received", "product", "issue", "sub_issue", "state", "potential_fraud_issue"]].itertuples(index=False, name=None)))
    return len(df)


def ingest_cfpb(data_dir: Path, lookback_days: int = 90, today: date | None = None,
                s: requests.Session | None = None) -> dict:
    if lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    today = today or date.today()
    first = today - timedelta(days=lookback_days - 1)
    # Re-pull an overlapping window: publications can be delayed and records revised.
    # Records older than lookback_days cannot be captured if newly published now.
    end_limit = today + timedelta(days=1)
    s = s or session_with_retries()
    conn = connect_db(data_dir / "complaints.sqlite")
    fetched = 0
    try:
        cursor = first
        while cursor < end_limit:
            right = min(cursor + timedelta(days=7), end_limit)
            batch = fetch_window(s, cursor, right)
            fetched += upsert(conn, batch)
            cursor = right
        count = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        report = pd.read_sql_query("""SELECT date_received, COUNT(*) AS complaint_count,
                SUM(potential_fraud_issue) AS potential_fraud_issue_count
                FROM complaints GROUP BY date_received ORDER BY date_received""", conn)
        out = data_dir.parent / "outputs" / "complaint_daily_trends.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        report.to_csv(out, index=False)
        return {"rows_downloaded_or_rechecked": fetched, "unique_complaints_in_store": count,
                "days_in_store": len(report), "report": str(out),
                "window_start": first.isoformat(), "window_end_exclusive": end_limit.isoformat(),
                "ingestion_complete": True}
    finally:
        conn.close()
