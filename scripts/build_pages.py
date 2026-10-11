"""Build a static dashboard: python scripts/build_pages.py."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from fraudopt.dashboard import validate_predictions, validate_trends
from fraudopt.diagnostics import write_diagnostics


def build(source, destination):
    predictions = validate_predictions(pd.read_csv(source / 'test_predictions.csv.gz'))
    complaints = validate_trends(pd.read_csv(source / 'complaint_daily_trends.csv'))
    report = json.loads((source / 'model_report.json').read_text())
    destination.mkdir(parents=True, exist_ok=True)
    for name in ['index.html', 'style.css', 'app.js', 'policy.js']:
        shutil.copyfile(ROOT / 'web' / name, destination / name)
    payload = {'report': report, 'prediction_columns': predictions.columns.tolist(),
               'predictions': predictions.values.tolist(),
               'complaints': [{'date': row.date_received.strftime('%Y-%m-%d'),
                               'count': int(row.complaint_count),
                               'matches': int(row.potential_fraud_issue_count)}
                              for row in complaints.itertuples()],
               'built_at_utc': datetime.now(timezone.utc).isoformat(),
               'source': 'Committed demonstration snapshot; scheduled pipeline artifacts are separate.'}
    (destination / 'data.json').write_text(json.dumps(payload, separators=(',', ':'), allow_nan=False))
    write_diagnostics(predictions.true_label, predictions.fraud_risk, destination)
    (destination / '.nojekyll').touch()
    print(f'Built {destination}: {len(predictions):,} held-out predictions, {len(complaints)} complaint dates')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'dashboard_data')
    parser.add_argument('--destination', type=Path, default=ROOT / '_site')
    args = parser.parse_args()
    build(args.source, args.destination)
