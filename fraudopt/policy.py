"""Capacity-constrained fraud review simulation. All costs in dataset amount units."""
from __future__ import annotations
import numpy as np


def validate_costs(review_cost, friction_cost, effectiveness):
    if not np.isfinite([review_cost, friction_cost, effectiveness]).all() or review_cost < 0 or friction_cost < 0 or not 0 <= effectiveness <= 1:
        raise ValueError("Invalid decisioning costs or effectiveness")


def select_reviews(scores: np.ndarray, amounts: np.ndarray, elapsed_seconds: np.ndarray,
                   capacity_per_day: int = 50, review_cost: float = 10.0,
                   friction_cost: float = 15.0, effectiveness: float = 0.7,
                   rank_by: str = "expected_value") -> np.ndarray:
    validate_costs(review_cost, friction_cost, effectiveness)
    if isinstance(capacity_per_day, (bool, np.bool_)) or not isinstance(capacity_per_day, (int, np.integer)) or capacity_per_day < 0:
        raise ValueError("Invalid decisioning constraints or costs")
    if rank_by not in {"expected_value", "risk"}:
        raise ValueError("rank_by must be expected_value or risk")
    p = np.asarray(scores, dtype=float)
    a = np.asarray(amounts, dtype=float)
    t = np.asarray(elapsed_seconds, dtype=float)
    if p.ndim != 1 or a.shape != p.shape or t.shape != p.shape or not np.isfinite(p).all() or not np.isfinite(a).all() or not np.isfinite(t).all():
        raise ValueError("Non-finite or incompatible policy inputs")
    if (p < 0).any() or (p > 1).any() or (a < 0).any() or (t < 0).any():
        raise ValueError("Invalid risk probabilities, amounts or elapsed seconds")
    expected_value = p * a * effectiveness - review_cost - (1 - p) * friction_cost
    utility = expected_value if rank_by == "expected_value" else p
    days = np.floor(t / 86400).astype(int)
    selected = np.zeros(len(p), dtype=bool)
    for day in np.unique(days):
        idx = np.flatnonzero(days == day)
        # risk-ranking comparator selects up to K, even when net benefit is negative;
        # optimise comparator only selects actions with positive estimated net benefit.
        eligible = idx[expected_value[idx] > 0] if rank_by == "expected_value" else idx
        order = eligible[np.argsort(-utility[eligible], kind="stable")]
        selected[order[:capacity_per_day]] = True
    return selected


def evaluate_policy(selected: np.ndarray, labels: np.ndarray, amounts: np.ndarray,
                    review_cost: float, friction_cost: float, effectiveness: float) -> dict:
    validate_costs(review_cost, friction_cost, effectiveness)
    selected = np.asarray(selected)
    labels = np.asarray(labels)
    amounts = np.asarray(amounts, dtype=float)
    if selected.ndim != 1 or labels.shape != selected.shape or amounts.shape != selected.shape:
        raise ValueError("Incompatible evaluation inputs")
    if not np.isin(selected, [0, 1]).all() or not np.isin(labels, [0, 1]).all() or not np.isfinite(amounts).all() or (amounts < 0).any():
        raise ValueError("Invalid selections, binary labels or amounts")
    selected = selected.astype(bool)
    fraud_reviewed = selected & (labels == 1)
    false_reviewed = selected & (labels == 0)
    value = (amounts[fraud_reviewed] * effectiveness).sum() - selected.sum() * review_cost - false_reviewed.sum() * friction_cost
    return {"reviews": int(selected.sum()), "fraud_found": int(fraud_reviewed.sum()),
            "false_reviews": int(false_reviewed.sum()),
            "fraud_recall": float(fraud_reviewed.sum() / max(1, (labels == 1).sum())),
            "precision": float(fraud_reviewed.sum() / max(1, selected.sum())),
            "simulated_net_benefit_amount_units": round(float(value), 2)}
