"""Basic source diagnostics: keep documentation grounded in the downloaded data."""
import json
from pathlib import Path
import pandas as pd


def profile_model_source(data_dir: Path, output_dir: Path) -> dict:
    path = data_dir / "creditcard_clean.csv.gz"
    if not path.exists():
        raise FileNotFoundError("Run `fraudopt ingest-model` first")
    df = pd.read_csv(path)
    report = {
        "source": "OpenML #43627: anonymised ULB card transactions, September 2013",
        "rows": int(len(df)),
        "columns": df.columns.tolist(),
        "null_count_by_column": {k: int(v) for k, v in df.isna().sum().items()},
        "fraud_count": int(df.is_fraud.sum()),
        "fraud_rate": float(df.is_fraud.mean()),
        "elapsed_time_seconds_min_max": [float(df.elapsed_seconds.min()), float(df.elapsed_seconds.max())],
        "amount_quantiles": {str(q): float(df.amount.quantile(q)) for q in (0.0, 0.5, 0.9, 0.99, 1.0)},
        "fraud_by_elapsed_hour": [
            {"elapsed_hour": int(hour), "transactions": int(group.shape[0]),
             "frauds": int(group.is_fraud.sum())}
            for hour, group in df.groupby((df.elapsed_seconds // 3600).astype(int))
        ],
        "duplicate_looking_pca_records_removed": False,
        "notes": ["The original Time is elapsed seconds, not a date.",
                  "V1-V28 are anonymous PCA components; their semantic meaning is unknown.",
                  "No transaction/customer identifier available for deterministic deduplication.",
                  "Historical 2013 data do not represent current fraud prevalence."],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source_profile.json").write_text(json.dumps(report, indent=2))
    return report
