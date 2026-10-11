"""Immutable historical model source: ULB credit-card dataset on OpenML #43627."""
from __future__ import annotations
import hashlib
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

DATASET_ID = 43627
# Direct OpenML canonical Parquet *preserves Time*. sklearn.fetch_openml can
# omit Time because this OpenML listing marks it as an ignored attribute.
PARQUET_URL = "https://data.openml.org/datasets/0004/43627/dataset_43627.pq"
PCA_COLUMNS = [f"V{i}" for i in range(1, 29)]
REQUIRED_COLUMNS = {"Time", "Amount", "Class", *PCA_COLUMNS}


def clean_creditcard(raw: pd.DataFrame) -> pd.DataFrame:
    """Strict rather than silent: fail on changed schema, bad rows or missing labels."""
    missing = REQUIRED_COLUMNS - set(raw.columns)
    if missing:
        raise ValueError(f"OpenML schema changed: missing {sorted(missing)}")
    frame = raw.loc[:, ["Time", *PCA_COLUMNS, "Amount", "Class"]].copy()
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col], errors="raise")
    if frame.isna().any().any() or not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Missing or non-finite numeric values in model source")
    if (frame["Amount"] < 0).any() or (frame["Time"] < 0).any():
        raise ValueError("Negative transaction amounts or elapsed time")
    if not frame["Class"].isin([0, 1]).all():
        raise ValueError("Target Class must contain only 0/1")
    frame = frame.rename(columns={"Time": "elapsed_seconds", "Amount": "amount", "Class": "is_fraud"})
    frame["is_fraud"] = frame["is_fraud"].astype("int8")
    # Safe deterministic transformation, no statistics learned from test period.
    frame["log_amount"] = np.log1p(frame["amount"])
    # Two indistinguishable PCA rows can be distinct transactions; do not deduplicate.
    frame = frame.sort_values("elapsed_seconds", kind="stable").reset_index(drop=True)
    if frame["is_fraud"].sum() < 10:
        raise ValueError("Too few positive labels for a valid fraud experiment")
    return frame


def ingest_openml(data_dir: Path, refresh: bool = False) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / "creditcard_clean.csv.gz"
    if dest.exists() and not refresh:
        return dest
    raw_parquet = data_dir / "creditcard_openml_43627.pq"
    if not raw_parquet.exists() or refresh:
        session = requests.Session()
        session.mount("https://", HTTPAdapter(max_retries=Retry(
            total=4, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504])))
        response = session.get(PARQUET_URL, stream=True, timeout=(20, 120))
        response.raise_for_status()
        temp_raw = raw_parquet.with_suffix(".download")
        with temp_raw.open("wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    out.write(chunk)
    # Read actual raw file, not fetch_openml's filtered feature matrix.
    # Fail loudly if source's fields no longer match published description.
    candidate = raw_parquet.with_suffix(".download") if not raw_parquet.exists() or refresh else raw_parquet
    raw = pd.read_parquet(candidate)
    clean = clean_creditcard(raw)
    # The original public snapshot is known to contain 284807 rows and 492 frauds.
    # Fail loudly if this mirror changes so the project can inspect the new version.
    if len(clean) != 284807 or int(clean.is_fraud.sum()) != 492:
        raise ValueError(f"Source snapshot unexpectedly changed: {len(clean)} rows, {clean.is_fraud.sum()} frauds")
    if candidate != raw_parquet:
        candidate.replace(raw_parquet)
    tmp = dest.with_suffix(".tmp")
    clean.to_csv(tmp, index=False, compression="gzip")
    tmp.replace(dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    manifest = {"source": PARQUET_URL, "openml_data_id": DATASET_ID,
                "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                "rows": len(clean), "fraud_rows": int(clean.is_fraud.sum()), "sha256_csv_gz": digest,
                "immutable_historical_snapshot": True}
    (data_dir / "creditcard_manifest.json").write_text(json.dumps(manifest, indent=2))
    return dest
