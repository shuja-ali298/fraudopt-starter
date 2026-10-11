"""Build a static dashboard: python scripts/build_pages.py."""
import argparse
from datetime import datetime, timezone
import json
import hashlib
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
    metadata_path = source / 'artifact_provenance.json'
    provenance = json.loads(metadata_path.read_text()) if metadata_path.exists() else {
        'sources': {'model': {'mode': 'snapshot'}, 'complaints': {'mode': 'snapshot'}}}
    for kind in ('model', 'complaints'):
        metadata = provenance['sources'][kind]
        if metadata['mode'] not in {'workflow_artifact', 'snapshot'}:
            raise ValueError('Unknown dashboard source mode')
        for name, digest in metadata.get('file_sha256', {}).items():
            if name not in {'model_report.json', 'test_predictions.csv.gz', 'complaint_daily_trends.csv'}:
                raise ValueError('Unexpected source file in provenance')
            if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
                raise ValueError('Staged dashboard file does not match its recorded hash')
    destination.mkdir(parents=True, exist_ok=True)
    for name in ['index.html', 'style.css', 'app.js', 'policy.js', 'icon.svg']:
        shutil.copyfile(ROOT / 'web' / name, destination / name)
    payload = {'report': report, 'prediction_columns': predictions.columns.tolist(),
               'predictions': predictions.values.tolist(),
               'complaints': [{'date': row.date_received.strftime('%Y-%m-%d'),
                               'count': int(row.complaint_count),
                               'matches': int(row.potential_fraud_issue_count)}
                              for row in complaints.itertuples()],
               'built_at_utc': datetime.now(timezone.utc).isoformat(),
               'source': 'Automatically selected workflow artifacts with labelled snapshot fallback.',
               'provenance': provenance}
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
