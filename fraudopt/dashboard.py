"""Validated data and policy comparisons for the stakeholder dashboard."""
import numpy as np
import pandas as pd
from pathlib import Path
from fraudopt.policy import select_reviews, evaluate_policy

PREDICTION_COLUMNS = ['elapsed_seconds', 'amount', 'true_label', 'fraud_risk']


def report_path(directory, name, allowed_directories):
    """Reject directories and symlink targets outside trusted report locations."""
    directory = Path(directory).resolve()
    if directory not in {Path(path).resolve() for path in allowed_directories}:
        raise ValueError('Choose an approved report location')
    path = (directory / name).resolve()
    if path.parent != directory:
        raise ValueError('Report file must stay inside its approved location')
    return path


def validate_predictions(frame):
    missing = set(PREDICTION_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Prediction file missing columns: {', '.join(sorted(missing))}")
    df = frame[PREDICTION_COLUMNS].apply(pd.to_numeric, errors='raise').copy()
    if df.empty or not np.isfinite(df.to_numpy()).all():
        raise ValueError('Prediction file must contain finite, nonempty observations')
    if not df.true_label.isin([0, 1]).all():
        raise ValueError('Prediction labels must be binary')
    select_reviews(df.fraud_risk, df.amount, df.elapsed_seconds, capacity_per_day=0)
    return df


def compare_policies(df, capacity, review_cost, friction_cost, effectiveness):
    """Select with scores only; reveal labels solely for retrospective evaluation."""
    rows, decisions = [], df.copy()
    day_count = int(np.floor(df.elapsed_seconds / 86400).nunique())
    for name, rank in [('Risk only', 'risk'), ('Expected value', 'expected_value')]:
        chosen = select_reviews(df.fraud_risk, df.amount, df.elapsed_seconds,
                                capacity, review_cost, friction_cost, effectiveness, rank)
        result = evaluate_policy(chosen, df.true_label, df.amount,
                                 review_cost, friction_cost, effectiveness)
        budget = capacity * day_count
        rows.append({'strategy': name, **result, 'available_reviews': budget,
                     'capacity_utilisation': result['reviews'] / budget if budget else 0.0})
        decisions[f'review_{rank}'] = chosen
    decisions['expected_review_benefit'] = (df.fraud_risk * df.amount * effectiveness
        - review_cost - (1 - df.fraud_risk) * friction_cost)
    return pd.DataFrame(rows).set_index('strategy'), decisions


def validate_trends(frame):
    required = ['date_received', 'complaint_count', 'potential_fraud_issue_count']
    if not set(required).issubset(frame.columns):
        raise ValueError('Complaint file is missing required date/count columns')
    df = frame[required].copy()
    df['date_received'] = pd.to_datetime(df.date_received, errors='raise').dt.normalize()
    counts = df[required[1:]].apply(pd.to_numeric, errors='raise')
    if df.date_received.isna().any() or df.date_received.duplicated().any():
        raise ValueError('Complaint dates must be valid and unique')
    if not np.isfinite(counts.to_numpy()).all() or (counts < 0).any().any() or (counts % 1 != 0).any().any():
        raise ValueError('Complaint counts must be finite nonnegative integers')
    if (counts.potential_fraud_issue_count > counts.complaint_count).any():
        raise ValueError('Issue-matching counts cannot exceed total complaints')
    df[required[1:]] = counts.astype(int)
    return df.sort_values('date_received')
